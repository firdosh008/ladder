import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { LockKey, Warning } from "@phosphor-icons/react";
import { Button } from "../components/ui/Button";
import { Input, FieldLabel } from "../components/ui/Input";
import { useAuth } from "../lib/auth";
import { supabase } from "../lib/supabase";

export default function ResetPassword() {
  const { session, loading, recovering, onboarded } = useAuth();
  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (pw.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (pw !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      const { error } = await supabase.auth.updateUser({ password: pw });
      if (error) throw error;
      navigate(onboarded ? "/make" : "/onboarding", { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update password.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="min-h-[100dvh] bg-night flex items-center justify-center">
        <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-mist">
          · verifying ·
        </span>
      </div>
    );
  }

  if (!session && !recovering) {
    return (
      <div className="min-h-[100dvh] bg-night text-white flex items-center justify-center px-6">
        <div className="max-w-[380px] text-center">
          <h1 className="font-display text-[32px] text-white mb-3">Reset link expired.</h1>
          <p className="text-mist mb-6">Request a new password reset.</p>
          <Link to="/auth" className="text-cinnabar underline">
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-[100dvh] bg-night text-white flex items-center justify-center px-6">
      <form onSubmit={onSubmit} className="w-full max-w-[400px] space-y-4">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist">
          § reset · new password
        </div>
        <h1 className="font-display font-bold text-[36px] leading-[1.05] tracking-tight">
          Set a new password.
        </h1>
        <div>
          <FieldLabel htmlFor="pw" hint="min 8 chars">
            New password
          </FieldLabel>
          <div className="relative">
            <LockKey size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-mist" />
            <Input
              id="pw"
              type="password"
              required
              minLength={8}
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              className="pl-9"
              autoFocus
            />
          </div>
        </div>
        <div>
          <FieldLabel htmlFor="confirm">Confirm</FieldLabel>
          <div className="relative">
            <LockKey size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-mist" />
            <Input
              id="confirm"
              type="password"
              required
              minLength={8}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>
        {error ? (
          <div className="flex items-start gap-2 rounded-md border border-sienna/40 bg-sienna/10 px-3 py-2 text-[12.5px] text-white/90">
            <Warning size={13} weight="fill" className="text-sienna shrink-0 mt-0.5" />
            <span className="leading-[1.45]">{error}</span>
          </div>
        ) : null}
        <Button type="submit" size="lg" className="w-full" disabled={busy}>
          {busy ? "· updating ·" : "Update password"}
        </Button>
      </form>
    </div>
  );
}
