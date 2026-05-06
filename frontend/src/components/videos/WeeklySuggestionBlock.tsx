import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkle, ArrowRight, X, ArrowsClockwise } from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { api } from "../../lib/api";
import { runResearchStream } from "../../lib/agents";
import { useAuth } from "../../lib/auth";
import type { WeeklySuggestion } from "../../types/videos";
import type { AgentEvent } from "../../lib/agents";

type Props = {
  suggestion: WeeklySuggestion | null;
  loading: boolean;
  onSave: (ideas: WeeklySuggestion["ideas"]) => Promise<WeeklySuggestion>;
  onDismiss: () => void;
  onRefresh: () => void;
};

export function WeeklySuggestionBlock({
  suggestion,
  loading,
  onSave,
  onDismiss,
  onRefresh,
}: Props) {
  const navigate = useNavigate();
  const { profile } = useAuth();
  const [generating, setGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [genIdeas, setGenIdeas] = useState<WeeklySuggestion["ideas"] | null>(null);
  const [statusLine, setStatusLine] = useState<string | null>(null);

  // Dismissed
  if (suggestion?.dismissed) return null;

  // Loading
  if (loading) {
    return (
      <div className="mb-5 rounded-xl border border-hairline bg-surface p-4">
        <div className="flex items-center gap-2 mb-4">
          <Sparkle size={14} weight="fill" className="text-cinnabar/60" />
          <span className="text-[12px] font-semibold text-white/80">
            This week's best bets
          </span>
          <span className="font-mono text-[10.5px] text-mist">· Loading…</span>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-lg border border-hairline bg-surface-input p-3 animate-pulse">
              <div className="h-3 w-10 bg-white/[0.06] rounded mb-2" />
              <div className="h-4 w-full bg-white/[0.06] rounded mb-1.5" />
              <div className="h-3 w-3/4 bg-white/[0.06] rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  async function handleGenerate() {
    setGenerating(true);
    setGenError(null);
    setGenIdeas(null);
    setStatusLine("Searching…");

    const topic = profile?.positioning
      ? `Trending topics in ${profile.positioning} for our audience: ${profile.audience ?? "founders and operators"}`
      : "Trending topics for founders and operators right now";

    try {
      await runResearchStream({ topic, duration_min: 10 }, (ev: AgentEvent) => {
        if (ev.type === "agent_start") {
          setStatusLine(`${ev.agent} started…`);
        } else if (ev.type === "task_complete") {
          setStatusLine(`${ev.agent ?? "task"} complete`);
        } else if (ev.type === "ideas_ready") {
          const top3 = (ev.ideas ?? []).slice(0, 3).map((d) => ({
            title: d.title,
            rationale: d.rationale ?? null,
            opportunity_score: d.opportunity_score ?? null,
            why_now: d.why_now ?? null,
            idea_type: d.idea_type ?? null,
            suggested_tags: d.suggested_tags ?? [],
          }));
          setGenIdeas(top3);
        } else if (ev.type === "error") {
          setGenError(ev.message);
        }
      });

      setStatusLine(null);
    } catch (e) {
      setGenError(e instanceof Error ? e.message : "Research generation failed");
      setStatusLine(null);
    } finally {
      setGenerating(false);
    }
  }

  async function handleSaveGenerated() {
    if (!genIdeas) return;
    await onSave(genIdeas);
    setGenIdeas(null);
    onRefresh();
  }

  async function handleMakeVideo(draft: WeeklySuggestion["ideas"][number]) {
    try {
      const r = await api.post<{ idea: { id: string } }>("/ideas", {
        title: draft.title,
        rationale: draft.rationale,
        opportunity_score: draft.opportunity_score,
        idea_type: draft.idea_type,
        source_type: "research",
      });
      navigate(`/studio/${r.idea.id}`);
    } catch {
      // If creation fails, navigate to /make
      navigate("/make");
    }
  }

  // Generating state
  if (generating || genIdeas) {
    return (
      <div className="mb-5 rounded-xl border border-cinnabar/30 bg-cinnabar/[0.025] p-4">
        <div className="flex items-center gap-2 mb-4">
          <Sparkle size={14} weight="fill" className="text-cinnabar" />
          <span className="text-[12px] font-semibold text-white/80">
            {genIdeas ? "This week's best bets" : "Researching this week's best bets"}
          </span>
          {statusLine ? (
            <span className="font-mono text-[10.5px] text-mist">
              · {statusLine}
            </span>
          ) : null}
        </div>

        {genError ? (
          <p className="text-[12px] text-cinnabar mb-3">{genError}</p>
        ) : null}

        {genIdeas ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
              {genIdeas.map((draft, i) => (
                <div
                  key={i}
                  className="rounded-lg border border-hairline bg-surface p-3 flex flex-col"
                >
                  <div className="flex items-center justify-between mb-2">
                    <Badge
                      tone={
                        (draft.opportunity_score ?? 0) > 80
                          ? "cinnabar"
                          : "neutral"
                      }
                    >
                      {draft.opportunity_score ?? "--"}
                    </Badge>
                  </div>
                  <span className="text-[13px] text-white font-medium leading-tight mb-1.5 line-clamp-2">
                    {draft.title}
                  </span>
                  {draft.why_now ? (
                    <p className="text-[11px] text-mist/80 leading-[1.4] mb-3 flex-1">
                      {draft.why_now}
                    </p>
                  ) : null}
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => handleMakeVideo(draft)}
                    className="mt-auto"
                  >
                    Make this video
                    <ArrowRight size={10} weight="bold" />
                  </Button>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" onClick={handleSaveGenerated}>
                Save suggestions
              </Button>
              <button
                type="button"
                onClick={() => {
                  setGenIdeas(null);
                  setGenError(null);
                }}
                className="text-[11.5px] text-mist hover:text-white transition-colors"
              >
                Discard
              </button>
            </div>
          </>
        ) : (
          <div className="flex items-center justify-center py-6">
            <Sparkle size={16} weight="fill" className="text-cinnabar/50 animate-pulse" />
            <span className="text-[12px] text-mist ml-2 font-mono">Researching…</span>
          </div>
        )}
      </div>
    );
  }

  // Empty / no suggestion
  if (!suggestion) {
    return (
      <div className="mb-5 rounded-xl border border-hairline bg-surface p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Sparkle size={14} weight="fill" className="text-cinnabar/60" />
              <span className="text-[13px] font-semibold text-white/80">
                Get weekly AI-powered video suggestions
              </span>
            </div>
            <p className="text-[12px] text-mist/80 leading-[1.5] mb-3 max-w-lg">
              Ladder analyzes trends in your industry and suggests the top 3 video
              ideas worth making this week.
            </p>
            <Button size="sm" onClick={handleGenerate} disabled={generating}>
              <Sparkle size={12} weight="fill" />
              Generate ideas
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Populated
  const { ideas } = suggestion;
  const monday = new Date(suggestion.week_start + "T00:00:00");
  const weekLabel = monday.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });

  return (
    <div className="mb-5 rounded-xl border border-hairline bg-surface p-4">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkle size={14} weight="fill" className="text-cinnabar" />
          <span className="text-[12px] font-semibold text-white/80">
            This week's best bets
          </span>
          <span className="font-mono text-[10.5px] text-mist">
            · Updated {weekLabel}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="inline-flex items-center gap-1 text-[11px] text-mist hover:text-white transition-colors font-mono"
          >
            <ArrowsClockwise size={11} weight="bold" />
            refresh
          </button>
          <button
            type="button"
            onClick={onDismiss}
            className="inline-flex items-center gap-1 text-[11px] text-mist hover:text-white transition-colors"
          >
            <X size={11} weight="bold" />
            dismiss
          </button>
        </div>
      </div>

      <p className="text-[11px] text-mist/70 font-mono mb-3">
        Based on what people in your industry are talking about now
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {ideas.map((draft, i) => (
          <div
            key={i}
            className="rounded-lg border border-hairline bg-surface-input p-3 flex flex-col"
          >
            <div className="flex items-center justify-between mb-2">
              <Badge
                tone={(draft.opportunity_score ?? 0) > 80 ? "cinnabar" : "neutral"}
              >
                {draft.opportunity_score ?? "--"}
              </Badge>
            </div>
            <span className="text-[13px] text-white font-medium leading-tight mb-1.5 line-clamp-2">
              {draft.title}
            </span>
            {draft.why_now ? (
              <p className="text-[11px] text-mist/80 leading-[1.4] mb-3 flex-1">
                {draft.why_now}
              </p>
            ) : null}
            <Button
              size="sm"
              variant="secondary"
              onClick={() => handleMakeVideo(draft)}
              className="mt-auto"
            >
              Make this video
              <ArrowRight size={10} weight="bold" />
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
