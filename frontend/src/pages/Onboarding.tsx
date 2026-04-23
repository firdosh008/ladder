import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, ArrowLeft, Check } from "@phosphor-icons/react";
import { Button } from "../components/ui/Button";
import { Input, Textarea, FieldLabel } from "../components/ui/Input";
import { cn } from "../lib/cn";

const STEPS = [
  { id: 1, title: "Who are you?", hint: "identity" },
  { id: 2, title: "How do you sound?", hint: "voice" },
  { id: 3, title: "Pick your first brand.", hint: "brand" },
];

export default function OnboardingPage() {
  const [step, setStep] = useState(1);
  const navigate = useNavigate();

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
            "The studio uses this at call time. There's no hard-coded context anywhere — every prompt reads from what you write here."}
          {step === 2 &&
            "Tell us what makes you sound like you. Be specific. Examples of creators are fine — we map them to latent voice qualities, not mimicry."}
          {step === 3 &&
            "You can add more brands later. One now gets you into the studio in under a minute."}
        </p>

        {step === 1 && <StepOne />}
        {step === 2 && <StepTwo />}
        {step === 3 && <StepThree />}

        <div className="flex items-center justify-between mt-12 pt-6 border-t border-hairline">
          <Button
            variant="ghost"
            onClick={() => setStep((s) => Math.max(1, s - 1))}
            disabled={step === 1}
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
            <Button onClick={() => navigate("/make")}>
              <Check size={13} weight="bold" />
              Enter studio
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function StepOne() {
  return (
    <div className="space-y-5">
      <div>
        <FieldLabel htmlFor="name">Your name</FieldLabel>
        <Input id="name" placeholder="Alex Kim" autoFocus />
      </div>
      <div>
        <FieldLabel htmlFor="pos">What do you make and for whom?</FieldLabel>
        <Textarea
          id="pos"
          rows={3}
          placeholder="I build AI agents and ship videos about it for founder-operators at 1–20 person companies."
        />
      </div>
    </div>
  );
}

function StepTwo() {
  return (
    <div className="space-y-5">
      <div>
        <FieldLabel htmlFor="voice">How would a friend describe your voice?</FieldLabel>
        <Textarea
          id="voice"
          rows={2}
          placeholder="Dry, structural, low-ceremony. Concrete over clever."
        />
      </div>
      <div>
        <FieldLabel htmlFor="creators" hint="comma separated">
          Creators you sound closest to
        </FieldLabel>
        <Input id="creators" placeholder="Packy McCormick, Ben Thompson, Lenny Rachitsky" />
      </div>
      <div>
        <FieldLabel htmlFor="avoid">Never do this</FieldLabel>
        <Textarea
          id="avoid"
          rows={2}
          placeholder="Filler words. Over-capitalised Frameworks. Fake urgency."
        />
      </div>
    </div>
  );
}

function StepThree() {
  return (
    <div className="space-y-5">
      <div>
        <FieldLabel htmlFor="brand">Brand name</FieldLabel>
        <Input id="brand" placeholder="Ladder" autoFocus />
      </div>
      <div>
        <FieldLabel htmlFor="ctx">One-paragraph brand context</FieldLabel>
        <Textarea
          id="ctx"
          rows={3}
          placeholder="Ladder is a video production OS for founder-operators who ship videos next to shipping product. We value density, precision, and not-wasting-your-time."
        />
      </div>
      <div>
        <FieldLabel htmlFor="color" hint="hex">
          Brand accent
        </FieldLabel>
        <div className="flex items-center gap-3">
          <Input id="color" defaultValue="#E8442A" className="max-w-[160px] font-mono" />
          <div className="h-9 w-9 rounded-md bg-cinnabar" />
        </div>
      </div>
    </div>
  );
}
