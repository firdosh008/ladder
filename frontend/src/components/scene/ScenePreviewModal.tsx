import { Suspense, lazy, useCallback, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X, TextAa } from "@phosphor-icons/react";
import { cn } from "../../lib/cn";
import { saveSceneSkeleton, type Scene, type SceneSkeletonElement } from "../../lib/agents";

const SceneView = lazy(() => import("./SceneView"));

// ─── Font helpers ───────────────────────────────────────────────────────────

const FONT_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: "Handmade" },
  { value: 2, label: "SF Pro" },
  { value: 3, label: "Mono" },
  { value: 9, label: "Arial" },
];

const FONT_STORAGE_KEY = "ladder:scene:font_family";
const ALLOWED_FONT_IDS = new Set(FONT_OPTIONS.map((o) => o.value));

function loadStoredFont(): number {
  if (typeof window === "undefined") return FONT_OPTIONS[0].value;
  const raw = window.localStorage.getItem(FONT_STORAGE_KEY);
  if (!raw) return FONT_OPTIONS[0].value;
  const n = Number(raw);
  if (!Number.isFinite(n) || !ALLOWED_FONT_IDS.has(n)) return FONT_OPTIONS[0].value;
  return n;
}

function storeFont(value: number): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(FONT_STORAGE_KEY, String(value));
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

// ─── FontPicker ─────────────────────────────────────────────────────────────

function FontPicker({
  value,
  onChange,
  disabled,
}: {
  value: number;
  onChange: (v: number) => void;
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
        value={String(value)}
        onChange={(e) => {
          onChange(Number(e.target.value));
        }}
        disabled={disabled}
        aria-label="Scene font"
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
      >
        {FONT_OPTIONS.map((o) => (
          <option key={String(o.value)} value={String(o.value)}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scene: Scene | null;
  sessionId: string | null;
  /** Backend MCP canvas URL (e.g. http://127.0.0.1:3000) — iframe shows live drawing during generation. */
  liveCanvasUrl?: string;
  /** True while scene WS run is in progress — switches modal body to live iframe when URL is set. */
  liveCanvasDuringRun?: boolean;
  /** Called when font changes are applied to the scene so the parent updates its state. */
  onSceneChange?: (scene: Scene) => void;
};

/**
 * Scene preview dialog: optional **live MCP iframe** while the backend draws,
 * then read-only ``SceneView`` from persisted scene JSON when idle.
 */
export function ScenePreviewModal({
  open,
  onOpenChange,
  scene,
  sessionId,
  liveCanvasUrl,
  liveCanvasDuringRun = false,
  onSceneChange,
}: Props) {
  const trimmedLiveUrl = liveCanvasUrl?.trim() ?? "";
  const showLive = !!trimmedLiveUrl && liveCanvasDuringRun && open;

  const showSceneSnapshot =
    !!scene &&
    !!sessionId &&
    (!liveCanvasDuringRun || !trimmedLiveUrl);

  const [fontFamily, setFontFamily] = useState<number>(loadStoredFont);
  const [applyingFont, setApplyingFont] = useState(false);
  const [fontError, setFontError] = useState<string | null>(null);

  const onFontChange = useCallback(
    async (value: number) => {
      setFontFamily(value);
      storeFont(value);
      if (!scene || !sessionId) return;
      setApplyingFont(true);
      setFontError(null);
      try {
        const next = applyFontFamilyToScene(structuredClone(scene), value);
        await saveSceneSkeleton(sessionId, next);
        onSceneChange?.(next);
      } catch (err) {
        setFontError(err instanceof Error ? err.message : String(err));
      } finally {
        setApplyingFont(false);
      }
    },
    [scene, sessionId, onSceneChange],
  );

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            "fixed inset-0 z-40 bg-black/70 backdrop-blur-sm",
            "data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-out",
          )}
        />
        <Dialog.Content
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[min(1200px,94vw)] max-h-[90vh]",
            "-translate-x-1/2 -translate-y-1/2",
            "rounded-xl border border-hairline bg-night shadow-2xl",
            "flex flex-col overflow-hidden",
            "data-[state=open]:animate-scale-in data-[state=closed]:animate-scale-out",
          )}
        >
          <header className="flex items-center justify-between gap-3 px-4 h-12 border-b border-hairline shrink-0">
            <div className="flex flex-col gap-0.5 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <Dialog.Title className="font-sans font-semibold text-[13.5px] text-white">
                  {showLive ? "Live MCP canvas" : "Scene preview"}
                </Dialog.Title>
                <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-cinnabar">
                  {showLive ? "building · websocket sync" : "read-only · open in excalidraw to edit"}
                </span>
              </div>
              {showLive ? (
                <p className="font-mono text-[10px] text-mist truncate">
                  Same view as the headless exporter — shapes appear as the backend draws them.
                </p>
              ) : null}
              {fontError ? (
                <p className="font-mono text-[10px] text-cinnabar truncate">{fontError}</p>
              ) : null}
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {showSceneSnapshot ? (
                <FontPicker
                  value={fontFamily}
                  onChange={onFontChange}
                  disabled={applyingFont}
                />
              ) : null}
              <Dialog.Close
                aria-label="Close preview"
                className={cn(
                  "inline-flex items-center justify-center h-8 w-8 rounded-md shrink-0",
                  "text-mist hover:text-white hover:bg-white/[0.04] transition-colors",
                )}
              >
                <X size={14} weight="bold" />
              </Dialog.Close>
            </div>
          </header>
          <div
            className={cn(
              "flex-1 min-h-0",
              showLive ? "p-0 bg-black/40" : "overflow-y-auto p-4",
            )}
          >
            {showLive ? (
              <iframe
                title="Live Excalidraw MCP canvas"
                src={`${trimmedLiveUrl.replace(/\/$/, "")}/`}
                className="w-full min-h-[min(720px,72vh)] h-[72vh] border-0"
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
              />
            ) : liveCanvasDuringRun && !trimmedLiveUrl ? (
              <div className="rounded-lg border border-hairline bg-surface px-4 py-6 font-mono text-[11.5px] text-mist leading-relaxed">
                <p className="text-white/90 mb-2">Live canvas URL not configured.</p>
                <p>
                  Set{" "}
                  <code className="text-cinnabar/90">VITE_EXCALIDRAW_CANVAS_URL</code> in{" "}
                  <code className="text-white/70">frontend/.env</code> (same host/port as the MCP
                  canvas, e.g. <code className="text-white/70">http://127.0.0.1:3000</code>) and
                  reload the app to watch the diagram draw here.
                </p>
              </div>
            ) : showSceneSnapshot ? (
              <Suspense
                fallback={
                  <div className="rounded-lg border border-hairline bg-surface px-4 py-6 font-mono text-[11.5px] text-mist">
                    loading canvas…
                  </div>
                }
              >
                <SceneView scene={scene} sessionId={sessionId} />
              </Suspense>
            ) : (
              <p className="font-mono text-[11.5px] text-mist">
                no scene yet
              </p>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
