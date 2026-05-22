import { cn } from "../../lib/cn";
import type { ChannelSummary } from "../../types/videos";

function fmt(n: number | null | undefined, suffix?: string): string {
  if (n == null) return "--";
  if (suffix === "%") return `${(n * 100).toFixed(1)}%`;
  if (suffix === "x") return `${n.toFixed(1)}x`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

const METRICS = [
  { key: "total_views_month" as const, label: "Views this month" },
  { key: "best_video_title" as const, label: "Best performing" },
  { key: "avg_ctr" as const, label: "Avg CTR" },
  { key: "avg_outlier_score" as const, label: "Avg outlier" },
];

export function ChannelSummaryStrip({
  summary,
}: {
  summary: ChannelSummary | null;
}) {
  return (
    <div className="mb-5 border-b border-hairline pb-4">
      <div className="flex flex-wrap gap-4">
        {METRICS.map(({ key, label }) => {
          const raw = summary?.[key as keyof ChannelSummary];
          let value: string;
          if (raw == null) {
            value = "--";
          } else if (key === "avg_ctr") {
            value = fmt(raw as number, "%");
          } else if (key === "avg_outlier_score") {
            value = fmt(raw as number, "x");
          } else if (key === "best_video_title") {
            value = raw as string;
          } else {
            value = fmt(raw as number);
          }

          const isOutlierHigh =
            key === "avg_outlier_score" &&
            typeof raw === "number" &&
            raw > 3.0;

          return (
            <div
              key={key}
              className="flex-1 min-w-[140px] rounded-lg border border-hairline bg-surface px-4 py-3"
            >
              <div className="text-[10.5px] font-mono uppercase tracking-[0.15em] text-mist mb-1">
                {label}
              </div>
              <div
                className={cn(
                  "text-[15px] font-semibold text-white leading-tight truncate",
                  isOutlierHigh && "text-cinnabar",
                )}
                title={key === "best_video_title" ? (value as string) : undefined}
              >
                {key === "best_video_title" && value !== "--"
                  ? (value as string).length > 40
                    ? (value as string).slice(0, 40) + "…"
                    : value
                  : value}
              </div>
            </div>
          );
        })}
      </div>
      {!summary ? (
        <p className="mt-2 text-[11px] text-mist font-mono">
          Connect YouTube in Settings to see metrics.
        </p>
      ) : null}
    </div>
  );
}
