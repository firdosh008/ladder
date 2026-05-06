import { useState } from "react";
import { flushSync } from "react-dom";
import { useNavigate } from "react-router-dom";
import { ArrowRight, ArrowLeft, Check, Warning } from "@phosphor-icons/react";
import { Button } from "../components/ui/Button";
import { Input, Textarea, FieldLabel } from "../components/ui/Input";
import { cn } from "../lib/cn";
import { api, ApiError } from "../lib/api";
import { useAuth, type Profile } from "../lib/auth";

const STEPS = [
  { id: 1, title: "Who are you?", hint: "identity · ~60s" },
  { id: 2, title: "Who do you sound like?", hint: "voice · ~30s" },
  { id: 3, title: "Pick your first brand.", hint: "brand · ~45s" },
];

const CREATOR_PRESETS = [
  "Greg Eisenberg",
  "Nick Saraev",
  "Lenny Rachitsky",
  "David Perell",
];

type FormState = {
  positioning: string;
  audience: string;
  creator_seed: string;
};

const INITIAL: FormState = {
  positioning: "",
  audience: "",
  creator_seed: "",
};

// TODO: wire to /brands endpoint once built
type BrandState = {
  name: string;
  context: string;
  accent: string;
};

const INITIAL_BRAND: BrandState = {
  name: "",
  context: "",
  accent: "#E8442A",
};

export default function OnboardingPage() {
  const [step, setStep] = useState(1);
  const [form, setForm] = useState<FormState>(INITIAL);
  const [brand, setBrand] = useState<BrandState>(INITIAL_BRAND);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  const { setProfileAndOnboarded } = useAuth();

  async function submit() {
    const creator = form.creator_seed.trim();
    if (!form.positioning.trim() || !form.audience.trim()) {
      setError("Tell us what you do and who you help.");
      setStep(1);
      return;
    }
    if (!creator) {
      setError("Pick a creator or type one to seed your voice.");
      setStep(2);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<{ profile: Profile | null }>("/auth/onboard", {
        positioning: form.positioning,
        audience: form.audience,
        creators_followed: [creator],
      });
      // Commit the new profile to context SYNCHRONOUSLY so the next route guard
      // sees onboarded=true immediately. flushSync forces React to apply the
      // state update before navigate runs — without it, RequireAuth on /make
      // can render with stale onboarded=false and bounce back to /onboarding.
      const freshProfile: Profile =
        res.profile ?? {
          user_id: "",
          display_name: null,
          forwarding_alias: null,
          positioning: form.positioning,
          audience: form.audience,
          voice: null,
          creators_followed: [creator],
          things_to_avoid: null,
          onboarded_at: new Date().toISOString(),
          avatar_storage_path: null,
          theme: null,
          font_scale: null,
          youtube_connected: null,
          youtube_channel_name: null,
          youtube_subscriber_count: null,
          youtube_last_sync: null,
          notion_token: null,
          gamma_api_key: null,
          nano_banana_api_key: null,
        };
      flushSync(() => {
        setProfileAndOnboarded(freshProfile, true);
      });
      navigate("/make", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save profile.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-[100dvh] bg-night text-white">
      {/* Top strip — numbered steps */}
      <div className="border-b border-hairline">
        <div className="max-w-[880px] mx-auto px-6 py-4 flex items-center gap-2">
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
            /OS · onboarding
          </span>
          <div className="flex-1" />
          <div className="flex items-center gap-1.5">
            {STEPS.map((s) => (
              <div
                key={s.id}
                className={cn(
                  "h-1.5 w-8 rounded-full transition-colors",
                  s.id < step
                    ? "bg-cinnabar"
                    : s.id === step
                      ? "bg-cinnabar/60"
                      : "bg-white/10",
                )}
              />
            ))}
            <span className="font-mono text-[10.5px] text-mist ml-2 tabular-nums">
              {step}/3
            </span>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="max-w-[720px] mx-auto px-6 py-16">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-4">
          § step {step.toString().padStart(2, "0")} · {STEPS[step - 1].hint}
        </div>
        <h1 className="font-display font-bold text-[44px] leading-[1.05] tracking-tight text-white mb-3">
          {STEPS[step - 1].title}
        </h1>
        <p className="text-[15px] text-white/65 leading-[1.55] mb-10 max-w-[54ch]">
          {step === 1 &&
            "Two fields map straight to your profile: what you do (positioning) and who you help (audience). The studio reads both at call time."}
          {step === 2 &&
            "Which creator's style do you want to sound like? One name seeds your voice profile; the system learns more as you edit scripts."}
          {step === 3 &&
            "You can add more brands later. One now gets you into the studio in under a minute."}
        </p>

        {step === 1 && <StepOne form={form} setForm={setForm} />}
        {step === 2 && <StepTwo form={form} setForm={setForm} />}
        {step === 3 && <StepThree brand={brand} setBrand={setBrand} />}

        {error ? (
          <div className="mt-4 flex items-start gap-2 rounded-md border border-sienna/40 bg-sienna/10 px-3 py-2 text-[12.5px] text-white/90">
            <Warning
              size={13}
              weight="fill"
              className="text-sienna shrink-0 mt-0.5"
            />
            <span className="leading-[1.45]">{error}</span>
          </div>
        ) : null}

        <div className="flex items-center justify-between mt-12 pt-6 border-t border-hairline">
          <Button
            variant="ghost"
            onClick={() => setStep((s) => Math.max(1, s - 1))}
            disabled={step === 1 || busy}
          >
            <ArrowLeft size={13} weight="bold" />
            Back
          </Button>
          <div className="font-mono text-[10.5px] text-mist uppercase tracking-[0.2em]">
            ⌘↵ to continue
          </div>
          {step < 3 ? (
            <Button onClick={() => setStep((s) => s + 1)}>
              Continue
              <ArrowRight size={13} weight="bold" />
            </Button>
          ) : (
            <Button onClick={submit} disabled={busy}>
              <Check size={13} weight="bold" />
              {busy ? "· saving ·" : "Enter studio"}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

type StepProps = {
  form: FormState;
  setForm: React.Dispatch<React.SetStateAction<FormState>>;
};

function StepOne({ form, setForm }: StepProps) {
  return (
    <div className="space-y-5">
      <div>
        <FieldLabel htmlFor="pos">What do you do?</FieldLabel>
        <Textarea
          id="pos"
          rows={3}
          autoFocus
          placeholder="e.g. I teach solo founders how to ship weekly video without a team."
          value={form.positioning}
          onChange={(e) => setForm({ ...form, positioning: e.target.value })}
        />
      </div>
      <div>
        <FieldLabel htmlFor="aud">Who do you help?</FieldLabel>
        <Textarea
          id="aud"
          rows={3}
          placeholder="e.g. Bootstrapped B2B founders at 0–20 person companies."
          value={form.audience}
          onChange={(e) => setForm({ ...form, audience: e.target.value })}
        />
      </div>
    </div>
  );
}

function StepTwo({ form, setForm }: StepProps) {
  const selected = form.creator_seed.trim();
  return (
    <div className="space-y-4">
      <FieldLabel htmlFor="creator">
        Which creator's style do you want to sound like?
      </FieldLabel>
      <div className="flex flex-wrap gap-2">
        {CREATOR_PRESETS.map((name) => {
          const active = selected.toLowerCase() === name.toLowerCase();
          return (
            <button
              key={name}
              type="button"
              onClick={() => setForm({ ...form, creator_seed: name })}
              className={cn(
                "h-9 px-4 rounded-full text-[13px] font-sans font-medium",
                "border transition-colors",
                active
                  ? "border-cinnabar bg-cinnabar/15 text-white"
                  : "border-white/15 bg-white/5 text-white/80 hover:border-white/30 hover:bg-white/10",
              )}
            >
              {name}
            </button>
          );
        })}
      </div>
      <Input
        id="creator"
        placeholder="Or type any creator name"
        value={form.creator_seed}
        onChange={(e) => setForm({ ...form, creator_seed: e.target.value })}
      />
    </div>
  );
}

type BrandStepProps = {
  brand: BrandState;
  setBrand: React.Dispatch<React.SetStateAction<BrandState>>;
};

function StepThree({ brand, setBrand }: BrandStepProps) {
  return (
    <div className="space-y-5">
      <div>
        <FieldLabel htmlFor="brand">Brand name</FieldLabel>
        <Input
          id="brand"
          placeholder="e.g. Ladder"
          autoFocus
          value={brand.name}
          onChange={(e) => setBrand({ ...brand, name: e.target.value })}
        />
      </div>
      <div>
        <FieldLabel htmlFor="ctx">One-paragraph brand context</FieldLabel>
        <Textarea
          id="ctx"
          rows={3}
          placeholder="e.g. A video production OS for founder-operators who ship videos next to shipping product."
          value={brand.context}
          onChange={(e) => setBrand({ ...brand, context: e.target.value })}
        />
      </div>
      <div>
        <FieldLabel htmlFor="color" hint="hex">
          Brand accent
        </FieldLabel>
        <div className="flex items-center gap-3">
          <Input
            id="color"
            className="max-w-[160px] font-mono"
            value={brand.accent}
            onChange={(e) => setBrand({ ...brand, accent: e.target.value })}
          />
          <div
            className="h-9 w-9 rounded-md"
            style={{ backgroundColor: brand.accent || "#E8442A" }}
          />
        </div>
      </div>
    </div>
  );
}
