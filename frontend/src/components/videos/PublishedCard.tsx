import { cn } from "../../lib/cn";
import type { PublishedEntry } from "../../types/videos";

function fmt(n: number | null | undefined, suffix?: string): string {
  if (n == null) return "--";
  if (suffix === "%") return `${(n * 100).toFixed(1)}%`;
  if (suffix === "hrs") return `${n.toFixed(1)}h`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

type Props = {
  entry: PublishedEntry;
  onClick: (entry: PublishedEntry) => void;
};

export function PublishedCard({ entry, onClick }: Props) {
  return (
    <div
      onClick={() => onClick(entry)}
      className={cn(
        "group relative rounded-lg border border-hairline bg-surface px-3.5 py-3 cursor-pointer",
        "transition-all duration-200",
        "hover:border-hairline-strong hover:-translate-y-[1px]",
        "hover:shadow-[0_4px_18px_-10px_rgba(0,0,0,0.6)]",
      )}
    >
      {/* Thumbnail */}
      {entry.thumbnail_url ? (
        <div className="mb-3 rounded-md overflow-hidden aspect-video bg-surface-input">
          <img
            src={entry.thumbnail_url}
            alt={entry.title}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        </div>
      ) : null}

      {/* Title */}
      <span className="text-[13.5px] text-white leading-[1.35] font-medium line-clamp-2 block mb-2.5">
        {entry.title}
      </span>

      {/* Metrics row */}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 mb-2.5">
        <Metric label="Views" value={fmt(entry.views)} />
        <Metric label="CTR" value={fmt(entry.ctr, "%")} />
        <Metric label="Watch time" value={fmt(entry.watch_time_hrs, "hrs")} />
        <Metric
          label="Outlier"
          value={entry.outlier_score != null ? `${entry.outlier_score}x` : "--"}
          highlight={entry.outlier_score != null && entry.outlier_score > 3.0}
        />
      </div>

      {/* What worked insight */}
      {entry.what_worked ? (
        <div className="border-t border-hairline pt-2 mt-2">
          <p className="text-[11px] text-mist/80 leading-[1.4] line-clamp-2 italic">
            {entry.what_worked}
          </p>
        </div>
      ) : null}
    </div>
  );
}

function Metric({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] font-mono uppercase tracking-[0.1em] text-mist/70 leading-none mb-0.5">
        {label}
      </div>
      <div
        className={cn(
          "text-[12.5px] font-semibold tabular-nums leading-tight",
          highlight ? "text-cinnabar" : "text-white/90",
        )}
      >
        {value}
      </div>
    </div>
  );
}
