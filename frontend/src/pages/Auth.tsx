import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  EnvelopeSimple,
  GoogleLogo,
  LockKey,
  Warning,
} from "@phosphor-icons/react";
import { Button } from "../components/ui/Button";
import { Input, FieldLabel } from "../components/ui/Input";
import { useAuth } from "../lib/auth";
import { supabase } from "../lib/supabase";
import { cn } from "../lib/cn";

type Mode = "signin" | "signup" | "verify-otp" | "forgot-password";

const RESEND_SECONDS = 60;

export default function AuthPage() {
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otpEmail, setOtpEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [resendCooldown, setResendCooldown] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { session, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const redirectTo =
    (location.state as { from?: string } | null)?.from ?? "/make";

  const cooldownTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!loading && session) navigate(redirectTo, { replace: true });
  }, [loading, session, navigate, redirectTo]);

  useEffect(() => {
    return () => {
      if (cooldownTimer.current) clearInterval(cooldownTimer.current);
    };
  }, []);

  function startResendCooldown() {
    if (cooldownTimer.current) clearInterval(cooldownTimer.current);
    setResendCooldown(RESEND_SECONDS);
    cooldownTimer.current = setInterval(() => {
      setResendCooldown((n) => {
        if (n <= 1) {
          if (cooldownTimer.current) clearInterval(cooldownTimer.current);
          return 0;
        }
        return n - 1;
      });
    }, 1000);
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
    setNotice(null);
  }

  function resetToSignIn() {
    setOtp("");
    setOtpEmail("");
    setPassword("");
    switchMode("signin");
  }

  async function handleSignIn() {
    const { error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (!error) return;
    const msg = error.message.toLowerCase();
    if (msg.includes("email") && msg.includes("not confirm")) {
      await supabase.auth.signInWithOtp({
        email,
        options: { shouldCreateUser: false },
      });
      setOtpEmail(email);
      setMode("verify-otp");
      startResendCooldown();
      setNotice("Confirm your email with the 6-digit code we just sent.");
      return;
    }
    if (msg.includes("invalid")) {
      setError("Wrong email or password.");
      return;
    }
    setError(error.message);
  }

  async function handleSignUp() {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) throw error;
    if (data.user && data.user.identities?.length === 0) {
      setError(
        "An account with this email already exists. Sign in or reset your password.",
      );
      return;
    }
    setOtpEmail(email);
    setMode("verify-otp");
    startResendCooldown();
    setNotice("We sent a 6-digit code to your inbox.");
  }

  async function handleVerifyOtp() {
    const { error } = await supabase.auth.verifyOtp({
      email: otpEmail,
      token: otp,
      type: "email",
    });
    if (error) throw error;
    navigate("/auth/callback", { replace: true });
  }

  async function handleForgotPassword() {
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/reset-password`,
    });
    if (error) throw error;
    setNotice("Check your inbox — password reset link sent.");
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      if (mode === "signin") await handleSignIn();
      else if (mode === "signup") await handleSignUp();
      else if (mode === "verify-otp") await handleVerifyOtp();
      else if (mode === "forgot-password") await handleForgotPassword();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function onResendOtp() {
    if (resendCooldown > 0 || busy) return;
    setError(null);
    setBusy(true);
    try {
      const { error } = await supabase.auth.signInWithOtp({
        email: otpEmail,
        options: { shouldCreateUser: false },
      });
      if (error) throw error;
      startResendCooldown();
      setNotice("New code sent.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resend code.");
    } finally {
      setBusy(false);
    }
  }

  async function onGoogle() {
    setError(null);
    setBusy(true);
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: { redirectTo: `${window.location.origin}/auth/callback` },
      });
      if (error) throw error;
    } catch (err) {
      setError(err instanceof Error ? err.message : "OAuth failed.");
      setBusy(false);
    }
  }

  const eyebrow = (() => {
    switch (mode) {
      case "signin":
        return "§ return · pick up";
      case "signup":
        return "§ new · begin";
      case "verify-otp":
        return "§ confirm · 6 digits";
      case "forgot-password":
        return "§ reset · password";
    }
  })();

  const headline = (() => {
    switch (mode) {
      case "signin":
        return "Welcome back.";
      case "signup":
        return "Make your account.";
      case "verify-otp":
        return "Check your email.";
      case "forgot-password":
        return "Reset your password.";
    }
  })();

  const subhead = (() => {
    switch (mode) {
      case "signin":
        return "Your ideas, scripts, scenes and metrics — exactly where you left them.";
      case "signup":
        return "Takes 20 seconds. Your content graph starts the moment you land inside.";
      case "verify-otp":
        return `We sent a 6-digit code to ${otpEmail}. Enter it below to confirm.`;
      case "forgot-password":
        return "Enter your email and we'll send you a link to set a new password.";
    }
  })();

  const submitLabel = (() => {
    if (busy) return "· working ·";
    switch (mode) {
      case "signin":
        return "Sign in";
      case "signup":
        return "Create account";
      case "verify-otp":
        return "Confirm code";
      case "forgot-password":
        return "Send reset link";
    }
  })();

  const showModeToggle = mode === "signin" || mode === "signup";
  const showEmail = mode !== "verify-otp";
  const showPassword = mode === "signin" || mode === "signup";
  const showOtp = mode === "verify-otp";
  const showGoogle = mode === "signin" || mode === "signup";

  return (
    <div className="min-h-[100dvh] bg-night text-white grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
      {/* ── LEFT: form column ──────────────────────────────────────────── */}
      <div className="flex flex-col min-h-[100dvh]">
        <TopBar mode={mode} />

        <div className="flex-1 flex items-center justify-center px-6 py-12">
          <div className="w-full max-w-[400px]">
            <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-4">
              {eyebrow}
            </div>

            <h1 className="font-display font-bold text-[40px] leading-[1.02] tracking-tight text-white mb-2">
              {headline}
            </h1>
            <p className="text-[14px] text-white/60 leading-[1.55] mb-8 max-w-[38ch]">
              {subhead}
            </p>

            {showModeToggle ? (
              <div className="mb-7 inline-flex items-center p-0.5 border border-hairline rounded-md bg-surface">
                <ModeTab
                  active={mode === "signin"}
                  onClick={() => switchMode("signin")}
                >
                  Sign in
                </ModeTab>
                <ModeTab
                  active={mode === "signup"}
                  onClick={() => switchMode("signup")}
                >
                  Sign up
                </ModeTab>
              </div>
            ) : null}

            <form onSubmit={onSubmit} className="space-y-4">
              {showEmail ? (
                <div>
                  <FieldLabel htmlFor="email">Email</FieldLabel>
                  <div className="relative">
                    <EnvelopeSimple
                      size={14}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-mist"
                    />
                    <Input
                      id="email"
                      type="email"
                      autoComplete="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="alex@ladder.so"
                      className="pl-9"
                    />
                  </div>
                </div>
              ) : null}

              {showPassword ? (
                <div>
                  <FieldLabel
                    htmlFor="password"
                    hint={mode === "signup" ? "min 8 chars" : undefined}
                  >
                    Password
                  </FieldLabel>
                  <div className="relative">
                    <LockKey
                      size={14}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-mist"
                    />
                    <Input
                      id="password"
                      type="password"
                      autoComplete={
                        mode === "signin" ? "current-password" : "new-password"
                      }
                      required
                      minLength={mode === "signup" ? 8 : 1}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="pl-9"
                    />
                  </div>
                </div>
              ) : null}

              {showOtp ? (
                <div>
                  <FieldLabel htmlFor="otp" hint="6 digits">
                    Confirmation code
                  </FieldLabel>
                  <Input
                    id="otp"
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={6}
                    autoComplete="one-time-code"
                    required
                    value={otp}
                    onChange={(e) =>
                      setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    placeholder="123456"
                    className="font-mono tracking-[0.35em] text-center text-[16px]"
                  />
                </div>
              ) : null}

              {error ? (
                <div className="flex items-start gap-2 rounded-md border border-sienna/40 bg-sienna/10 px-3 py-2 text-[12.5px] text-white/90">
                  <Warning
                    size={13}
                    weight="fill"
                    className="text-sienna shrink-0 mt-0.5"
                  />
                  <span className="leading-[1.45]">{error}</span>
                </div>
              ) : null}
              {notice ? (
                <div className="rounded-md border border-cinnabar/30 bg-cinnabar/[0.06] px-3 py-2 text-[12.5px] text-white/90 leading-[1.45]">
                  {notice}
                </div>
              ) : null}

              <Button
                type="submit"
                size="lg"
                className="w-full"
                disabled={busy || (mode === "verify-otp" && otp.length !== 6)}
              >
                {submitLabel}
                {!busy ? <ArrowRight size={13} weight="bold" /> : null}
              </Button>
            </form>

            {mode === "signin" ? (
              <div className="mt-3 text-right">
                <button
                  type="button"
                  onClick={() => switchMode("forgot-password")}
                  className="font-mono text-[11px] uppercase tracking-[0.18em] text-mist hover:text-white transition-colors"
                >
                  Forgot password?
                </button>
              </div>
            ) : null}

            {mode === "forgot-password" ? (
              <div className="mt-4">
                <button
                  type="button"
                  onClick={() => switchMode("signin")}
                  className="font-mono text-[11px] uppercase tracking-[0.18em] text-mist hover:text-white transition-colors"
                >
                  ← back to sign in
                </button>
              </div>
            ) : null}

            {mode === "verify-otp" ? (
              <div className="mt-4 flex items-center justify-between">
                <button
                  type="button"
                  onClick={onResendOtp}
                  disabled={resendCooldown > 0 || busy}
                  className="font-mono text-[11px] uppercase tracking-[0.18em] text-mist hover:text-white transition-colors disabled:opacity-40 disabled:hover:text-mist"
                >
                  {resendCooldown > 0
                    ? `Resend (${resendCooldown}s)`
                    : "Resend code"}
                </button>
                <button
                  type="button"
                  onClick={resetToSignIn}
                  className="font-mono text-[11px] uppercase tracking-[0.18em] text-mist hover:text-white transition-colors"
                >
                  Not your account? Start over
                </button>
              </div>
            ) : null}

            {showGoogle ? (
              <>
                <div className="flex items-center gap-3 my-6">
                  <div className="flex-1 h-px bg-hairline" />
                  <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-mist">
                    or
                  </span>
                  <div className="flex-1 h-px bg-hairline" />
                </div>

                <Button
                  type="button"
                  variant="secondary"
                  size="lg"
                  className="w-full"
                  onClick={onGoogle}
                  disabled={busy}
                >
                  <GoogleLogo size={14} weight="bold" />
                  Continue with Google
                </Button>
              </>
            ) : null}

            {mode === "signin" ? (
              <p className="mt-8 text-[12px] text-mist leading-[1.55]">
                New here?{" "}
                <button
                  type="button"
                  onClick={() => switchMode("signup")}
                  className="text-white hover:text-cinnabar transition-colors underline underline-offset-4 decoration-hairline hover:decoration-cinnabar"
                >
                  Make an account
                </button>
                .
              </p>
            ) : null}
            {mode === "signup" ? (
              <p className="mt-8 text-[12px] text-mist leading-[1.55]">
                Already inside?{" "}
                <button
                  type="button"
                  onClick={() => switchMode("signin")}
                  className="text-white hover:text-cinnabar transition-colors underline underline-offset-4 decoration-hairline hover:decoration-cinnabar"
                >
                  Sign in
                </button>
                .
              </p>
            ) : null}

            <p className="mt-2 text-[11px] text-mist leading-[1.55] font-mono">
              By continuing you agree to ship videos, not drafts.
            </p>
          </div>
        </div>

        <div className="border-t border-hairline px-6 py-3 flex items-center justify-between font-mono text-[10.5px] text-mist uppercase tracking-[0.2em]">
          <Link to="/" className="hover:text-white transition-colors">
            ← back to landing
          </Link>
          <span>v0.1.0 · pre-release</span>
        </div>
      </div>

      {/* ── RIGHT: editorial panel ─────────────────────────────────────── */}
      <EditorialPanel />
    </div>
  );
}

function TopBar({ mode }: { mode: Mode }) {
  const label =
    mode === "signin"
      ? "sign in"
      : mode === "signup"
        ? "sign up"
        : mode === "verify-otp"
          ? "confirm"
          : "reset";
  return (
    <div className="border-b border-hairline px-6 py-4 flex items-center gap-2">
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
      <span className="font-sans font-semibold text-[14px] text-white">
        Ladder
      </span>
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-mist">
        /OS · {label}
      </span>
      <div className="flex-1" />
      <span className="font-mono text-[10.5px] text-mist tabular-nums">
        private β
      </span>
    </div>
  );
}

function ModeTab({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "h-7 px-3 text-[12.5px] font-medium rounded-[5px] transition-colors",
        active
          ? "bg-cinnabar text-white"
          : "text-mist hover:text-white",
      )}
    >
      {children}
    </button>
  );
}

function EditorialPanel() {
  return (
    <div className="hidden lg:flex relative overflow-hidden border-l border-hairline bg-[#0B0B0B] flex-col justify-between p-10">
      {/* Ambient gradient — cinnabar bloom top-right, sienna pool bottom-left */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.55]"
        style={{
          background:
            "radial-gradient(520px 520px at 85% -10%, rgba(232,68,42,0.22), transparent 60%), radial-gradient(700px 500px at -20% 120%, rgba(139,74,58,0.2), transparent 65%)",
        }}
      />
      {/* Grain */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.06] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>\")",
        }}
      />

      {/* Top eyebrow */}
      <div className="relative flex items-center gap-3">
        <span className="h-1.5 w-1.5 rounded-full bg-cinnabar animate-pulse" />
        <span className="font-mono text-[10.5px] uppercase tracking-[0.25em] text-cinnabar">
          studio · idle · waiting for creator
        </span>
      </div>

      {/* Middle editorial headline */}
      <div className="relative">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-5">
          § manifesto · 001
        </div>
        <h2 className="font-display font-bold text-[56px] leading-[0.98] tracking-[-0.01em] text-white mb-6 max-w-[16ch]">
          Ship the video.
          <br />
          <span className="text-cinnabar">Not the draft.</span>
        </h2>
        <p className="font-sans text-[15px] leading-[1.6] text-white/70 max-w-[44ch]">
          Ladder is a studio OS for founder-operators who make videos next to
          shipping product. Every prompt reads from what{" "}
          <span className="text-white">you</span> know — no hard-coded context,
          no cloned taste.
        </p>

        {/* Hairline dividers with mono labels — dev-tool density */}
        <div className="mt-10 grid grid-cols-3 gap-0 border-t border-hairline">
          <Stat label="models" value="7" hint="routed" />
          <Stat label="agents" value="12" hint="composable" />
          <Stat label="your data" value="yours" hint="rls · pgvector" />
        </div>
      </div>

      {/* Bottom footer — credit + date stamp */}
      <div className="relative flex items-end justify-between font-mono text-[10.5px] text-mist">
        <div>
          <div className="text-white/70">ladder.so</div>
          <div className="mt-0.5">built for the people shipping weekly.</div>
        </div>
        <div className="text-right">
          <div>{new Date().toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" }).toUpperCase()}</div>
          <div className="mt-0.5">no · 0001</div>
        </div>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="border-r last:border-r-0 border-hairline pt-4 pr-4 first:pl-0 pl-4">
      <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-mist mb-1.5">
        {label}
      </div>
      <div className="font-display text-[24px] leading-none text-white tabular-nums">
        {value}
      </div>
      <div className="mt-1.5 font-mono text-[10.5px] text-cinnabar/80">
        {hint}
      </div>
    </div>
  );
}
