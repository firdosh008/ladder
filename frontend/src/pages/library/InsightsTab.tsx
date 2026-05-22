import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Lightbulb, ArrowRight, Sparkle } from "@phosphor-icons/react";
import { useInsights, type Insight } from "../../lib/useKnowledge";
import { cn } from "../../lib/cn";

const SIGNAL_LABELS: Record<string, string> = {
  trend_shift: "Trend shift",
  positioning_gap: "Positioning gap",
  audience_signal: "Audience signal",
};

function timeAgo(dateStr: string): string {
  const ms = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default function InsightsTab() {
  const { insights, loading, error, refresh, markRead, generate } =
    useInsights();
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function handleGenerate() {
    setGenerating(true);
    setGenError(null);
    try {
      await generate();
    } catch (e: any) {
      setGenError(e?.message ?? "Failed to generate insights");
    } finally {
      setGenerating(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-3 max-w-[1100px]">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-24 rounded-xl bg-white/[0.04] animate-pulse"
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-hairline bg-surface p-8 text-center max-w-[1100px]">
        <p className="text-[13px] text-sienna mb-2">{error}</p>
        <button
          onClick={refresh}
          className="text-[12px] text-cinnabar hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (insights.length === 0) {
    return (
      <div className="rounded-xl border border-hairline bg-surface p-10 text-center max-w-[1100px]">
        <Lightbulb size={18} className="text-cinnabar mx-auto mb-2" />
        <p className="text-[13.5px] text-white mb-1">No insights yet.</p>
        <p className="text-[12px] text-mist font-mono leading-[1.6] max-w-[52ch] mx-auto mb-4">
          Synthesised signals from the research agent appear here once the
          system has analyzed your niche.
        </p>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="inline-flex items-center gap-1.5 h-9 px-4 rounded-md bg-cinnabar hover:bg-cinnabar-hover text-white text-[13px] font-medium transition-colors disabled:opacity-50"
        >
          <Sparkle size={13} weight="bold" />
          {generating ? "Generating…" : "Generate insights now"}
        </button>
        {genError && (
          <p className="text-[12px] text-sienna mt-2">{genError}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3 max-w-[1100px]">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist">
          {insights.length} signal{insights.length !== 1 ? "s" : ""} · last 7 days
        </span>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="inline-flex items-center gap-1 h-7 px-2.5 rounded-md bg-white/[0.04] border border-hairline text-[11.5px] text-mist hover:text-white hover:bg-white/[0.08] transition-colors disabled:opacity-40"
        >
          <Sparkle size={11} weight="bold" />
          {generating ? "Generating…" : "Generate more"}
        </button>
      </div>
      {genError && (
        <p className="text-[12px] text-sienna">{genError}</p>
      )}
      {insights.map((insight) => (
        <InsightCard
          key={insight.id}
          insight={insight}
          onMakeVideo={() => {
            markRead(insight.id);
            navigate(
              `/make?topic=${encodeURIComponent(insight.title)}`,
            );
          }}
        />
      ))}
    </div>
  );
}

function InsightCard({
  insight,
  onMakeVideo,
}: {
  insight: Insight;
  onMakeVideo: () => void;
}) {
  const signalLabel =
    insight.signal_type && SIGNAL_LABELS[insight.signal_type]
      ? SIGNAL_LABELS[insight.signal_type]
      : insight.signal_type ?? "Signal";

  return (
    <div
      className={cn(
        "rounded-xl border border-hairline bg-surface p-5 transition-colors",
        !insight.read && "border-l-[3px] border-l-cinnabar",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <h3 className="text-[14px] text-white font-medium leading-snug">
              {insight.title}
            </h3>
            {!insight.read && (
              <span className="w-1.5 h-1.5 rounded-full bg-cinnabar shrink-0" />
            )}
          </div>
          {insight.body && (
            <p className="text-[13px] text-white/60 leading-relaxed mb-2">
              {insight.body}
            </p>
          )}
          <div className="flex items-center gap-3">
            <span className="font-mono text-[10.5px] text-mist bg-white/[0.06] rounded px-1.5 py-0.5">
              {signalLabel}
            </span>
            {insight.source_ref && (
              <span className="font-mono text-[11px] text-mist truncate">
                {insight.source_ref}
              </span>
            )}
            <span className="font-mono text-[10.5px] text-mist">
              {insight.created_at ? timeAgo(insight.created_at) : ""}
            </span>
          </div>
        </div>
        <button
          onClick={onMakeVideo}
          className="inline-flex items-center gap-1.5 shrink-0 h-8 px-3 rounded-md bg-white/[0.06] border border-hairline hover:bg-white/[0.1] transition-colors text-[12px] text-white font-medium"
        >
          Make a video about this
          <ArrowRight size={11} weight="bold" />
        </button>
      </div>
    </div>
  );
}
