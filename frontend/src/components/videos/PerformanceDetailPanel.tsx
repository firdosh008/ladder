import { useNavigate } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { X, ArrowRight, ChartLine } from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/cn";
import type { PublishedEntry } from "../../types/videos";

function fmt(n: number | null | undefined, suffix?: string): string {
  if (n == null) return "--";
  if (suffix === "%") return `${(n * 100).toFixed(1)}%`;
  if (suffix === "h") return `${n.toFixed(1)} hrs`;
  if (suffix === "s") return `${n.toFixed(0)}s`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

type Props = {
  video: PublishedEntry | null;
  open: boolean;
  onClose: () => void;
};

export function PerformanceDetailPanel({ video, open, onClose }: Props) {
  const navigate = useNavigate();

  if (!video) return null;
  const {
    video_id,
    thumbnail_url,
    title,
    published_at,
    views,
    ctr,
    avg_duration_s,
    watch_time_hrs,
    subscribers_gained,
    outlier_score,
    total_duration_s,
    what_worked,
  } = video;

  const dropOffPct =
    avg_duration_s != null && total_duration_s != null && total_duration_s > 0
      ? Math.round((1 - avg_duration_s / total_duration_s) * 100)
      : null;

  function handleMakeFollowUp() {
    navigate(`/make`, { state: { seedTopic: what_worked ?? title } });
    onClose();
  }

  return (
    <Dialog.Root open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            "fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px]",
            "data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-out",
          )}
        />
        <Dialog.Content
          className={cn(
            "fixed right-0 top-0 bottom-0 w-full sm:w-[520px] z-50",
            "bg-night border-l border-hairline overflow-y-auto focus:outline-none",
            "flex flex-col",
            "data-[state=open]:animate-slide-in-right data-[state=closed]:animate-slide-out-right",
          )}
          aria-describedby={undefined}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-hairline">
            <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist">
              performance · {video_id.slice(0, 8)}
            </span>
            <Dialog.Close asChild>
              <button
                type="button"
                onClick={onClose}
                className="text-mist hover:text-white transition-colors"
                aria-label="Close"
              >
                <X size={16} weight="bold" />
              </button>
            </Dialog.Close>
          </div>

          {/* Thumbnail + title */}
          {thumbnail_url ? (
            <div className="px-6 pt-5">
              <div className="rounded-lg overflow-hidden aspect-video bg-surface-input">
                <img
                  src={thumbnail_url}
                  alt={title}
                  className="w-full h-full object-cover"
                />
              </div>
            </div>
          ) : null}

          <div className="px-6 pt-4 pb-2">
            <Dialog.Title className="text-[20px] font-semibold text-white leading-tight">
              {title}
            </Dialog.Title>
            {published_at ? (
              <p className="text-[12px] text-mist mt-1 font-mono">
                Published {new Date(published_at).toLocaleDateString()}
              </p>
            ) : null}
          </div>

          {/* Core metrics grid */}
          <div className="px-6 py-4 border-t border-hairline">
            <Label>Core Metrics</Label>
            <div className="grid grid-cols-3 gap-3">
              <MetricBox label="Views" value={fmt(views)} />
              <MetricBox label="CTR" value={fmt(ctr, "%")} />
              <MetricBox label="Avg duration" value={fmt(avg_duration_s, "s")} />
              <MetricBox label="Watch time" value={fmt(watch_time_hrs, "h")} />
              <MetricBox label="Subs gained" value={fmt(subscribers_gained)} />
              <MetricBox
                label="Outlier"
                value={
                  outlier_score != null
                    ? `${outlier_score}x`
                    : "--"
                }
                highlight={
                  outlier_score != null && outlier_score > 3.0
                }
              />
            </div>
          </div>

          {/* Outlier score bar */}
          {outlier_score != null ? (
            <div className="px-6 py-3 border-t border-hairline">
              <Label>Performance vs Average</Label>
              <div className="flex items-center gap-3">
                <div className="flex-1 h-2 rounded-full bg-surface-input overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all",
                      outlier_score > 3.0 ? "bg-cinnabar" : "bg-mist",
                    )}
                    style={{ width: `${Math.min(outlier_score * 25, 100)}%` }}
                  />
                </div>
                <span
                  className={cn(
                    "text-[14px] font-bold tabular-nums",
                    outlier_score > 3.0 ? "text-cinnabar" : "text-mist",
                  )}
                >
                  {outlier_score}x
                </span>
              </div>
              <p className="text-[11px] text-mist mt-1.5">
                This video performed {outlier_score} times your channel average.
              </p>
            </div>
          ) : null}

          {/* 30-day views chart placeholder */}
          <div className="px-6 py-4 border-t border-hairline">
            <Label>Views over time</Label>
            <div className="rounded-lg border border-hairline bg-surface-input flex flex-col items-center justify-center py-8 px-4">
              <ChartLine size={22} weight="bold" className="text-mist/30 mb-2" />
              <p className="text-[11px] text-mist/60 text-center font-mono leading-[1.5]">
                Daily view breakdown available<br />when YouTube Data API is connected.
              </p>
            </div>
          </div>

          {/* Drop-off */}
          {dropOffPct != null ? (
            <div className="px-6 py-4 border-t border-hairline">
              <Label>Drop-off Signal</Label>
              <p className="text-[13px] text-white/80 leading-[1.5]">
                Viewers drop off by ~{dropOffPct}% through the video
                {dropOffPct > 50
                  ? " — consider tightening the framework section."
                  : " — retention is solid."}
              </p>
            </div>
          ) : null}

          {/* What worked */}
          {what_worked ? (
            <div className="px-6 py-4 border-t border-hairline">
              <Label>What worked</Label>
              <div className="rounded-lg border border-hairline bg-surface p-3.5">
                <p className="text-[12.5px] text-white/85 leading-[1.55] italic">
                  {what_worked}
                </p>
              </div>
            </div>
          ) : null}

          <div className="flex-1" />

          {/* Footer */}
          <div className="sticky bottom-0 bg-night border-t border-hairline px-6 py-4">
            <Button onClick={handleMakeFollowUp} className="w-full">
              Make a follow-up video
              <ArrowRight size={12} weight="bold" />
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-3">
      {children}
    </div>
  );
}

function MetricBox({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-md border border-hairline bg-surface px-3 py-2.5">
      <div className="text-[10px] font-mono uppercase tracking-[0.1em] text-mist/60 mb-0.5">
        {label}
      </div>
      <div
        className={cn(
          "text-[15px] font-semibold tabular-nums",
          highlight ? "text-cinnabar" : "text-white",
        )}
      >
        {value}
      </div>
    </div>
  );
}
