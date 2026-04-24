import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import {
  X,
  ArrowRight,
  MagnifyingGlass,
  Gauge,
  Sparkle,
  CheckCircle,
  Warning,
} from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { cn } from "../../lib/cn";
import {
  runResearchStream,
  type AgentEvent,
  type IdeaDraft,
  type ResearchSetup,
} from "../../lib/agents";
import { api, ApiError } from "../../lib/api";

type TimelineEntry = {
  id: number;
  label: string;
  detail?: string;
  kind: "agent" | "tool" | "task" | "info" | "error";
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  setup: ResearchSetup | null;
  onIdeaSaved?: () => void;
};

const AGENT_LABELS: Record<string, string> = {
  search_agent: "Trend researcher",
  trend_scorer: "Outlier scorer",
  idea_formulator: "Idea architect",
};

function labelFor(agent?: string | null): string {
  if (!agent) return "Agent";
  return AGENT_LABELS[agent] ?? agent;
}

export function ResearchStreamDrawer({ open, onOpenChange, setup, onIdeaSaved }: Props) {
  const navigate = useNavigate();
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [drafts, setDrafts] = useState<IdeaDraft[]>([]);
  const [status, setStatus] = useState<"idle" | "running" | "ready" | "failed">("idle");
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState<number | null>(null);
  const [savingIdx, setSavingIdx] = useState<number | null>(null);
  const keyRef = useRef(0);
  const hasStartedRef = useRef(false);

  useEffect(() => {
    if (!open || !setup) {
      hasStartedRef.current = false;
      return;
    }
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;

    setTimeline([]);
    setDrafts([]);
    setStatus("running");
    setError(null);
    setCost(null);
    setSavingIdx(null);

    const push = (entry: Omit<TimelineEntry, "id">) => {
      keyRef.current += 1;
      setTimeline((prev) => [...prev, { id: keyRef.current, ...entry }]);
    };

    const handle = (ev: AgentEvent) => {
      switch (ev.type) {
        case "agent_start":
          push({ kind: "agent", label: `${labelFor(ev.agent)} online` });
          break;
        case "tool_call":
          push({
            kind: "tool",
            label: `${labelFor(ev.agent)} → ${ev.tool}`,
            detail: ev.query,
          });
          break;
        case "tool_result":
          push({
            kind: "tool",
            label: `${labelFor(ev.agent)} ← results`,
            detail: ev.preview,
          });
          break;
        case "task_complete":
          push({
            kind: "task",
            label: `${labelFor(ev.agent)} wrapped`,
            detail: ev.preview,
          });
          break;
        case "ideas_ready":
          setDrafts(ev.ideas);
          push({
            kind: "info",
            label: `${ev.ideas.length} ideas ready — pick one to save`,
          });
          break;
        case "error":
          push({ kind: "error", label: "error", detail: ev.message });
          break;
        default:
          break;
      }
    };

    runResearchStream(setup, handle)
      .then((result) => {
        setCost(result.cost_usd);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("failed");
      });
  }, [open, setup]);

  async function pickDraft(index: number) {
    if (savingIdx !== null) return;
    const draft = drafts[index];
    if (!draft) return;
    setSavingIdx(index);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        title: draft.title,
        status: "new",
        source_type: "research",
      };
      if (setup?.topic) payload.source_content = setup.topic;
      if (draft.rationale) payload.rationale = draft.rationale;
      if (draft.idea_type) payload.idea_type = draft.idea_type;
      if (typeof draft.opportunity_score === "number") {
        payload.opportunity_score = draft.opportunity_score;
      }
      const res = await api.post<{ idea: { id: string } }>("/ideas", payload);
      onIdeaSaved?.();
      onOpenChange(false);
      navigate(`/studio/${res.idea.id}`);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "Could not save idea",
      );
      setSavingIdx(null);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            "fixed inset-0 z-40 bg-black/60 backdrop-blur-[3px]",
            "data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-out",
          )}
        />
        <Dialog.Content
          aria-describedby={undefined}
          className={cn(
            "fixed right-0 top-0 bottom-0 z-50 w-[min(560px,100vw)]",
            "bg-ink border-l border-hairline shadow-diffuse",
            "flex flex-col focus:outline-none",
            "data-[state=open]:animate-slide-in-right data-[state=closed]:animate-slide-out-right",
          )}
        >
          <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-hairline">
            <div className="min-w-0">
              <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-1.5 flex items-center gap-2">
                <span>§ research crew</span>
                <StatusBadge status={status} />
              </div>
              <Dialog.Title className="font-display text-[20px] leading-[1.15] text-white truncate">
                {setup?.topic ?? "Research"}
              </Dialog.Title>
              <p className="mt-1 text-[12.5px] text-mist">
                3 agents searching, scoring, and drafting. Pick one to continue.
              </p>
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close"
                className="text-mist hover:text-white transition-colors -mt-1 -mr-1 p-1"
              >
                <X size={16} weight="bold" />
              </button>
            </Dialog.Close>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
            <section>
              <SectionHeading icon={Gauge} label="Agent timeline" />
              <ol className="mt-3 space-y-2">
                {timeline.length === 0 ? (
                  <li className="font-mono text-[11.5px] text-mist">
                    · warming up agents ·
                  </li>
                ) : (
                  timeline.map((entry) => (
                    <TimelineRow key={entry.id} entry={entry} />
                  ))
                )}
              </ol>
            </section>

            <section>
              <SectionHeading
                icon={Sparkle}
                label={
                  drafts.length > 0
                    ? `Drafts · ${drafts.length}`
                    : "Drafts"
                }
              />
              <div className="mt-3 space-y-2">
                {drafts.length === 0 ? (
                  <p className="font-mono text-[11.5px] text-mist">
                    · ideas land here once the crew wraps ·
                  </p>
                ) : (
                  drafts.map((draft, i) => (
                    <DraftCard
                      key={`${draft.title}-${i}`}
                      draft={draft}
                      loading={savingIdx === i}
                      disabled={savingIdx !== null && savingIdx !== i}
                      onPick={() => pickDraft(i)}
                    />
                  ))
                )}
              </div>
            </section>

            {error ? (
              <div className="rounded-md border border-sienna/40 bg-sienna/[0.08] p-3 text-[12.5px] text-white/90 flex gap-2">
                <Warning
                  size={14}
                  weight="fill"
                  className="text-sienna shrink-0 mt-0.5"
                />
                <span>{error}</span>
              </div>
            ) : null}
          </div>

          <div className="flex items-center justify-between gap-2 px-6 py-4 border-t border-hairline">
            <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
              {status === "ready" && cost !== null
                ? `${drafts.length} ready · $${cost.toFixed(4)}`
                : status === "running"
                  ? "streaming"
                  : status === "failed"
                    ? "failed"
                    : "idle"}
            </span>
            <Dialog.Close asChild>
              <Button variant="ghost" size="sm">
                {status === "ready" ? "Close" : "Dismiss"}
              </Button>
            </Dialog.Close>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function StatusBadge({ status }: { status: "idle" | "running" | "ready" | "failed" }) {
  if (status === "running") {
    return (
      <Badge tone="cinnabar">
        <MagnifyingGlass size={10} weight="bold" />
        live
      </Badge>
    );
  }
  if (status === "ready") {
    return (
      <Badge tone="neutral">
        <CheckCircle size={10} weight="fill" />
        ready
      </Badge>
    );
  }
  if (status === "failed") {
    return (
      <Badge tone="warn">
        <Warning size={10} weight="fill" />
        failed
      </Badge>
    );
  }
  return null;
}

function SectionHeading({
  icon: Icon,
  label,
}: {
  icon: React.ElementType;
  label: string;
}) {
  return (
    <div className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist">
      <Icon size={11} weight="bold" />
      {label}
    </div>
  );
}

function TimelineRow({ entry }: { entry: TimelineEntry }) {
  const dotColor =
    entry.kind === "error"
      ? "bg-sienna"
      : entry.kind === "task"
        ? "bg-cinnabar"
        : entry.kind === "tool"
          ? "bg-white/60"
          : "bg-mist";
  return (
    <li className="flex gap-3 text-[12.5px] leading-[1.45]">
      <span
        className={cn("mt-[6px] h-1.5 w-1.5 rounded-full shrink-0", dotColor)}
      />
      <div className="min-w-0 flex-1">
        <div className="text-white/90">{entry.label}</div>
        {entry.detail ? (
          <div className="text-mist text-[11.5px] mt-0.5 truncate">
            {entry.detail}
          </div>
        ) : null}
      </div>
    </li>
  );
}

function DraftCard({
  draft,
  loading,
  disabled,
  onPick,
}: {
  draft: IdeaDraft;
  loading: boolean;
  disabled: boolean;
  onPick: () => void;
}) {
  const tags = draft.suggested_tags ?? [];
  return (
    <button
      type="button"
      onClick={onPick}
      disabled={disabled || loading}
      className={cn(
        "w-full text-left rounded-md border bg-surface/70 p-3 transition-colors",
        "border-hairline hover:border-cinnabar/50",
        "disabled:opacity-60 disabled:cursor-not-allowed",
      )}
    >
      <div className="flex items-start gap-2.5">
        {typeof draft.opportunity_score === "number" ? (
          <span
            className={cn(
              "font-mono text-[11px] shrink-0 tabular-nums pt-[2px]",
              draft.opportunity_score >= 80 ? "text-cinnabar" : "text-mist",
            )}
          >
            {draft.opportunity_score}
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <div className="text-[13.5px] text-white leading-[1.35] flex-1">
              {draft.title}
            </div>
            {typeof draft.outlier_score === "number" ? (
              <Badge tone="muted" className="shrink-0">
                {draft.outlier_score.toFixed(1)}× outlier
              </Badge>
            ) : null}
          </div>
          {draft.rationale ? (
            <div className="text-[11.5px] text-mist mt-1 leading-[1.5]">
              {draft.rationale}
            </div>
          ) : null}
          {draft.why_now ? (
            <div className="text-[11.5px] text-white/70 mt-1.5 italic leading-[1.5]">
              {draft.why_now}
            </div>
          ) : null}
          {tags.length > 0 ? (
            <div className="flex flex-wrap gap-1 mt-2">
              {tags.map((t) => (
                <span
                  key={t}
                  className="font-mono text-[10px] text-mist border border-hairline rounded px-1.5 py-0.5"
                >
                  {t}
                </span>
              ))}
            </div>
          ) : null}
          <div className="mt-2.5 flex items-center gap-1 font-mono text-[10.5px] uppercase tracking-[0.18em] text-cinnabar/80">
            {loading ? (
              <span>· saving ·</span>
            ) : (
              <>
                <span>save &amp; open in studio</span>
                <ArrowRight size={10} weight="bold" />
              </>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}
