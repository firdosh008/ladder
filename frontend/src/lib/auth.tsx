import type { Session, User } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ApiError, api } from "./api";
import { supabase } from "./supabase";

export type Profile = {
  user_id: string;
  display_name: string | null;
  forwarding_alias: string | null;
  positioning: string | null;
  audience: string | null;
  voice: string | null;
  creators_followed: string[] | null;
  things_to_avoid: string | null;
  onboarded_at: string | null;
  avatar_storage_path: string | null;
  theme: string | null;
  font_scale: string | null;
  youtube_connected: boolean | null;
  youtube_channel_name: string | null;
  youtube_subscriber_count: number | null;
  youtube_last_sync: string | null;
  notion_token: string | null;
  gamma_api_key: string | null;
  nano_banana_api_key: string | null;
  linkedin_url: string | null;
  linkedin_scraped_at: string | null;
};

type AuthState = {
  session: Session | null;
  user: User | null;
  profile: Profile | null;
  onboarded: boolean;
  is_admin: boolean;
  loading: boolean;
  recovering: boolean;
  refreshProfile: () => Promise<void>;
  /** Synchronously mark the user as onboarded with a freshly-returned profile.
   *  Use immediately after a successful POST /auth/onboard so that the very next
   *  render (e.g. after a navigate call) sees onboarded=true — avoids the race
   *  where RequireAuth reads stale context and bounces back to /onboarding. */
  setProfileAndOnboarded: (profile: Profile, onboarded: boolean) => void;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [onboarded, setOnboarded] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [loading, setLoading] = useState(true);
  const [recovering, setRecovering] = useState(false);

  const refreshProfile = useCallback(async () => {
    try {
      const r = await api.get<{ profile: Profile | null; onboarded: boolean; is_admin: boolean }>("/auth/me");
      setProfile(r.profile);
      setOnboarded(r.onboarded);
      setIsAdmin(r.is_admin);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 404)) {
        setProfile(null);
        setOnboarded(false);
      } else {
        throw e;
      }
    }
  }, []);

  useEffect(() => {
    let active = true;

    (async () => {
      const { data } = await supabase.auth.getSession();
      if (!active) return;
      setSession(data.session);
      if (data.session) {
        await refreshProfile();
      }
      if (!active) return;
      setLoading(false);
    })();

    const { data: sub } = supabase.auth.onAuthStateChange((event, next) => {
      setSession(next);
      if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED" || event === "USER_UPDATED") {
        void refreshProfile();
      } else if (event === "PASSWORD_RECOVERY") {
        setRecovering(true);
      } else if (event === "SIGNED_OUT") {
        setProfile(null);
        setRecovering(false);
      }
    });

    return () => {
      active = false;
      sub.subscription.unsubscribe();
    };
  }, [refreshProfile]);

  const value: AuthState = {
    session,
    user: session?.user ?? null,
    profile,
    onboarded,
    is_admin: isAdmin,
    loading,
    recovering,
    refreshProfile,
    setProfileAndOnboarded: (p, ob) => {
      setProfile(p);
      setOnboarded(ob);
    },
    signOut: async () => {
      await supabase.auth.signOut();
    },
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function RequireAuth({
  children,
  requireOnboarded = true,
}: {
  children: ReactNode;
  requireOnboarded?: boolean;
}) {
  const { session, loading, onboarded } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-[100dvh] bg-night flex items-center justify-center">
        <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-mist">
          · verifying session ·
        </span>
      </div>
    );
  }

  if (!session) {
    return <Navigate to="/auth" state={{ from: location.pathname }} replace />;
  }

  if (requireOnboarded && !onboarded && location.pathname !== "/onboarding") {
    return <Navigate to="/onboarding" replace />;
  }

  return <>{children}</>;
}
