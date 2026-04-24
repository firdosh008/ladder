import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowsClockwise,
  CheckCircle,
  FileText,
  Lightning,
  Sparkle,
  Warning,
} from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { cn } from "../../lib/cn";
import {
  runExtractStream,
  type AgentEvent,
  type ExtractedVideo,
} from "../../lib/agents";

/**
 * Inline content_extract panel shown on /make Option 3.
 *
 * Mirrors ResearchRunPanel UX shape (header strip + agents + activity)
 * but smaller: only 2 agents, only 1 idea drops out the end, and on
 * `persisted` we navigate straight to /studio/:idea_id.
 */

type Setup = {
  source_content: string;
  source_url?: string | null;
};

type Props = {
  setup: Setup | null;
  onStartOver: () => void;
  onIdeasChanged?: () => void;
};

type AgentKey = "analyzer" | "extractor";

type AgentRuntime = {
  key: AgentKey;
  label: string;
  status: "idle" | "active" | "done";
  streamingText: string;
};

const AGENT_ORDER: AgentKey[] = ["analyzer", "extractor"];

const AGENT_LABELS: Record<AgentKey, string> = {
  analyzer: "Source analyzer",
  extractor: "Source extractor",
};

const AGENT_HINT: Record<AgentKey, string> = {
  analyzer: "deciding title, type, runtime + key beats",
  extractor: "drafting script + outline grounded in your source",
};

function initialRuntime(): Record<AgentKey, AgentRuntime> {
  return AGENT_ORDER.reduce(
    (acc, key) => {
      acc[key] = {
        key,
        label: AGENT_LABELS[key],
        status: "idle",
        streamingText: "",
      };
      return acc;
    },
    {} as Record<AgentKey, AgentRuntime>,
  );
}

type TimelineKind = "agent" | "task" | "info" | "error";
type TimelineEntry = {
  id: number;
  kind: TimelineKind;
  agent?: string | null;
  label: string;
  detail?: string;
};

type Status = "running" | "ready" | "failed";

export function ContentExtractPanel({ setup, onStartOver, onIdeasChanged }: Props) {
  const navigate = useNavigate();
  const [runtime, setRuntime] = useState<Record<AgentKey, AgentRuntime>>(
    initialRuntime,
  );
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [extracted, setExtracted] = useState<ExtractedVideo | null>(null);
  const [status, setStatus] = useState<Status>("running");
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState<number | null>(null);
  const [persistedIdeaId, setPersistedIdeaId] = useState<string | null>(null);
  const [autoNavigated, setAutoNavigated] = useState(false);
  const keyRef = useRef(0);

  useEffect(() => {
    if (!setup) return;

    let cancelled = false;

    setRuntime(initialRuntime());
    setTimeline([]);
    setExtracted(null);
    setStatus("running");
    setError(null);
    setCost(null);
    setPersistedIdeaId(null);
    setAutoNavigated(false);

    const push = (entry: Omit<TimelineEntry, "id">) => {
      if (cancelled) return;
      keyRef.current += 1;
      setTimeline((prev) => [...prev, { id: keyRef.current, ...entry }]);
    };

    const handle = (ev: AgentEvent) => {
      if (cancelled) return;
      switch (ev.type) {
        case "agent_start": {
          const key = ev.agent as AgentKey;
          setRuntime((prev) => {
            const next = { ...prev };
            for (const k of AGENT_ORDER) {
              if (next[k].status === "active") next[k] = { ...next[k], status: "done" };
            }
            if (next[key]) next[key] = { ...next[key], status: "active" };
            return next;
          });
          push({ kind: "agent", agent: ev.agent, label: `${labelFor(ev.agent)} online` });
          break;
        }
        case "text_delta": {
          const key = ev.agent as AgentKey;
          setRuntime((prev) =>
            prev[key]
              ? {
                  ...prev,
                  [key]: {
                    ...prev[key],
                    streamingText: (prev[key].streamingText + ev.content).slice(-1400),
                  },
                }
              : prev,
          );
          break;
        }
        case "task_complete": {
          const key = (ev.agent ?? "") as AgentKey;
          setRuntime((prev) =>
            prev[key] ? { ...prev, [key]: { ...prev[key], status: "done" } } : prev,
          );
          push({
            kind: "task",
            agent: ev.agent,
            label: `${labelFor(ev.agent)} wrapped`,
            detail: ev.preview,
          });
          break;
        }
        case "extract_ready":
          setExtracted(ev.extracted);
          push({
            kind: "info",
            label: `extracted "${ev.extracted.title}" · ${ev.extracted.derived_duration_min} min`,
          });
          break;
        case "persisted": {
          if (ev.idea_id) {
            setPersistedIdeaId(ev.idea_id);
            push({
              kind: "info",
              label: "saved to /videos · opening studio…",
            });
          }
          break;
        }
        case "usage":
          setCost(ev.token_usage.cost_usd);
          break;
        case "error":
          push({ kind: "error", label: "error", detail: ev.message });
          break;
        default:
          break;
      }
    };

    runExtractStream(setup, handle)
      .then((result) => {
        if (cancelled) return;
        setCost(result.cost_usd);
        setStatus("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setStatus("failed");
      });

    return () => {
      cancelled = true;
    };
  }, [setup]);

  // Auto-navigate to studio once persisted (~600ms grace so the user sees
  // the success state instead of a hard redirect).
  useEffect(() => {
    if (!persistedIdeaId || autoNavigated) return;
    const t = window.setTimeout(() => {
      setAutoNavigated(true);
      onIdeasChanged?.();
      navigate(`/studio/${persistedIdeaId}`);
    }, 700);
    return () => window.clearTimeout(t);
  }, [persistedIdeaId, autoNavigated, navigate, onIdeasChanged]);

  const activeAgent = AGENT_ORDER.find((k) => runtime[k].status === "active") ?? null;

  return (
    <section
      aria-label="Content extract run"
      className="mt-8 rounded-xl border border-hairline bg-surface/70 overflow-hidden"
    >
      <div className="px-6 pt-5 pb-4 border-b border-hairline flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-1.5 flex items-center gap-2">
            <span>§ content extract</span>
            <StatusBadge status={status} />
          </div>
          <h2 className="font-display text-[22px] leading-[1.15] text-white">
            {extracted?.title ?? "Extracting your source"}
          </h2>
          <p className="mt-1 text-[12.5px] text-mist">
            {activeAgent
              ? `${AGENT_LABELS[activeAgent]} · ${AGENT_HINT[activeAgent]}`
              : status === "ready"
                ? extracted
                  ? `${extracted.script.sections.length} sections · ${extracted.outline.items.length} outline rows${
                      cost !== null ? ` · $${cost.toFixed(4)}` : ""
                    }`
                  : "ready"
                : status === "failed"
                  ? "Extraction failed"
                  : "Warming up 2 agents"}
          </p>
        </div>
        {status !== "running" ? (
          <Button variant="ghost" size="sm" onClick={onStartOver}>
            <ArrowsClockwise size={12} weight="bold" />
            Try another source
          </Button>
        ) : null}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-0">
        <div className="p-6 lg:border-r lg:border-hairline space-y-6 min-w-0">
          <section>
            <SectionHeading icon={Sparkle} label="Extracted video" />
            <div className="mt-3">
              {extracted ? (
                <ExtractedSummary extracted={extracted} />
              ) : (
                <p className="font-mono text-[11.5px] text-mist">
                  · the video lands here once the extractor wraps ·
                </p>
              )}
            </div>
          </section>

          <section>
            <SectionHeading icon={FileText} label="Agents" />
            <div className="mt-3 space-y-2">
              {AGENT_ORDER.map((key) => (
                <AgentRow key={key} runtime={runtime[key]} />
              ))}
            </div>
          </section>

          {timeline.length > 0 ? (
            <section>
              <SectionHeading icon={Lightning} label="Activity" />
              <ol className="mt-3 space-y-2">
                {timeline.map((entry) => (
                  <TimelineRow key={entry.id} entry={entry} />
                ))}
              </ol>
            </section>
          ) : null}

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

        <aside className="p-6 bg-black/20 lg:bg-transparent">
          <SectionHeading icon={FileText} label="Source" />
          <p className="mt-3 text-[12px] text-mist leading-[1.55] line-clamp-[12] whitespace-pre-wrap">
            {setup?.source_content?.slice(0, 1400) ?? ""}
            {setup && setup.source_content.length > 1400 ? "…" : ""}
          </p>
          {persistedIdeaId ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate(`/studio/${persistedIdeaId}`)}
              className="w-full mt-4"
            >
              Open in Studio
            </Button>
          ) : null}
        </aside>
      </div>
    </section>
  );
}

function labelFor(agent?: string | null) {
  if (!agent) return "Agent";
  return AGENT_LABELS[agent as AgentKey] ?? agent;
}

function ExtractedSummary({ extracted }: { extracted: ExtractedVideo }) {
  return (
    <div className="rounded-md border border-hairline bg-surface p-4 space-y-3">
      <div className="flex items-start gap-3">
        <div className="flex flex-col items-center shrink-0 pt-[2px] min-w-[42px]">
          <span className="font-mono text-[18px] tabular-nums leading-none text-white">
            {extracted.derived_duration_min}
          </span>
          <span className="mt-0.5 font-mono text-[9px] uppercase tracking-[0.15em] text-mist">
            min
          </span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <h3 className="text-[14px] text-white leading-[1.3] flex-1 font-medium">
              {extracted.title}
            </h3>
            <Badge tone="muted" className="shrink-0">
              {extracted.idea_type}
            </Badge>
          </div>
          <p className="text-[12.5px] text-white/75 mt-2 leading-[1.55]">
            {extracted.rationale}
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 pt-2 border-t border-hairline">
        <div>
          <div className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-mist mb-1.5">
            Sections · {extracted.script.sections.length}
          </div>
          <ul className="space-y-1">
            {extracted.script.sections.map((s, i) => (
              <li key={i} className="text-[12px] text-white/85 leading-[1.4]">
                <span className="font-mono tabular-nums text-mist text-[10.5px] mr-1.5">
                  {String(i + 1).padStart(2, "0")}
                </span>
                {s.heading}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-mist mb-1.5">
            Outline · {extracted.outline.items.length}
          </div>
          <ul className="space-y-1">
            {extracted.outline.items.slice(0, 6).map((it) => (
              <li key={it.number} className="text-[12px] text-white/85 leading-[1.4]">
                <span className="font-mono tabular-nums text-mist text-[10.5px] mr-1.5">
                  {String(it.number).padStart(2, "0")}
                </span>
                {it.label}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: Status }) {
  if (status === "running") {
    return (
      <Badge tone="cinnabar">
        <Sparkle size={10} weight="bold" />
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
  return (
    <Badge tone="warn">
      <Warning size={10} weight="fill" />
      failed
    </Badge>
  );
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

function AgentRow({ runtime }: { runtime: AgentRuntime }) {
  const trail = runtime.streamingText.slice(-200).trim();
  return (
    <div
      className={cn(
        "rounded-md border px-3 py-2.5 transition-colors",
        runtime.status === "active"
          ? "border-cinnabar/40 bg-cinnabar/[0.04]"
          : runtime.status === "done"
            ? "border-hairline bg-white/[0.015]"
            : "border-hairline bg-transparent",
      )}
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-full shrink-0",
            runtime.status === "active"
              ? "bg-cinnabar animate-pulse"
              : runtime.status === "done"
                ? "bg-white/60"
                : "bg-mist/40",
          )}
        />
        <span className="text-[12.5px] text-white flex-1">{runtime.label}</span>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-mist">
          {runtime.status === "active"
            ? "working"
            : runtime.status === "done"
              ? "done"
              : "idle"}
        </span>
      </div>
      {runtime.status === "active" && trail ? (
        <pre className="mt-2 max-h-[80px] overflow-hidden whitespace-pre-wrap font-mono text-[11px] leading-[1.5] text-white/70">
          {trail}
        </pre>
      ) : null}
    </div>
  );
}

function TimelineRow({ entry }: { entry: TimelineEntry }) {
  const dotColor =
    entry.kind === "error"
      ? "bg-sienna"
      : entry.kind === "task"
        ? "bg-cinnabar"
        : entry.kind === "info"
          ? "bg-white/60"
          : "bg-mist";
  return (
    <li className="flex gap-3 text-[12.5px] leading-[1.45]">
      <span className={cn("mt-[6px] h-1.5 w-1.5 rounded-full shrink-0", dotColor)} />
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

export type { Setup as ContentExtractSetup };
