import { cn } from "../../lib/cn";

type Tone = "cinnabar" | "neutral" | "muted" | "warn";

const tones: Record<Tone, string> = {
  cinnabar: "bg-cinnabar text-white",
  neutral: "bg-white/[0.08] text-white border border-hairline",
  muted: "bg-transparent text-mist border border-hairline",
  warn: "bg-sienna/20 text-sienna border border-sienna/40",
};

export function Badge({
  children,
  tone = "neutral",
  mono = true,
  className,
}: {
  children: React.ReactNode;
  tone?: Tone;
  mono?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 h-[18px]",
        "text-[10.5px] font-semibold tabular-nums",
        mono ? "font-mono" : "font-sans",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
