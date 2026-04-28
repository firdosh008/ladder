import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Sparkle,
  Cpu,
  CheckCircle,
  Warning,
  ArrowsClockwise,
  Lightning,
} from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { cn } from "../../lib/cn";
import {
  fetchStudioByIdea,
  runStudioStream,
  type AgentEvent,
  type Outline,
  type Scene,
  type Script,
} from "../../lib/agents";

/**
 * Inline studio streamer.
 *
 * Mounted inside the Script + Scene panels of /studio/:id. On mount:
 *   1. Calls GET /studio-sessions/by-idea/{idea_id}.
 *   2. If a script artifact exists → renders it (no streaming).
 *   3. Else → opens /ws/agents/studio and streams script + outline live.
 *
 * Exposes the resolved Script + Outline to its parent via render-props so
 * the parent panels can lay them out independently in the studio's
 * three-column grid.
 */

type AgentKey = "script_writer" | "outline_planner";

type AgentRuntime = {
  key: AgentKey;
  label: string;
  status: "idle" | "active" | "done";
  streamingText: string;
};

const AGENT_ORDER: AgentKey[] = ["script_writer", "outline_planner"];

const AGENT_LABELS: Record<AgentKey, string> = {
  script_writer: "Script writer",
  outline_planner: "Outline planner",
};

const AGENT_HINT: Record<AgentKey, string> = {
  script_writer: "drafting talking points + transitions section by section",
  outline_planner: "compressing the script into a numbered scene outline",
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

type Status = "loading" | "running" | "ready" | "failed";

export type StudioSessionRow = {
  id: string;
  output_type?: string | null;
  brand_id?: string | null;
  thumbnail_selected_id?: string | null;
  target_duration_min?: number | null;
};

export type StudioStreamState = {
  status: Status;
  script: Script | null;
  outline: Outline | null;
  scene: Scene | null;
  sessionId: string | null;
  session: StudioSessionRow | null;
  runtime: Record<AgentKey, AgentRuntime>;
  error: string | null;
  cost: number | null;
  hydratedFromDb: boolean;
  /** Replace the local outline (e.g. after a manual edit save). */
  setOutline: (outline: Outline) => void;
  /**
   * Force a fresh agent run, bypassing the DB-hydrate path. The next
   * effect cycle will skip `fetchStudioByIdea` and open the WS directly,
   * so any saved script/outline gets superseded by a new versioned
   * artifact. Used when the founder changes the target runtime, or when
   * they explicitly hit "re-run".
   */
  regenerate: () => void;
  /** @deprecated alias of `regenerate`, kept so existing callers compile. */
  rerun: () => void;
};

type Props = {
  ideaId: string;
  duration?: number;
  /** Optional render-prop. Useful when parent wants to lay things out itself. */
  children?: (state: StudioStreamState) => React.ReactNode;
};

export function useStudioStream(ideaId: string, duration?: number): StudioStreamState {
  const [status, setStatus] = useState<Status>("loading");
  const [script, setScript] = useState<Script | null>(null);
  const [outline, setOutline] = useState<Outline | null>(null);
  const [scene, setScene] = useState<Scene | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<StudioSessionRow | null>(null);
  const [runtime, setRuntime] = useState<Record<AgentKey, AgentRuntime>>(
    initialRuntime,
  );
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState<number | null>(null);
  const [hydratedFromDb, setHydratedFromDb] = useState(false);
  const [runEpoch, setRunEpoch] = useState(0);
  // Set synchronously by `regenerate()` so the very next effect cycle
  // skips the GET-and-hydrate path and opens a fresh WS instead. Reset
  // to false the moment the new stream starts, so subsequent
  // navigation/refresh still rehydrate the latest saved artifact.
  const forceFreshRef = useRef(false);

  const startStream = useCallback(() => {
    let cancelled = false;
    setStatus("running");
    setError(null);
    setHydratedFromDb(false);
    setScript(null);
    setOutline(null);
    setScene(null);
    setRuntime(initialRuntime());

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
                    streamingText: (prev[key].streamingText + ev.content).slice(-1800),
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
          break;
        }
        case "script_ready":
          setScript(ev.script);
          break;
        case "outline_ready":
          setOutline(ev.outline);
          break;
        case "persisted":
          if (ev.session_id) setSessionId(ev.session_id);
          break;
        case "usage":
          setCost(ev.token_usage.cost_usd);
          break;
        case "error":
          setError(ev.message);
          break;
        default:
          break;
      }
    };

    runStudioStream(ideaId, duration, handle)
      .then((result) => {
        if (cancelled) return;
        setCost(result.cost_usd);
        setStatus("ready");
        setRuntime((prev) => {
          const next = { ...prev };
          for (const k of AGENT_ORDER) next[k] = { ...next[k], status: "done" };
          return next;
        });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setStatus("failed");
      });

    return () => {
      cancelled = true;
    };
  }, [ideaId, duration]);

  useEffect(() => {
    if (!ideaId) return;

    let cancelled = false;
    let teardown: (() => void) | null = null;

    setStatus("loading");
    setError(null);
    setScript(null);
    setOutline(null);
    setScene(null);
    setSessionId(null);
    setSession(null);
    setHydratedFromDb(false);
    setRuntime(initialRuntime());

    if (forceFreshRef.current) {
      forceFreshRef.current = false;
      teardown = startStream();
      return () => {
        cancelled = true;
        if (teardown) teardown();
      };
    }

    fetchStudioByIdea(ideaId)
      .then((res) => {
        if (cancelled) return;
        const existingScript = (res.script?.content_json as Script | undefined) ?? null;
        const existingOutline =
          (res.outline?.content_json as Outline | undefined) ?? null;
        const existingScene =
          (res.scene?.content_json as Scene | undefined) ?? null;
        const sessionRow = (res.session as StudioSessionRow | null) ?? null;
        const existingSessionId = sessionRow?.id ?? null;
        if (existingSessionId) setSessionId(existingSessionId);
        if (sessionRow) setSession(sessionRow);
        if (existingScene) setScene(existingScene);
        if (existingScript && existingOutline) {
          setScript(existingScript);
          setOutline(existingOutline);
          setRuntime((prev) => {
            const next = { ...prev };
            for (const k of AGENT_ORDER) next[k] = { ...next[k], status: "done" };
            return next;
          });
          setHydratedFromDb(true);
          setStatus("ready");
          return;
        }
        teardown = startStream();
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setStatus("failed");
      });

    return () => {
      cancelled = true;
      if (teardown) teardown();
    };
  }, [ideaId, runEpoch, startStream]);

  const regenerate = useCallback(() => {
    forceFreshRef.current = true;
    setRunEpoch((e) => e + 1);
  }, []);
  const rerun = regenerate;

  return useMemo(
    () => ({
      status,
      script,
      outline,
      scene,
      sessionId,
      session,
      runtime,
      error,
      cost,
      hydratedFromDb,
      setOutline,
      regenerate,
      rerun,
    }),
    [
      status,
      script,
      outline,
      scene,
      sessionId,
      session,
      runtime,
      error,
      cost,
      hydratedFromDb,
      regenerate,
      rerun,
    ],
  );
}

export function StudioStreamProvider({ ideaId, duration, children }: Props) {
  const state = useStudioStream(ideaId, duration);
  return <>{children?.(state)}</>;
}

export function StudioRunStrip({ state }: { state: StudioStreamState }) {
  const { status, runtime, hydratedFromDb, cost, error, rerun } = state;
  const activeAgent =
    AGENT_ORDER.find((k) => runtime[k].status === "active") ??
    (status === "ready" ? null : AGENT_ORDER[0]);

  return (
    <div className="rounded-md border border-hairline bg-white/[0.015] p-3">
      <div className="flex items-center gap-2">
        {status === "ready" ? (
          <Badge tone="neutral">
            <CheckCircle size={10} weight="fill" />
            ready
          </Badge>
        ) : status === "failed" ? (
          <Badge tone="warn">
            <Warning size={10} weight="fill" />
            failed
          </Badge>
        ) : status === "loading" ? (
          <Badge tone="muted">
            <Cpu size={10} weight="bold" />
            checking
          </Badge>
        ) : (
          <Badge tone="cinnabar">
            <Sparkle size={10} weight="bold" />
            live
          </Badge>
        )}
        <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
          {hydratedFromDb
            ? "hydrated from last run"
            : status === "loading"
              ? "checking for saved version"
              : activeAgent
                ? `${runtime[activeAgent].label} · ${AGENT_HINT[activeAgent]}`
                : status === "ready"
                  ? "fresh run complete"
                  : status === "running"
                    ? "opening connection"
                    : "stalled"}
        </span>
        <div className="flex-1" />
        {status === "ready" ? (
          <Button variant="ghost" size="sm" onClick={rerun}>
            <ArrowsClockwise size={11} weight="bold" />
            re-run
          </Button>
        ) : null}
        {cost !== null ? (
          <span className="font-mono text-[10.5px] text-mist">
            ${cost.toFixed(4)}
          </span>
        ) : null}
      </div>
      <div className="mt-2 grid grid-cols-2 gap-1.5">
        {AGENT_ORDER.map((k) => (
          <AgentRow key={k} runtime={runtime[k]} />
        ))}
      </div>
      {error ? (
        <div className="mt-2 rounded border border-sienna/40 bg-sienna/[0.08] p-2 text-[12px] text-white/90 flex gap-2">
          <Warning
            size={12}
            weight="fill"
            className="text-sienna shrink-0 mt-[2px]"
          />
          <span>{error}</span>
        </div>
      ) : null}
    </div>
  );
}

function AgentRow({ runtime }: { runtime: AgentRuntime }) {
  return (
    <div
      className={cn(
        "rounded-md border px-2.5 py-1.5",
        runtime.status === "active"
          ? "border-cinnabar/40 bg-cinnabar/[0.04]"
          : runtime.status === "done"
            ? "border-hairline bg-white/[0.015]"
            : "border-hairline",
      )}
    >
      <div className="flex items-center gap-1.5">
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
        <span className="text-[12px] text-white truncate flex-1">
          {runtime.label}
        </span>
        <span className="font-mono text-[9.5px] uppercase tracking-[0.18em] text-mist">
          {runtime.status === "active"
            ? "working"
            : runtime.status === "done"
              ? "done"
              : "queued"}
        </span>
      </div>
    </div>
  );
}

export function ScriptView({
  script,
  state,
}: {
  script: Script | null;
  state: StudioStreamState;
}) {
  if (script) {
    return (
      <div className="space-y-4">
        {script.sections.map((sec, i) => (
          <article
            key={i}
            className="rounded-lg border border-hairline bg-surface p-4"
          >
            <header className="flex items-baseline justify-between gap-3 mb-2">
              <div className="flex items-baseline gap-2.5 min-w-0">
                <span className="font-mono text-[10.5px] tabular-nums text-mist tracking-[0.18em] uppercase">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <h3 className="font-sans font-semibold text-[15px] text-white leading-tight truncate">
                  {sec.heading}
                </h3>
              </div>
              <Badge tone="muted" className="shrink-0">
                {sec.duration_min} min
              </Badge>
            </header>
            <ul className="space-y-1.5">
              {sec.talking_points.map((tp, j) => (
                <li
                  key={j}
                  className="flex gap-2 text-[13.5px] text-white/85 leading-[1.55]"
                >
                  <span className="text-mist shrink-0">•</span>
                  <span>{tp}</span>
                </li>
              ))}
            </ul>
            {sec.transition ? (
              <p className="mt-3 pt-3 border-t border-hairline text-[12.5px] text-mist italic leading-[1.55]">
                → {sec.transition}
              </p>
            ) : null}
          </article>
        ))}
      </div>
    );
  }

  if (state.status === "running" || state.status === "loading") {
    const writer = state.runtime.script_writer;
    const trail = writer.streamingText.slice(-1200).trim();
    const phase =
      state.status === "loading"
        ? "checking saved version"
        : writer.status === "active"
          ? "live tokens"
          : "warming up";
    return (
      <div className="space-y-3">
        <p className="font-mono text-[11.5px] text-mist">
          · streaming script · {phase} ·
        </p>
        {trail ? (
          <pre className="rounded-md border border-hairline bg-black/30 p-3 max-h-[420px] overflow-hidden whitespace-pre-wrap font-mono text-[12px] leading-[1.55] text-white/75">
            {trail}
          </pre>
        ) : (
          <ShimmerLines count={8} />
        )}
      </div>
    );
  }

  if (state.status === "failed") {
    return (
      <div className="rounded-md border border-sienna/40 bg-sienna/[0.08] p-3 text-[12.5px] text-white/90 flex gap-2">
        <Warning
          size={14}
          weight="fill"
          className="text-sienna shrink-0 mt-0.5"
        />
        <span>{state.error ?? "stream failed"}</span>
      </div>
    );
  }
  return null;
}

export function OutlineView({
  outline,
  state,
}: {
  outline: Outline | null;
  state: StudioStreamState;
}) {
  if (outline) {
    return (
      <ol className="space-y-2.5">
        {outline.items.map((it) => (
          <li
            key={it.number}
            className="rounded-md border border-hairline bg-surface p-3"
          >
            <div className="flex items-baseline gap-2.5 mb-1">
              <span className="font-mono text-[10.5px] tabular-nums text-mist tracking-[0.18em] uppercase shrink-0">
                {String(it.number).padStart(2, "0")}
              </span>
              <span className="font-sans font-semibold text-[13.5px] text-white leading-tight">
                {it.label}
              </span>
            </div>
            <p className="text-[12.5px] text-white/80 leading-[1.55] pl-[26px]">
              {it.beat}
            </p>
          </li>
        ))}
      </ol>
    );
  }

  if (state.status === "running" || state.status === "loading") {
    const planner = state.runtime.outline_planner;
    const trail = planner.streamingText.slice(-800).trim();
    return (
      <div className="space-y-3">
        <p className="font-mono text-[11.5px] text-mist">
          · outline lands once the script settles ·
        </p>
        {trail ? (
          <pre className="rounded-md border border-hairline bg-black/30 p-3 max-h-[300px] overflow-hidden whitespace-pre-wrap font-mono text-[12px] leading-[1.55] text-white/75">
            {trail}
          </pre>
        ) : (
          <ShimmerLines count={5} />
        )}
      </div>
    );
  }

  return null;
}

function ShimmerLines({ count }: { count: number }) {
  return (
    <div className="space-y-2 animate-pulse">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="h-3 rounded bg-white/[0.04]"
          style={{ width: `${65 + ((i * 13) % 30)}%` }}
        />
      ))}
    </div>
  );
}

export function StudioRunBlock({ state }: { state: StudioStreamState }) {
  return (
    <div className="space-y-3">
      <StudioRunStrip state={state} />
      <ScriptViewHints state={state} />
    </div>
  );
}

function ScriptViewHints({ state }: { state: StudioStreamState }) {
  if (state.status === "ready" || state.status === "failed") return null;
  return (
    <p className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
      <Lightning size={11} weight="bold" />
      script writer first · then outline planner · auto-saves to artifacts
    </p>
  );
}

export type { Script, Outline };

export {
  Cpu as ScenePanelIcon,
  Sparkle as ScriptPanelIcon,
};
