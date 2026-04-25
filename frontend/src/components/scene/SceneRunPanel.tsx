import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Sparkle, Lightning, Warning, ArrowsClockwise, Cube } from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/cn";
import { runSceneStream, type AgentEvent, type Scene } from "../../lib/agents";

const SceneView = lazy(() => import("./SceneView"));

type AgentKey = "layout_planner" | "element_designer";

const AGENT_ORDER: AgentKey[] = ["layout_planner", "element_designer"];

const AGENT_LABEL: Record<AgentKey, string> = {
  layout_planner: "Layout planner",
  element_designer: "Element designer",
};

const AGENT_HINT: Record<AgentKey, string> = {
  layout_planner: "deciding canvas size + per-frame regions",
  element_designer: "drawing rectangles, diamonds, arrows, labels",
};

type AgentRuntime = {
  key: AgentKey;
  status: "idle" | "active" | "done";
  preview: string;
};

type Status = "idle" | "running" | "ready" | "failed";

function initialRuntime(): Record<AgentKey, AgentRuntime> {
  return AGENT_ORDER.reduce(
    (acc, key) => {
      acc[key] = { key, status: "idle", preview: "" };
      return acc;
    },
    {} as Record<AgentKey, AgentRuntime>,
  );
}

type Props = {
  sessionId: string | null;
  initialScene: Scene | null;
  outlineReady: boolean;
};

export function SceneRunPanel({
  sessionId,
  initialScene,
  outlineReady,
}: Props) {
  const [scene, setScene] = useState<Scene | null>(initialScene);
  const [status, setStatus] = useState<Status>(
    initialScene ? "ready" : "idle",
  );
  const [runtime, setRuntime] = useState<Record<AgentKey, AgentRuntime>>(
    initialRuntime,
  );
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState<number | null>(null);

  useEffect(() => {
    setScene(initialScene);
    setStatus(initialScene ? "ready" : "idle");
  }, [initialScene]);

  const startRun = useCallback(() => {
    if (!sessionId) return;
    let cancelled = false;
    setStatus("running");
    setError(null);
    setRuntime(initialRuntime());

    const handle = (ev: AgentEvent) => {
      if (cancelled) return;
      switch (ev.type) {
        case "agent_start": {
          const key = ev.agent as AgentKey;
          setRuntime((prev) => {
            const next = { ...prev };
            for (const k of AGENT_ORDER) {
              if (next[k].status === "active")
                next[k] = { ...next[k], status: "done" };
            }
            if (next[key]) next[key] = { ...next[key], status: "active" };
            return next;
          });
          break;
        }
        case "task_complete": {
          const key = (ev.agent ?? "") as AgentKey;
          setRuntime((prev) =>
            prev[key]
              ? {
                  ...prev,
                  [key]: {
                    ...prev[key],
                    status: "done",
                    preview: ev.preview ?? prev[key].preview,
                  },
                }
              : prev,
          );
          break;
        }
        case "scene_ready":
          setScene(ev.scene);
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

    runSceneStream(sessionId, handle)
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
  }, [sessionId]);

  const canStart = !!sessionId && outlineReady && status !== "running";

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-lg border border-hairline bg-surface px-4 py-3 flex items-center gap-3">
        <Cube size={16} weight="duotone" className="text-cinnabar shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-[13px] text-white">
            {scene
              ? "Scene is ready. Rebuild from the latest outline if you've edited it."
              : "Generate the Excalidraw scene for this outline."}
          </p>
          <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-mist mt-0.5">
            ws_agents_scene · 2 agents · sequential
            {cost !== null ? ` · $${cost.toFixed(3)}` : ""}
          </p>
        </div>
        <Button
          size="sm"
          variant={scene ? "secondary" : "primary"}
          onClick={startRun}
          disabled={!canStart}
          title={
            !canStart
              ? "Scene crew needs a finished outline before it can run"
              : undefined
          }
        >
          {scene ? (
            <ArrowsClockwise size={12} weight="bold" />
          ) : status === "running" ? (
            <Sparkle size={12} weight="duotone" className="animate-pulse" />
          ) : (
            <Lightning size={12} weight="bold" />
          )}
          {scene
            ? "Rebuild scene"
            : status === "running"
              ? "Building scene…"
              : "Build scene"}
        </Button>
      </div>

      {(status === "running" || status === "failed") && (
        <div className="rounded-lg border border-hairline bg-surface p-3 space-y-2">
          {AGENT_ORDER.map((key) => {
            const r = runtime[key];
            return (
              <div
                key={key}
                className={cn(
                  "flex items-start gap-2 px-2 py-1.5 rounded-md",
                  r.status === "active" && "bg-white/[0.04]",
                )}
              >
                <span
                  className={cn(
                    "inline-block h-1.5 w-1.5 rounded-full mt-1.5 shrink-0",
                    r.status === "active" && "bg-cinnabar animate-pulse",
                    r.status === "done" && "bg-white/40",
                    r.status === "idle" && "bg-white/10",
                  )}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[12.5px] text-white">
                      {AGENT_LABEL[key]}
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-mist">
                      {r.status}
                    </span>
                  </div>
                  <p className="font-mono text-[11px] text-mist leading-[1.5] truncate">
                    {r.preview || AGENT_HINT[key]}
                  </p>
                </div>
              </div>
            );
          })}
          {status === "failed" && error ? (
            <div className="flex items-start gap-2 px-2 py-1.5 rounded-md bg-cinnabar/10 border border-cinnabar/20">
              <Warning size={12} weight="fill" className="text-cinnabar mt-0.5" />
              <p className="font-mono text-[11px] text-cinnabar leading-[1.5] flex-1">
                {error}
              </p>
            </div>
          ) : null}
        </div>
      )}

      {scene && sessionId ? (
        <Suspense
          fallback={
            <div className="rounded-lg border border-hairline bg-surface px-4 py-6 font-mono text-[11.5px] text-mist">
              loading canvas…
            </div>
          }
        >
          <SceneView scene={scene} sessionId={sessionId} />
        </Suspense>
      ) : null}
    </div>
  );
}

export default SceneRunPanel;
