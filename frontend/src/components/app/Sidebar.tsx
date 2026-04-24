import { useMemo } from "react";
import { NavLink, Link, useNavigate } from "react-router-dom";
import {
  PlusCircle,
  Stack,
  BookOpen,
  GearSix,
  Sparkle,
  CaretUpDown,
  Lightning,
  SignOut,
} from "@phosphor-icons/react";
import { cn } from "../../lib/cn";
import { useAuth } from "../../lib/auth";
import { useIdeas } from "../../lib/useIdeas";

const nav = [
  { to: "/make", label: "Make a video", icon: PlusCircle, hint: "M" },
  { to: "/videos", label: "My videos", icon: Stack, hint: "V" },
  { to: "/library", label: "Library", icon: BookOpen, hint: "L" },
  { to: "/settings", label: "Settings", icon: GearSix, hint: "," },
];

export function Sidebar() {
  const auth = useAuth() as {
    user: { email?: string } | null;
    profile?: { display_name?: string | null } | null;
    signOut: () => Promise<void>;
  };
  const navigate = useNavigate();
  const { ideas } = useIdeas({ status: "new" });
  const topIdeas = useMemo(
    () =>
      [...ideas]
        .sort(
          (a, b) =>
            (b.opportunity_score ?? -1) - (a.opportunity_score ?? -1),
        )
        .slice(0, 3),
    [ideas],
  );
  const displayName = auth.profile?.display_name ?? auth.user?.email ?? "—";
  const subLabel =
    auth.profile?.display_name && auth.user?.email ? auth.user.email : "signed in";
  const avatarLetter = (displayName[0] ?? "?").toUpperCase();

  const handleSignOut = async () => {
    await auth.signOut();
    navigate("/auth", { replace: true });
  };

  return (
    <aside className="hidden md:flex w-[224px] shrink-0 flex-col border-r border-hairline bg-night">
      {/* Brand + workspace switcher */}
      <div className="px-3 pt-3.5 pb-3 border-b border-hairline">
        <Link to="/" className="flex items-center gap-2 px-2 py-1.5">
          <svg width="18" height="18" viewBox="0 0 32 32" aria-hidden="true">
            <path
              d="M8 22 L16 8 L24 22"
              stroke="#E8442A"
              strokeWidth="2.6"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
            <line
              x1="11"
              y1="17"
              x2="21"
              y2="17"
              stroke="#E8442A"
              strokeWidth="2.6"
              strokeLinecap="round"
            />
          </svg>
          <span className="font-sans font-semibold text-[14px] text-white tracking-tight">
            Ladder
          </span>
          <span className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-mist">
            /OS
          </span>
        </Link>

        <button
          type="button"
          className="mt-1 w-full flex items-center justify-between gap-2 h-8 px-2 rounded-md hover:bg-white/[0.04] transition-colors group"
        >
          <div className="flex items-center gap-2 min-w-0">
            <span className="h-5 w-5 rounded bg-cinnabar/[0.15] border border-cinnabar/25 grid place-items-center text-cinnabar font-mono text-[10px] font-bold">
              {avatarLetter}
            </span>
            <span className="text-[12.5px] text-white/90 font-medium truncate">
              {displayName}
            </span>
          </div>
          <CaretUpDown size={12} className="text-mist shrink-0 opacity-70" />
        </button>
      </div>

      {/* Primary nav */}
      <nav className="px-2 py-3 space-y-0.5">
        {nav.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "group relative flex items-center gap-2.5 h-8 px-2.5 rounded-md text-[13px]",
                  "transition-colors duration-150",
                  isActive
                    ? "bg-white/[0.05] text-white"
                    : "text-white/70 hover:text-white hover:bg-white/[0.03]",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive ? (
                    <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-r-full bg-cinnabar" />
                  ) : null}
                  <Icon
                    size={14}
                    weight={isActive ? "fill" : "regular"}
                    className={cn(
                      "shrink-0",
                      isActive ? "text-cinnabar" : "text-mist group-hover:text-white",
                    )}
                  />
                  <span className="font-sans flex-1">{item.label}</span>
                  <span
                    className={cn(
                      "font-mono text-[10px] text-mist shrink-0",
                      "opacity-0 group-hover:opacity-100 transition-opacity",
                    )}
                  >
                    {item.hint}
                  </span>
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      {/* Separator with label */}
      <div className="px-2 mt-2 mb-1">
        <div className="px-2.5 flex items-center justify-between h-6">
          <span className="font-mono text-[9.5px] uppercase tracking-[0.22em] text-mist">
            top ideas
          </span>
          <Sparkle size={10} className="text-cinnabar opacity-80" />
        </div>
      </div>

      {/* Top ideas by opportunity_score */}
      <div className="px-2 space-y-0.5">
        {topIdeas.length === 0 ? (
          <div className="px-2.5 py-2 font-mono text-[10.5px] text-mist">
            · none yet ·
          </div>
        ) : (
          topIdeas.map((idea) => (
            <button
              key={idea.id}
              type="button"
              onClick={() => navigate(`/studio/${idea.id}`)}
              className="w-full group flex items-center gap-2.5 h-auto py-2 px-2.5 rounded-md text-left hover:bg-white/[0.03] transition-colors"
            >
              <span
                className={cn(
                  "font-mono mono-tab text-[10.5px] shrink-0 tabular-nums",
                  (idea.opportunity_score ?? 0) >= 90
                    ? "text-cinnabar"
                    : "text-mist",
                )}
              >
                {idea.opportunity_score ?? "—"}
              </span>
              <span className="text-[12px] text-white/75 leading-snug truncate group-hover:text-white">
                {idea.title}
              </span>
            </button>
          ))
        )}
      </div>

      <div className="flex-1" />

      {/* User / seat info */}
      <div className="border-t border-hairline p-2">
        <div className="w-full flex items-center gap-1.5">
          <button
            type="button"
            className="flex-1 min-w-0 flex items-center gap-2.5 h-10 px-2 rounded-md hover:bg-white/[0.04] transition-colors"
          >
            <span className="h-7 w-7 rounded-full bg-cinnabar/[0.15] border border-cinnabar/30 grid place-items-center text-cinnabar text-[11px] font-mono font-bold">
              {avatarLetter}
            </span>
            <div className="flex flex-col min-w-0 leading-tight text-left">
              <span className="text-[12.5px] text-white font-medium truncate">
                {displayName}
              </span>
              <span className="text-[10.5px] text-mist font-mono truncate flex items-center gap-1">
                <Lightning size={9} weight="fill" className="text-cinnabar" />
                {subLabel}
              </span>
            </div>
          </button>
          <button
            type="button"
            onClick={handleSignOut}
            className="text-mist hover:text-white transition-colors p-1.5 rounded-md hover:bg-white/[0.04] shrink-0"
            aria-label="Sign out"
            title="Sign out"
          >
            <SignOut size={14} />
          </button>
        </div>
      </div>
    </aside>
  );
}
