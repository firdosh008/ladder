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
  TextAa,
} from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/cn";
import {
  generateDiagramFromScript,
  saveSceneSkeleton,
  type Scene,
  type SceneSkeletonElement,
} from "../../lib/agents";

const FONT_OPTIONS: { value: number | null; label: string }[] = [
  { value: null, label: "Handmade" },
  { value: 9, label: "Arial" },
  { value: 1, label: "Times Roman" },
  { value: 2, label: "SF Pro" },
];

const FONT_STORAGE_KEY = "ladder:scene:font_family";

const ALLOWED_FONT_IDS = new Set(
  FONT_OPTIONS.map((o) => o.value).filter((v): v is number => typeof v === "number"),
);

function inferTypographyFontFromScene(scene: Scene | null): number | null {
  if (!scene?.elements?.length) return null;
  for (const el of scene.elements) {
    if (typeof el.fontFamily === "number") return el.fontFamily;
    const lbl = el.label as { fontFamily?: number } | null | undefined;
    if (lbl != null && typeof lbl.fontFamily === "number") return lbl.fontFamily;
  }
  return null;
}

function applyFontFamilyToScene(scene: Scene, fontFamily: number | null): Scene {
  const elements = scene.elements.map((el: SceneSkeletonElement) => {
    const labelObj = el.label;
    const hasLabel =
      labelObj != null &&
      typeof labelObj === "object" &&
      String(labelObj.text ?? "").trim().length > 0;
    const hasTextField = typeof el.text === "string" && el.text.trim().length > 0;
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

type Status = "idle" | "running" | "ready" | "failed";

type Props = {
  sessionId: string | null;
  diagramScript: string;
  initialScene: Scene | null;
  outlineReady: boolean;
  onPreview: () => void;
  onSceneReady?: (scene: Scene) => void;
};

/** ``POST /generate-diagram`` plus scene typography controls · Preview opens the modal viewer. */
export function SceneRunPanel({
  sessionId,
  diagramScript,
  initialScene,
  outlineReady,
  onPreview,
  onSceneReady,
}: Props) {
  const [scene, setScene] = useState<Scene | null>(initialScene);
  const [status, setStatus] = useState<Status>(initialScene ? "ready" : "idle");
  const [error, setError] = useState<string | null>(null);
  const [fontFamily, setFontFamily] = useState<number | null>(loadStoredFont);
  const [fontCommittedToScene, setFontCommittedToScene] = useState<number | null>(
    () => inferTypographyFontFromScene(initialScene),
  );
  const [applyingFont, setApplyingFont] = useState(false);

  useEffect(() => {
    setScene(initialScene);
    setStatus(initialScene ? "ready" : "idle");
    setFontCommittedToScene(inferTypographyFontFromScene(initialScene));
  }, [initialScene]);

  const scriptOk = diagramScript.trim().length >= 8;

  const startRun = useCallback(async () => {
    if (!sessionId || !scriptOk) return;
    setStatus("running");
    setError(null);
    try {
      const res = await generateDiagramFromScript({
        script: diagramScript,
        session_id: sessionId,
      });
      let next = res.json;
      if ((fontFamily ?? null) !== null) {
        next = applyFontFamilyToScene(structuredClone(next), fontFamily);
      }
      setScene(next);
      setFontCommittedToScene(fontFamily ?? null);
      setStatus("ready");
      onSceneReady?.(next);
      if (typeof res.diagram_url === "string" && res.diagram_url) {
        console.info("Diagram PNG:", res.diagram_url);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("failed");
    }
  }, [sessionId, diagramScript, scriptOk, fontFamily, onSceneReady]);

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
      void startRun();
    }
  }, [sessionId, scene, fontFamily, fontCommittedToScene, regenerateTypography, startRun]);

  const fontPickerDiffersFromCanvas = (fontFamily ?? null) !== (fontCommittedToScene ?? null);

  const onFontChange = useCallback((value: number | null) => {
    setFontFamily(value);
    storeFont(value);
  }, []);

  const canStart =
    !!sessionId && outlineReady && scriptOk && status !== "running" && !applyingFont;
  const isRunning = status === "running";
  const hidePreviewCluster = isRunning || applyingFont;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-3 min-h-[28px]">
          {!scene ? (
            <>
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span
                  className={cn(
                    "inline-block h-1.5 w-1.5 rounded-full shrink-0",
                    outlineReady && scriptOk ? "bg-cinnabar" : "bg-white/20",
                  )}
                />
                <p className="text-[12.5px] text-white/85 truncate">
                  {outlineReady && scriptOk
                    ? "Outline + script ready — generate to draw via Claude + MCP."
                    : outlineReady
                      ? "Waiting for script text."
                      : "Waiting on the outline."}
                </p>
              </div>
              <FontPicker value={fontFamily} onChange={onFontChange} disabled={hidePreviewCluster} />
              <Button
                size="sm"
                variant="primary"
                onClick={() => void startRun()}
                disabled={!canStart}
                title={
                  !canStart
                    ? "Need session, outline, and script before building the board"
                    : undefined
                }
                className="shrink-0"
              >
                {isRunning ? (
                  <Sparkle size={11} weight="duotone" className="animate-pulse" />
                ) : (
                  <Lightning size={11} weight="bold" />
                )}
                {isRunning ? "Drawing…" : "Generate whiteboard"}
              </Button>
            </>
          ) : (
            <>
              <div className="flex items-center gap-1.5 min-w-0 mr-auto">
                <CheckCircle size={11} weight="fill" className="text-cinnabar shrink-0" />
                <span className="text-[12.5px] text-white/90 truncate">Diagram ready</span>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <FontPicker
                  value={fontFamily}
                  onChange={onFontChange}
                  disabled={hidePreviewCluster}
                />
                {!hidePreviewCluster ? (
                  <FooterIconBtn
                    icon={Eye}
                    label="Preview"
                    onClick={onPreview}
                    title="Preview the saved scene"
                  />
                ) : null}
                <FooterIconBtn
                  icon={applyingFont || isRunning ? Spinner : ArrowsClockwise}
                  label={
                    applyingFont ? "Applying…" : isRunning ? "Re-drawing…" : "Regenerate"
                  }
                  onClick={handleRegenerate}
                  disabled={!canStart}
                  spinning={applyingFont || isRunning}
                  title={
                    fontPickerDiffersFromCanvas
                      ? "Apply the selected font only (layout unchanged)"
                      : "Rebuild the board from your script via Claude + MCP"
                  }
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

        {applyingFont ? (
          <p className="font-mono text-[11px] text-mist px-1">Updating typography…</p>
        ) : null}
        {isRunning ? (
          <p className="font-mono text-[11px] text-mist px-1">
            Claude is driving the Excalidraw MCP tools on the server — use Preview when the
            diagram is ready to inspect it.
          </p>
        ) : null}

        {status === "failed" && error ? (
          <div className="flex items-start gap-2 px-2 py-2 rounded-md bg-cinnabar/10 border border-cinnabar/20">
            <Warning size={14} weight="fill" className="text-cinnabar mt-0.5 shrink-0" />
            <p className="font-mono text-[11px] text-cinnabar leading-[1.5]">{error}</p>
          </div>
        ) : null}
        {error && status !== "failed" ? (
          <p className="font-mono text-[11px] text-cinnabar">{error}</p>
        ) : null}
    </div>
  );
}

export default SceneRunPanel;

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
        muted &&
          "bg-transparent border-transparent text-mist hover:text-mist hover:bg-transparent hover:border-transparent",
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
