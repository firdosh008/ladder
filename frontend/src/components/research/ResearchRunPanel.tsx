import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  ArrowsClockwise,
  MagnifyingGlass,
  Gauge,
  Sparkle,
  CheckCircle,
  Warning,
  Globe,
  Stack,
  Lightning,
} from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { cn } from "../../lib/cn";
import {
  runResearchStream,
  type AgentEvent,
  type IdeaDraft,
  type ResearchSetup,
  type Source,
  type SourcePlatform,
} from "../../lib/agents";
import { api, ApiError } from "../../lib/api";
import { SourcePreview } from "./SourcePreview";
import {
  buildSnapshotPayload,
  writeIdeaResearchSnapshot,
} from "../../lib/researchSnapshot";

/**
 * Inline research panel shown on /make per PRD §2 Option 2.
 *
 * Lives in the page flow (not a drawer) so the run stays visible until the
 * user explicitly starts over. Completed runs are mirrored to
 * sessionStorage so a page refresh within the same tab restores the last
 * set of drafts (the live WS dies on refresh — we only resurrect the
 * terminal state).
 */

const STORAGE_KEY = "ladder:research:last";
const STORAGE_VERSION = 2;

type StoredRun = {
  v: number;
  topic: string;
  drafts: IdeaDraft[];
  sources: Source[];
  queries: string[];
  costUsd: number | null;
  completedAt: number;
};

type TimelineKind = "agent" | "tool" | "task" | "info" | "error";

type TimelineEntry = {
  id: number;
  kind: TimelineKind;
  agent?: string | null;
  label: string;
  detail?: string;
};

type AgentKey = "search_agent" | "trend_scorer" | "idea_formulator";

type AgentRuntime = {
  key: AgentKey;
  label: string;
  status: "idle" | "active" | "done";
  streamingText: string;
  toolCalls: { tool: string; arguments: string }[];
};

type Props = {
  setup: ResearchSetup | null;
  onStartOver: () => void;
  onIdeasChanged?: () => void;
};

const AGENT_ORDER: AgentKey[] = ["search_agent", "trend_scorer", "idea_formulator"];

const AGENT_LABELS: Record<AgentKey, string> = {
  search_agent: "Trend researcher",
  trend_scorer: "Outlier scorer",
  idea_formulator: "Idea architect",
};

const AGENT_HINT: Record<AgentKey, string> = {
  search_agent: "scouring the web for specific, recent signals",
  trend_scorer: "ranking signals by outlier potential",
  idea_formulator: "shaping signals into founder-voice drafts",
};

function labelFor(agent?: string | null): string {
  if (!agent) return "Agent";
  return AGENT_LABELS[agent as AgentKey] ?? agent;
}

function initialRuntime(): Record<AgentKey, AgentRuntime> {
  return AGENT_ORDER.reduce(
    (acc, key) => {
      acc[key] = {
        key,
        label: AGENT_LABELS[key],
        status: "idle",
        streamingText: "",
        toolCalls: [],
      };
      return acc;
    },
    {} as Record<AgentKey, AgentRuntime>,
  );
}

function completedRuntime(): Record<AgentKey, AgentRuntime> {
  return AGENT_ORDER.reduce(
    (acc, key) => {
      acc[key] = {
        key,
        label: AGENT_LABELS[key],
        status: "done",
        streamingText: "",
        toolCalls: [],
      };
      return acc;
    },
    {} as Record<AgentKey, AgentRuntime>,
  );
}

export function loadStoredRun(): StoredRun | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as StoredRun;
    if (parsed.v !== STORAGE_VERSION) return null;
    if (!parsed.topic || !Array.isArray(parsed.drafts)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearStoredRun(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(STORAGE_KEY);
}

export function ResearchRunPanel({ setup, onStartOver, onIdeasChanged }: Props) {
  const navigate = useNavigate();
  const stored = useMemo(() => (setup ? null : loadStoredRun()), [setup]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [runtime, setRuntime] = useState<Record<AgentKey, AgentRuntime>>(() =>
    stored ? completedRuntime() : initialRuntime(),
  );
  const [sources, setSources] = useState<Source[]>(() => stored?.sources ?? []);
  const [queries, setQueries] = useState<string[]>(() => stored?.queries ?? []);
  const [drafts, setDrafts] = useState<IdeaDraft[]>(() => stored?.drafts ?? []);
  const [status, setStatus] = useState<"idle" | "running" | "ready" | "failed">(
    stored ? "ready" : setup ? "running" : "idle",
  );
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState<number | null>(stored?.costUsd ?? null);
  const [savingIdx, setSavingIdx] = useState<number | null>(null);
  const [savingAll, setSavingAll] = useState(false);
  const [savedAllCount, setSavedAllCount] = useState<number | null>(null);
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [platformFilter, setPlatformFilter] = useState<SourcePlatform | null>(null);
  const keyRef = useRef(0);
  const hasStartedRef = useRef<string | null>(null);
  const storedTopic = stored?.topic ?? null;
  const currentTopic = setup?.topic ?? storedTopic ?? "";

  useEffect(() => {
    if (!setup) {
      hasStartedRef.current = null;
      return;
    }
    if (hasStartedRef.current === setup.topic) return;
    hasStartedRef.current = setup.topic;

    clearStoredRun();

    setTimeline([]);
    setRuntime(initialRuntime());
    setSources([]);
    setQueries([]);
    setDrafts([]);
    setStatus("running");
    setError(null);
    setCost(null);
    setSavingIdx(null);
    setSavingAll(false);
    setSavedAllCount(null);
    setSourcesExpanded(false);
    setPlatformFilter(null);

    const push = (entry: Omit<TimelineEntry, "id">) => {
      keyRef.current += 1;
      setTimeline((prev) => [...prev, { id: keyRef.current, ...entry }]);
    };

    const markAgent = (agent: AgentKey, status: AgentRuntime["status"]) => {
      setRuntime((prev) => ({ ...prev, [agent]: { ...prev[agent], status } }));
    };

    let finalDrafts: IdeaDraft[] = [];
    let finalSources: Source[] = [];
    let finalQueries: string[] = [];

    const handle = (ev: AgentEvent) => {
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
        case "tool_call": {
          const agent = (ev.agent ?? "") as AgentKey;
          let queryText = "";
          try {
            const parsed = ev.arguments ? JSON.parse(ev.arguments) : {};
            queryText = typeof parsed.query === "string" ? parsed.query : "";
          } catch {
            queryText = ev.arguments ?? "";
          }
          setRuntime((prev) =>
            prev[agent]
              ? {
                  ...prev,
                  [agent]: {
                    ...prev[agent],
                    toolCalls: [
                      ...prev[agent].toolCalls,
                      { tool: ev.tool, arguments: queryText || ev.arguments || "" },
                    ],
                  },
                }
              : prev,
          );
          push({
            kind: "tool",
            agent: ev.agent,
            label: `${labelFor(ev.agent)} → ${ev.tool}`,
            detail: queryText || ev.arguments,
          });
          break;
        }
        case "sources": {
          setQueries((prev) => {
            const next = prev.includes(ev.query) ? prev : [...prev, ev.query];
            finalQueries = next;
            return next;
          });
          setSources((prev) => {
            const seen = new Set(prev.map((s) => s.url));
            const additions = ev.items.filter((s) => s.url && !seen.has(s.url));
            const next = [...prev, ...additions];
            finalSources = next;
            return next;
          });
          push({
            kind: "tool",
            agent: "search_agent",
            label: `${ev.items.length} sources ← "${ev.query}"`,
          });
          break;
        }
        case "text_delta": {
          const agent = ev.agent as AgentKey;
          setRuntime((prev) =>
            prev[agent]
              ? {
                  ...prev,
                  [agent]: {
                    ...prev[agent],
                    streamingText: (prev[agent].streamingText + ev.content).slice(-1400),
                  },
                }
              : prev,
          );
          break;
        }
        case "task_complete": {
          const agent = (ev.agent ?? "") as AgentKey;
          if (AGENT_ORDER.includes(agent)) markAgent(agent, "done");
          push({
            kind: "task",
            agent: ev.agent,
            label: `${labelFor(ev.agent)} wrapped`,
            detail: ev.preview,
          });
          break;
        }
        case "ideas_ready":
          finalDrafts = ev.ideas;
          setDrafts(ev.ideas);
          push({
            kind: "info",
            label: `${ev.ideas.length} drafts ready — pick one to open in Studio, or save all to /videos`,
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
        try {
          const snapshot: StoredRun = {
            v: STORAGE_VERSION,
            topic: setup.topic,
            drafts: finalDrafts,
            sources: finalSources,
            queries: finalQueries,
            costUsd: result.cost_usd,
            completedAt: Date.now(),
          };
          window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
        } catch {
          /* sessionStorage may be full or disabled — best-effort */
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err));
        setStatus("failed");
      });
  }, [setup]);

  const handleStartOver = useCallback(() => {
    clearStoredRun();
    hasStartedRef.current = null;
    onStartOver();
  }, [onStartOver]);

  async function pickDraft(index: number) {
    if (savingIdx !== null || savingAll) return;
    const draft = drafts[index];
    if (!draft) return;
    setSavingIdx(index);
    setError(null);
    try {
      const payload = buildIdeaPayload(draft, currentTopic, {
        sources,
        queries,
        costUsd: cost,
      });
      const res = await api.post<{ idea: { id: string } }>("/ideas", payload);
      writeIdeaResearchSnapshot({
        ideaId: res.idea.id,
        topic: currentTopic,
        sources,
        queries,
        costUsd: cost,
      });
      onIdeasChanged?.();
      clearStoredRun();
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

  async function saveAllToIdeas() {
    if (savingAll || savingIdx !== null || drafts.length === 0) return;
    setSavingAll(true);
    setError(null);
    setSavedAllCount(null);
    try {
      const results = await Promise.allSettled(
        drafts.map((d) =>
          api.post<{ idea: { id: string } }>(
            "/ideas",
            buildIdeaPayload(d, currentTopic, {
              sources,
              queries,
              costUsd: cost,
            }),
          ),
        ),
      );
      results.forEach((r) => {
        if (r.status === "fulfilled") {
          writeIdeaResearchSnapshot({
            ideaId: r.value.idea.id,
            topic: currentTopic,
            sources,
            queries,
            costUsd: cost,
          });
        }
      });
      const saved = results.filter((r) => r.status === "fulfilled").length;
      const failed = results.length - saved;
      setSavedAllCount(saved);
      onIdeasChanged?.();
      if (failed > 0) {
        setError(`${saved}/${results.length} saved · ${failed} failed`);
      }
      if (saved === drafts.length) {
        clearStoredRun();
      }
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "Could not save ideas",
      );
    } finally {
      setSavingAll(false);
    }
  }

  const activeAgent = useMemo(
    () => AGENT_ORDER.find((k) => runtime[k].status === "active") ?? null,
    [runtime],
  );

  const platformCounts = useMemo(() => {
    const counts = new Map<SourcePlatform, number>();
    for (const s of sources) {
      const p = (s.platform ?? "web") as SourcePlatform;
      counts.set(p, (counts.get(p) ?? 0) + 1);
    }
    return counts;
  }, [sources]);

  const filteredSources = useMemo(
    () =>
      platformFilter
        ? sources.filter((s) => (s.platform ?? "web") === platformFilter)
        : sources,
    [sources, platformFilter],
  );

  // Default ('all' filter, collapsed) interleaves by platform so visual
  // platforms (yt / x / ig) aren't buried behind whichever search tool fired
  // first. Filtered or expanded views show the natural arrival order.
  const visibleSources = useMemo(() => {
    if (platformFilter || sourcesExpanded) return filteredSources;
    return roundRobinByPlatform(sources).slice(0, 8);
  }, [filteredSources, sources, platformFilter, sourcesExpanded]);

  const isRestored = !setup && stored !== null;

  return (
    <section
      aria-label="Research run"
      className="mt-8 rounded-xl border border-hairline bg-surface/70 overflow-hidden"
    >
      {/* Header */}
      <div className="px-6 pt-5 pb-4 border-b border-hairline flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-1.5 flex items-center gap-2">
            <span>§ research crew</span>
            <StatusBadge status={status} />
            {isRestored ? (
              <Badge tone="muted">
                <Stack size={10} weight="bold" />
                restored
              </Badge>
            ) : null}
          </div>
          <h2 className="font-display text-[22px] leading-[1.15] text-white truncate">
            {currentTopic || "Research"}
          </h2>
          <p className="mt-1 text-[12.5px] text-mist">
            {activeAgent
              ? `${labelFor(activeAgent)} · ${AGENT_HINT[activeAgent]}`
              : status === "ready"
                ? `${drafts.length} draft${drafts.length === 1 ? "" : "s"} · ${sources.length} source${sources.length === 1 ? "" : "s"}${
                    cost !== null ? ` · $${cost.toFixed(4)}` : ""
                  }${isRestored ? " · from this session" : ""}`
                : status === "failed"
                  ? "Stream failed"
                  : status === "running"
                    ? "Warming up 3 agents"
                    : ""}
          </p>
        </div>
        {status !== "running" ? (
          <Button variant="ghost" size="sm" onClick={handleStartOver}>
            <ArrowsClockwise size={12} weight="bold" />
            New research
          </Button>
        ) : null}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-0">
        {/* LEFT: drafts + progress */}
        <div className="p-6 lg:border-r lg:border-hairline space-y-6 min-w-0">
          {/* Drafts / primary output */}
          <section>
            <SectionHeading
              icon={Sparkle}
              label={
                drafts.length > 0 ? `Drafts · ${drafts.length}` : "Drafts"
              }
              right={
                drafts.length > 0 ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={saveAllToIdeas}
                    disabled={savingAll || savingIdx !== null}
                  >
                    <Lightning size={11} weight="bold" />
                    {savingAll
                      ? "saving…"
                      : savedAllCount !== null
                        ? `saved ${savedAllCount}/${drafts.length}`
                        : "save all to /videos"}
                  </Button>
                ) : null
              }
            />
            <div className="mt-3 space-y-2">
              {drafts.length === 0 ? (
                <p className="font-mono text-[11.5px] text-mist">
                  · ideas land here once the crew wraps (~15s) ·
                </p>
              ) : (
                drafts.map((draft, i) => (
                  <DraftCard
                    key={`${draft.title}-${i}`}
                    draft={draft}
                    loading={savingIdx === i}
                    disabled={
                      (savingIdx !== null && savingIdx !== i) || savingAll
                    }
                    onPick={() => pickDraft(i)}
                  />
                ))
              )}
            </div>
          </section>

          {/* Agents */}
          <section>
            <SectionHeading icon={Gauge} label="Agents" />
            <div className="mt-3 space-y-2">
              {AGENT_ORDER.map((key) => (
                <AgentRow key={key} runtime={runtime[key]} />
              ))}
            </div>
          </section>

          {/* Activity */}
          {timeline.length > 0 ? (
            <section>
              <SectionHeading icon={MagnifyingGlass} label="Activity" />
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

        {/* RIGHT: sources rail */}
        <aside className="p-6 bg-black/20 lg:bg-transparent">
          <SectionHeading
            icon={Globe}
            label={sources.length > 0 ? `Sources · ${sources.length}` : "Sources"}
            right={
              queries.length > 0 ? (
                <span className="font-mono text-[10.5px] text-mist normal-case tracking-normal">
                  {queries.length} quer{queries.length === 1 ? "y" : "ies"}
                </span>
              ) : null
            }
          />
          {sources.length === 0 ? (
            <p className="mt-3 font-mono text-[11.5px] text-mist">
              · search results surface here as the researcher works ·
            </p>
          ) : (
            <>
              {platformCounts.size > 1 ? (
                <PlatformFilterRow
                  counts={platformCounts}
                  active={platformFilter}
                  total={sources.length}
                  onChange={(p) => {
                    setPlatformFilter(p);
                    setSourcesExpanded(false);
                  }}
                />
              ) : null}
              <ol className="mt-2 grid grid-cols-1 gap-1.5">
                {visibleSources.map((source, i) => (
                  <li key={source.url + i}>
                    <SourcePreview source={source} index={i + 1} variant="compact" />
                  </li>
                ))}
              </ol>
              {!platformFilter && filteredSources.length > visibleSources.length ? (
                <button
                  type="button"
                  onClick={() => setSourcesExpanded(true)}
                  className="mt-2 font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist hover:text-white transition-colors"
                >
                  + show {filteredSources.length - visibleSources.length} more
                </button>
              ) : null}
            </>
          )}
        </aside>
      </div>
    </section>
  );
}

function buildIdeaPayload(
  draft: IdeaDraft,
  topic: string,
  research: {
    sources: Source[];
    queries: string[];
    costUsd: number | null;
  },
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    title: draft.title,
    status: "new",
    source_type: "research",
  };
  if (topic) payload.source_content = topic;
  if (draft.rationale) payload.rationale = draft.rationale;
  if (draft.idea_type) payload.idea_type = draft.idea_type;
  if (typeof draft.opportunity_score === "number") {
    payload.opportunity_score = draft.opportunity_score;
  }
  if (typeof draft.outlier_score === "number") {
    payload.outlier_score = draft.outlier_score;
  }
  // Persist the snapshot on the row itself so /studio/:id can render the
  // same source previews after a reload, on a different device, or when
  // sessionStorage gets nuked.
  if (research.sources.length > 0) {
    payload.research_snapshot = buildSnapshotPayload({
      topic,
      sources: research.sources,
      queries: research.queries,
      costUsd: research.costUsd,
    });
  }
  return payload;
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
  right,
}: {
  icon: React.ElementType;
  label: string;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist">
        <Icon size={11} weight="bold" />
        {label}
      </div>
      {right}
    </div>
  );
}

function AgentRow({ runtime }: { runtime: AgentRuntime }) {
  const trailingText = runtime.streamingText.slice(-240).trim();
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
      {runtime.toolCalls.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {runtime.toolCalls.map((tc, i) => (
            <span
              key={`${tc.tool}-${i}`}
              className="inline-flex items-center gap-1 rounded-full border border-hairline bg-white/[0.02] px-2 py-0.5 font-mono text-[10px] text-mist"
              title={tc.arguments}
            >
              <MagnifyingGlass size={9} weight="bold" />
              {tc.tool}
              {tc.arguments ? (
                <span className="text-white/60 max-w-[220px] truncate">
                  · {tc.arguments}
                </span>
              ) : null}
            </span>
          ))}
        </div>
      ) : null}
      {runtime.status === "active" && trailingText ? (
        <pre className="mt-2 max-h-[96px] overflow-hidden whitespace-pre-wrap font-mono text-[11px] leading-[1.5] text-white/70">
          {trailingText}
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
        : entry.kind === "tool"
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
        "w-full text-left rounded-md border bg-surface p-4 transition-colors",
        "border-hairline hover:border-cinnabar/50",
        "disabled:opacity-60 disabled:cursor-not-allowed",
      )}
    >
      <div className="flex items-start gap-3">
        {typeof draft.opportunity_score === "number" ? (
          <div className="flex flex-col items-center shrink-0 pt-[2px] min-w-[36px]">
            <span
              className={cn(
                "font-mono text-[16px] tabular-nums leading-none",
                draft.opportunity_score >= 80 ? "text-cinnabar" : "text-white/85",
              )}
            >
              {draft.opportunity_score}
            </span>
            <span className="mt-0.5 font-mono text-[9px] uppercase tracking-[0.15em] text-mist">
              opp
            </span>
            {typeof draft.outlier_score === "number" ? (
              <span className="mt-2 font-mono text-[10px] tabular-nums text-white/75">
                {draft.outlier_score.toFixed(1)}×
              </span>
            ) : null}
          </div>
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <div className="text-[14px] text-white leading-[1.3] flex-1 font-medium">
              {draft.title}
            </div>
            {draft.idea_type ? (
              <Badge tone="muted" className="shrink-0">
                {draft.idea_type}
              </Badge>
            ) : null}
          </div>
          {draft.rationale ? (
            <p className="text-[12.5px] text-white/75 mt-2 leading-[1.55]">
              {draft.rationale}
            </p>
          ) : null}
          {draft.why_now ? (
            <div className="mt-2.5 flex gap-1.5 items-start">
              <span className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-mist mt-[3px] shrink-0">
                why now
              </span>
              <p className="text-[11.5px] text-white/75 italic leading-[1.5]">
                {draft.why_now}
              </p>
            </div>
          ) : null}
          {tags.length > 0 ? (
            <div className="flex flex-wrap gap-1 mt-2.5">
              {tags.map((t, i) => (
                <span
                  key={`${t}-${i}`}
                  className="font-mono text-[10px] text-mist border border-hairline rounded px-1.5 py-0.5"
                >
                  {t}
                </span>
              ))}
            </div>
          ) : null}
          <div className="mt-3 flex items-center gap-1 font-mono text-[10.5px] uppercase tracking-[0.18em] text-cinnabar/85">
            {loading ? (
              <span>· saving ·</span>
            ) : (
              <>
                <span>pick &amp; open in studio</span>
                <ArrowRight size={10} weight="bold" />
              </>
            )}
          </div>
        </div>
      </div>
    </button>
  );
}

// ─── platform filter row ──────────────────────────────────────────────────
//
// Subtle chip row that surfaces every platform that returned at least one
// source. Each chip mirrors the SourcePreview pill colors so the rail stays
// visually quiet but the user can drill into IG / YT / X without hunting
// behind a "show more". Only renders when sources span >1 platform.

const PLATFORM_ORDER: SourcePlatform[] = [
  "youtube",
  "x",
  "instagram",
  "reddit",
  "web",
];

const PLATFORM_CHIP_LABEL: Record<SourcePlatform, string> = {
  web: "web",
  reddit: "reddit",
  youtube: "yt",
  x: "x",
  instagram: "ig",
};

const PLATFORM_CHIP_TONE: Record<SourcePlatform, string> = {
  web: "bg-white/[0.04] text-white/65 hover:text-white",
  reddit: "bg-[#ff4500]/[0.10] text-[#ff7a3d] hover:bg-[#ff4500]/[0.18]",
  youtube: "bg-[#ff0000]/[0.10] text-[#ff5c5c] hover:bg-[#ff0000]/[0.18]",
  x: "bg-white/[0.08] text-white/85 hover:bg-white/[0.14]",
  instagram: "bg-[#E1306C]/[0.10] text-[#f06292] hover:bg-[#E1306C]/[0.18]",
};

function PlatformFilterRow({
  counts,
  active,
  total,
  onChange,
}: {
  counts: Map<SourcePlatform, number>;
  active: SourcePlatform | null;
  total: number;
  onChange: (next: SourcePlatform | null) => void;
}) {
  const platforms = PLATFORM_ORDER.filter((p) => (counts.get(p) ?? 0) > 0);
  return (
    <div className="mt-3 -mx-1 flex flex-wrap items-center gap-1">
      <button
        type="button"
        onClick={() => onChange(null)}
        className={cn(
          "rounded px-1.5 py-[2px] font-mono text-[10px] uppercase tracking-[0.14em] transition-colors",
          active === null
            ? "bg-white/[0.10] text-white"
            : "text-mist hover:text-white",
        )}
      >
        all · {total}
      </button>
      {platforms.map((p) => {
        const isActive = active === p;
        const count = counts.get(p) ?? 0;
        return (
          <button
            key={p}
            type="button"
            onClick={() => onChange(isActive ? null : p)}
            className={cn(
              "rounded px-1.5 py-[2px] font-mono text-[10px] uppercase tracking-[0.14em] transition-colors",
              isActive
                ? "ring-1 ring-white/40"
                : "ring-1 ring-transparent",
              PLATFORM_CHIP_TONE[p],
            )}
          >
            {PLATFORM_CHIP_LABEL[p]} · {count}
          </button>
        );
      })}
    </div>
  );
}

// ─── round-robin interleave ───────────────────────────────────────────────
//
// Group sources by platform, then walk groups in PLATFORM_ORDER picking one
// at a time. Visual platforms (yt / x / ig) come first so they always claim
// the prime slots even when reddit/web flooded the stream early.

function roundRobinByPlatform(sources: Source[]): Source[] {
  if (sources.length <= 1) return sources;
  const groups = new Map<SourcePlatform, Source[]>();
  for (const s of sources) {
    const p = (s.platform ?? "web") as SourcePlatform;
    const existing = groups.get(p);
    if (existing) existing.push(s);
    else groups.set(p, [s]);
  }
  const buckets = PLATFORM_ORDER.map((p) => groups.get(p) ?? []).filter(
    (b) => b.length > 0,
  );
  const out: Source[] = [];
  let added = true;
  while (added) {
    added = false;
    for (const bucket of buckets) {
      const next = bucket.shift();
      if (next) {
        out.push(next);
        added = true;
      }
    }
  }
  return out;
}
