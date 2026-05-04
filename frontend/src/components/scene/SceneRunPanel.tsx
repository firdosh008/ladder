import { useCallback, useEffect, useState } from "react";
import {
  Sparkle,
  Lightning,
  Warning,
  ArrowsClockwise,
  Image as ImageIcon,
  Eye,
  Spinner,
  CheckCircle,
} from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/cn";
import {
  runSceneStream,
  saveSceneSkeleton,
  type AgentEvent,
  type Scene,
  type SceneSkeletonElement,
} from "../../lib/agents";

// Excalidraw bundled fontFamily integers — each ID renders a distinct typeface:
//   1 = Virgil      (hand-drawn / sketch)
//   2 = Helvetica   (clean sans-serif; renders as SF Pro on macOS)
//   3 = Cascadia    (monospace / code)
//   9 = Liberation  (neutral Arial-style sans)
// null omitted = designer default (usually Virgil/Excalifont)
const FONT_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: "Handmade" },   // Virgil — sketchy, hand-drawn
  { value: 2, label: "SF Pro" },     // Helvetica → SF Pro on Apple
  { value: 3, label: "Mono" },       // Cascadia Code — monospaced
  { value: 9, label: "Arial" },      // Liberation Sans — neutral sans
];

const FONT_STORAGE_KEY = "ladder:scene:font_family";

const ALLOWED_FONT_IDS = new Set(FONT_OPTIONS.map((o) => o.value));

function inferTypographyFontFromScene(scene: Scene | null): number | null {
  if (!scene?.elements?.length) return null;
  for (const el of scene.elements) {
    if (typeof el.fontFamily === "number") return el.fontFamily;
    const lbl = el.label as { fontFamily?: number } | null | undefined;
    if (lbl != null && typeof lbl.fontFamily === "number") return lbl.fontFamily;
  }
  return null;
}

function applyFontFamilyToScene(scene: Scene, fontFamily: number): Scene {
  const elements = scene.elements.map((el: SceneSkeletonElement) => {
    const labelObj = el.label;
    const hasLabel =
      labelObj != null &&
      typeof labelObj === "object" &&
      String(labelObj.text ?? "").trim().length > 0;
    const hasTextField =
      typeof el.text === "string" && el.text.trim().length > 0;
    const isTextEl = el.type === "text";
    if (!isTextEl && !hasLabel && !hasTextField) return el;

    const next: SceneSkeletonElement = { ...el };

    if (hasLabel && labelObj) {
      next.label = { ...labelObj, fontFamily };
    }
    next.fontFamily = fontFamily;
    return next;
  });
  return { ...scene, elements };
}

function loadStoredFont(): number {
  if (typeof window === "undefined") return FONT_OPTIONS[0].value;
  const raw = window.localStorage.getItem(FONT_STORAGE_KEY);
  if (!raw) return FONT_OPTIONS[0].value;
  const n = Number(raw);
  if (!Number.isFinite(n) || !ALLOWED_FONT_IDS.has(n)) return FONT_OPTIONS[0].value;
  return n;
}

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
  /** Open the scene preview modal in the parent. */
  onPreview: () => void;
  /** Same accent as the Studio brand pill; passed through to the scene WS. */
  sceneAccentHex?: string | null;
  /** Lift `scene_ready` into studio state so Preview / modal see the canvas. */
  onSceneReady?: (scene: Scene) => void;
  /** Signal scene websocket run started/finished — parent opens live MCP modal while active. */
  onDiagramRunActive?: (active: boolean) => void;
};

/**
 * Bottom-of-left-pane action row.
 *
 * Pre-build:   [Approve and build scene →]
 * Post-build:  [Preview canvas] [Open in Excalidraw] [Regenerate scene] [Thumbnail preview]
 *
 * The inline canvas now lives behind the Preview button (rendered in a
 * modal by the parent so the cramped 65%-wide pane doesn't try to host
 * a full Excalidraw viewer).
 */
export function SceneRunPanel({
  sessionId,
  initialScene,
  outlineReady,
  onPreview,
  sceneAccentHex,
  onSceneReady,
  onDiagramRunActive,
}: Props) {
  const [scene, setScene] = useState<Scene | null>(initialScene);
  const [status, setStatus] = useState<Status>(initialScene ? "ready" : "idle");
  const [runtime, setRuntime] = useState<Record<AgentKey, AgentRuntime>>(
    initialRuntime,
  );
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState<number | null>(null);
  const [fontFamily] = useState<number>(loadStoredFont);
  const [fontCommittedToScene, setFontCommittedToScene] = useState<number | null>(
    () => inferTypographyFontFromScene(initialScene),
  );
  const [diagramProgress, setDiagramProgress] = useState<string | null>(null);
  /** MCP / live-canvas stream emits diagram_* events, not layout_planner / element_designer. */
  const [liveCanvasDiagramRun, setLiveCanvasDiagramRun] = useState(false);
  const [applyingFont, setApplyingFont] = useState(false);

  useEffect(() => {
    setScene(initialScene);
    setStatus(initialScene ? "ready" : "idle");
    setFontCommittedToScene(inferTypographyFontFromScene(initialScene));
  }, [initialScene]);

  const startRun = useCallback(() => {
    if (!sessionId) return;
    let cancelled = false;
    let signaledLiveModal = false;
    const signalLiveCanvasModal = () => {
      if (signaledLiveModal || !onDiagramRunActive) return;
      signaledLiveModal = true;
      onDiagramRunActive(true);
    };

    setStatus("running");
    setError(null);
    setDiagramProgress(null);
    setLiveCanvasDiagramRun(false);
    setRuntime(initialRuntime());

    const handle = (ev: AgentEvent) => {
      if (cancelled) return;
      switch (ev.type) {
        case "agent_start": {
          if (ev.agent === "diagram_agent") {
            setLiveCanvasDiagramRun(true);
            signalLiveCanvasModal();
            break;
          }
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
          setFontCommittedToScene(inferTypographyFontFromScene(ev.scene));
          setDiagramProgress(null);
          onSceneReady?.(ev.scene);
          break;
        case "diagram_draft":
          setLiveCanvasDiagramRun(true);
          signalLiveCanvasModal();
          setDiagramProgress(
            ev.phase === "drawn"
              ? `Live canvas · drawn (${ev.element_count ?? "?"} elements)`
              : ev.phase === "waiting_live_viewer"
                ? "Live canvas · connecting headless viewer…"
                : `Live canvas · ${ev.phase}`,
          );
          break;
        case "diagram_iteration":
          setLiveCanvasDiagramRun(true);
          signalLiveCanvasModal();
          setDiagramProgress(
            [
              "Live canvas ·",
              ev.phase,
              ev.iteration != null ? `(round ${ev.iteration})` : "",
              ev.layout_hint ? `· ${ev.layout_hint.replace(/_/g, " ")}` : "",
            ]
              .filter(Boolean)
              .join(" "),
          );
          break;
        case "diagram_complete":
          setLiveCanvasDiagramRun(true);
          signalLiveCanvasModal();
          setDiagramProgress(`Live canvas · QA complete (${ev.iterations} iteration${ev.iterations === 1 ? "" : "s"})`);
          break;
        case "usage":
          setCost(ev.token_usage.cost_usd);
          break;
        case "error":
          setError(ev.message);
          setDiagramProgress(null);
          break;
        default:
          break;
      }
    };

    runSceneStream(
      sessionId,
      handle,
      sceneAccentHex ?? undefined,
      fontFamily ?? undefined,
    )
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
      })
      .finally(() => {
        if (!cancelled) onDiagramRunActive?.(false);
      });
  }, [sessionId, sceneAccentHex, fontFamily, onSceneReady, onDiagramRunActive]);

  const regenerateTypography = useCallback(async () => {
    if (!sessionId || !scene) return;
    setApplyingFont(true);
    setError(null);
    try {
      const next = applyFontFamilyToScene(structuredClone(scene), fontFamily);
      await saveSceneSkeleton(sessionId, next);
      setScene(next);
      setFontCommittedToScene(fontFamily ?? null);
      onSceneReady?.(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setApplyingFont(false);
    }
  }, [sessionId, scene, fontFamily, onSceneReady]);

  const handleRegenerate = useCallback(() => {
    if (!sessionId || !scene) return;
    const picker = fontFamily ?? null;
    const committed = fontCommittedToScene ?? null;
    if (picker !== committed) {
      void regenerateTypography();
    } else {
      startRun();
    }
  }, [
    sessionId,
    scene,
    fontFamily,
    fontCommittedToScene,
    regenerateTypography,
    startRun,
  ]);

  const fontPickerDiffersFromCanvas = (fontFamily ?? null) !== (fontCommittedToScene ?? null);

  const canStart = !!sessionId && outlineReady && status !== "running" && !applyingFont;
  const isRunning = status === "running";
  /** After scene_ready we have a drawable scene even if the WS is still draining usage events. */
  const hidePreviewCluster = applyingFont || (isRunning && !scene);

  return (
    <div className="flex flex-col gap-2">
      {/* Action row — pinned at the bottom of the left pane */}
      <div className="flex items-center gap-3 min-h-[28px]">
        {!scene ? (
          <>
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <span
                className={cn(
                  "inline-block h-1.5 w-1.5 rounded-full shrink-0",
                  outlineReady ? "bg-cinnabar" : "bg-white/20",
                )}
              />
              <p className="text-[12.5px] text-white/85 truncate">
                {outlineReady
                  ? "Outline ready — build the scene when you're happy."
                  : "Waiting on the outline."}
              </p>
              {cost !== null ? (
                <span className="font-mono text-[10.5px] text-mist shrink-0">
                  ${cost.toFixed(3)}
                </span>
              ) : null}
            </div>
            <Button
              size="sm"
              variant="primary"
              onClick={startRun}
              disabled={!canStart}
              title={
                !canStart
                  ? "Scene crew needs a finished outline before it can run"
                  : undefined
              }
              className="shrink-0"
            >
              {isRunning ? (
                <Sparkle size={11} weight="duotone" className="animate-pulse" />
              ) : (
                <Lightning size={11} weight="bold" />
              )}
              {isRunning ? "Building…" : "Approve & build scene"}
            </Button>
          </>
        ) : (
          <>
            <div className="flex items-center gap-1.5 min-w-0 mr-auto">
              <CheckCircle size={11} weight="fill" className="text-cinnabar shrink-0" />
              <span className="text-[12.5px] text-white/90 truncate">Scene ready</span>
              {cost !== null ? (
                <span className="font-mono text-[10.5px] text-mist shrink-0">
                  · ${cost.toFixed(3)}
                </span>
              ) : null}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              {!hidePreviewCluster ? (
                <>
                  <FooterIconBtn
                    icon={Eye}
                    label="Preview"
                    onClick={onPreview}
                    title="Preview the canvas"
                  />
                  {/* <FooterIconBtn
                    icon={openingExcalidraw ? Spinner : ArrowSquareOut}
                    label={openingExcalidraw ? "Uploading…" : "Open in Excalidraw"}
                    onClick={onOpenInExcalidraw}
                    disabled={openingExcalidraw}
                    spinning={openingExcalidraw}
                    title="Open scene in excalidraw.com"
                  /> */}
                </>
              ) : null}
              <FooterIconBtn
                icon={applyingFont || isRunning ? Spinner : ArrowsClockwise}
                label={
                  applyingFont ? "Applying…" : isRunning ? "Rebuilding…" : "Regenerate"
                }
                onClick={handleRegenerate}
                disabled={!canStart}
                spinning={applyingFont || isRunning}
                title={
                  fontPickerDiffersFromCanvas
                    ? "Apply the selected font only (layout unchanged)"
                    : "Rebuild the full scene from the outline using the current font"
                }
              />
              <FooterIconBtn
                icon={ImageIcon}
                label="Generate Thumbnail"
                onClick={onPreview}
                disabled={hidePreviewCluster}
                title="Generate Thumbnail of the scene"
              />
            </div>
          </>
        )}
      </div>

      {/* Run progress + errors */}
      {diagramProgress ? (
        <p className="font-mono text-[11px] text-cinnabar/90 px-1 animate-pulse">
          {diagramProgress}
        </p>
      ) : null}
      {applyingFont ? (
        <p className="font-mono text-[11px] text-mist px-1">Updating typography…</p>
      ) : isRunning && scene && !liveCanvasDiagramRun ? (
        <p className="font-mono text-[11px] text-mist px-1">Rebuilding scene from outline…</p>
      ) : null}
      {(status === "running" || status === "failed") && !liveCanvasDiagramRun && (
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

      {error && status !== "failed" ? (
        <p className="font-mono text-[11px] text-cinnabar">{error}</p>
      ) : null}
    </div>
  );
}

export default SceneRunPanel;

// ─── Footer button ────────────────────────────────────────────────────────

/**
 * Compact secondary button used in the sticky footer cluster. Smaller than
 * the design-system Button, optical density tuned for an icon + 1-word
 * label. Hover lifts the chrome so the cluster reads as a tight group.
 */
function FooterIconBtn({
  icon: Icon,
  label,
  onClick,
  disabled,
  muted,
  spinning,
  title,
}: {
  icon: React.ElementType;
  label: string;
  onClick?: () => void;
  disabled?: boolean;
  muted?: boolean;
  spinning?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        "inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md",
        "text-[12px] font-medium font-sans whitespace-nowrap",
        "border border-hairline bg-white/[0.03] text-white/85",
        "hover:bg-white/[0.07] hover:text-white hover:border-hairline-strong",
        "transition-colors",
        "disabled:opacity-40 disabled:pointer-events-none",
        muted && "bg-transparent border-transparent text-mist hover:text-mist hover:bg-transparent hover:border-transparent",
      )}
    >
      <Icon
        size={11}
        weight="bold"
        className={cn("shrink-0", spinning && "animate-spin")}
      />
      <span>{label}</span>
    </button>
  );
}
