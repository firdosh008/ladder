import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

export default function AuthCallback() {
  const { session, loading, onboarded, recovering } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (loading) return;
    if (recovering) {
      navigate("/auth/reset-password", { replace: true });
      return;
    }
    if (session) {
      navigate(onboarded ? "/make" : "/onboarding", { replace: true });
      return;
    }
    const t = setTimeout(() => {
      if (!session) navigate("/auth", { replace: true });
    }, 3000);
    return () => clearTimeout(t);
  }, [session, loading, onboarded, recovering, navigate]);

  return (
    <div className="min-h-[100dvh] bg-night flex items-center justify-center text-white">
      <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-mist">
        · completing sign in ·
      </span>
    </div>
  );
}
