import { useCallback, useEffect, useState } from "react";
import {
  Sparkle,
  Lightning,
  Warning,
  ArrowsClockwise,
  ArrowSquareOut,
  Image as ImageIcon,
  Eye,
  Spinner,
  CheckCircle,
  TextAa,
} from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/cn";
import {
  publishScene,
  runSceneStream,
  saveSceneSkeleton,
  type AgentEvent,
  type Scene,
  type SceneSkeletonElement,
} from "../../lib/agents";

// Excalidraw 0.18 only exposes bundled fontFamily ints; labels follow the
// product copy while mapping to the nearest renderer preset.
const FONT_OPTIONS: { value: number | null; label: string }[] = [
  { value: null, label: "Handmade" },
  { value: 9, label: "Arial" }, // Liberation Sans — neutral sans
  { value: 1, label: "Times Roman" }, // Virgil — closest bundled serif mood
  { value: 2, label: "SF Pro" }, // Helvetica stack → SF on Apple
];

const FONT_STORAGE_KEY = "ladder:scene:font_family";

const ALLOWED_FONT_IDS = new Set(
  FONT_OPTIONS.map((o) => o.value).filter((v): v is number => typeof v === "number"),
);

function applyFontFamilyToScene(scene: Scene, fontFamily: number | null): Scene {
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
      const lbl = { ...labelObj };
      if (fontFamily === null) {
        delete lbl.fontFamily;
      } else {
        lbl.fontFamily = fontFamily;
      }
      next.label = lbl;
    }

    if (fontFamily === null) {
      delete next.fontFamily;
    } else {
      next.fontFamily = fontFamily;
    }
    return next;
  });
  return { ...scene, elements };
}

function loadStoredFont(): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(FONT_STORAGE_KEY);
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || !ALLOWED_FONT_IDS.has(n)) return null;
  return n;
}

function storeFont(value: number | null): void {
  if (typeof window === "undefined") return;
  if (value === null) window.localStorage.removeItem(FONT_STORAGE_KEY);
  else window.localStorage.setItem(FONT_STORAGE_KEY, String(value));
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
};

/**
 * Bottom-of-left-pane action row.
 *
 * Pre-build:   [Approve and build scene →]
 * Post-build:  [Preview canvas] [Open in Excalidraw] [Regenerate scene] [Generate thumbnail]
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
}: Props) {
  const [scene, setScene] = useState<Scene | null>(initialScene);
  const [status, setStatus] = useState<Status>(initialScene ? "ready" : "idle");
  const [runtime, setRuntime] = useState<Record<AgentKey, AgentRuntime>>(
    initialRuntime,
  );
  const [error, setError] = useState<string | null>(null);
  const [cost, setCost] = useState<number | null>(null);
  const [openingExcalidraw, setOpeningExcalidraw] = useState(false);
  const [fontFamily, setFontFamily] = useState<number | null>(loadStoredFont);
  const [applyingFont, setApplyingFont] = useState(false);

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
          onSceneReady?.(ev.scene);
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
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId, sceneAccentHex, fontFamily, onSceneReady]);

  const regenerateTypography = useCallback(async () => {
    if (!sessionId || !scene) return;
    setApplyingFont(true);
    setError(null);
    try {
      const next = applyFontFamilyToScene(structuredClone(scene), fontFamily);
      await saveSceneSkeleton(sessionId, next);
      setScene(next);
      onSceneReady?.(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setApplyingFont(false);
    }
  }, [sessionId, scene, fontFamily, onSceneReady]);

  const onFontChange = useCallback((value: number | null) => {
    setFontFamily(value);
    storeFont(value);
  }, []);

  const onOpenInExcalidraw = useCallback(async () => {
    if (!scene || !sessionId) return;
    setOpeningExcalidraw(true);
    setError(null);
    try {
      // Inflate to the standard Excalidraw envelope server-side so the
      // shareable URL points at a fully-formed file. The convert step
      // happens inside SceneView in the modal — for the action button,
      // we hand the skeleton through and the publish endpoint accepts
      // either shape.
      const { convertToExcalidrawElements } = await import(
        "@excalidraw/excalidraw"
      );
      const elements = convertToExcalidrawElements(
        scene.elements as unknown as Parameters<
          typeof convertToExcalidrawElements
        >[0],
        { regenerateIds: false },
      );
      const envelope = {
        type: "excalidraw" as const,
        version: 2,
        source: "https://excalidraw.com",
        elements,
        appState: {
          viewBackgroundColor: scene.background_color,
          gridSize: null,
        },
        files: (scene.files ?? {}) as Record<string, unknown>,
      };
      const { excalidraw_url } = await publishScene(
        sessionId,
        envelope as unknown as Record<string, unknown>,
      );
      window.open(excalidraw_url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setOpeningExcalidraw(false);
    }
  }, [scene, sessionId]);

  const canStart = !!sessionId && outlineReady && status !== "running" && !applyingFont;
  const isRunning = status === "running";
  const hidePreviewCluster = isRunning || applyingFont;

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
            <FontPicker value={fontFamily} onChange={onFontChange} disabled={hidePreviewCluster} />
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
              <FontPicker
                value={fontFamily}
                onChange={onFontChange}
                disabled={hidePreviewCluster}
              />
              {!hidePreviewCluster ? (
                <>
                  <FooterIconBtn
                    icon={Eye}
                    label="Preview"
                    onClick={onPreview}
                    title="Preview the canvas"
                  />
                  <FooterIconBtn
                    icon={openingExcalidraw ? Spinner : ArrowSquareOut}
                    label={openingExcalidraw ? "Uploading…" : "Open in Excalidraw"}
                    onClick={onOpenInExcalidraw}
                    disabled={openingExcalidraw}
                    spinning={openingExcalidraw}
                    title="Open scene in excalidraw.com"
                  />
                </>
              ) : null}
              <FooterIconBtn
                icon={applyingFont ? Spinner : ArrowsClockwise}
                label={applyingFont ? "Applying…" : "Regenerate"}
                onClick={regenerateTypography}
                disabled={!canStart}
                spinning={applyingFont}
                title="Apply the selected font to this scene (layout unchanged)"
              />
              <FooterIconBtn
                icon={ImageIcon}
                label="Thumbnail"
                disabled
                muted
                title="Thumbnail generator ships in a follow-up pass"
              />
            </div>
          </>
        )}
      </div>

      {/* Run progress + errors */}
      {applyingFont ? (
        <p className="font-mono text-[11px] text-mist px-1">Updating typography…</p>
      ) : null}
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

// ─── Font picker ──────────────────────────────────────────────────────────

/**
 * Native <select> wrapped in a chip-style label. Excalidraw 0.18 only ships
 * bundled font integers — labels are founder-facing; see FONT_OPTIONS mapping.
 */
function FontPicker({
  value,
  onChange,
  disabled,
}: {
  value: number | null;
  onChange: (v: number | null) => void;
  disabled?: boolean;
}) {
  const active = FONT_OPTIONS.find((o) => o.value === value) ?? FONT_OPTIONS[0];
  return (
    <label
      className={cn(
        "relative inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md",
        "border border-hairline bg-white/[0.03] text-white/85",
        "hover:bg-white/[0.07] hover:text-white hover:border-hairline-strong",
        "transition-colors",
        disabled ? "opacity-40 pointer-events-none" : "cursor-pointer",
      )}
      title={`Scene font · ${active.label}`}
    >
      <TextAa size={11} weight="bold" className="shrink-0" />
      <span className="text-[12px] font-medium font-sans whitespace-nowrap">
        {active.label}
      </span>
      <select
        value={value === null ? "default" : String(value)}
        onChange={(e) => {
          const raw = e.target.value;
          onChange(raw === "default" ? null : Number(raw));
        }}
        disabled={disabled}
        aria-label="Scene font"
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
      >
        {FONT_OPTIONS.map((o) => (
          <option key={String(o.value)} value={o.value === null ? "default" : String(o.value)}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
