import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Excalidraw,
  convertToExcalidrawElements,
} from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";
import {
  DownloadSimple,
  ArrowSquareOut,
  Spinner,
  Copy,
  Check,
} from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { publishScene, type Scene, type SceneBinaryFile } from "../../lib/agents";

/**
 * Read-only viewer for a generated SceneSkeleton.
 *
 * The agent persists `Scene` (a tiny ExcalidrawElementSkeleton list). Here we
 *   1) inflate it via `convertToExcalidrawElements()` from the official lib,
 *   2) hand the inflated elements to a read-only `<Excalidraw>` viewer, and
 *   3) expose two affordances:
 *        Download .excalidraw — builds the envelope client-side, blob save.
 *        Open in excalidraw.com — POSTs envelope to backend, gets a public
 *        Storage URL, opens `excalidraw.com/#url=<encoded>` in a new tab.
 *
 * Edits stay disabled in v1 (PRD §5.5 first-pass scope: view + open in
 * Excalidraw). Inline editing + screenshot-to-edit ship in the next slice.
 */

type Props = {
  scene: Scene;
  sessionId: string;
};

/** Stable key so Excalidraw remounts when typography changes (`updateScene` alone often misses font swaps). */
function sceneTypographyKey(scene: Scene): string {
  return scene.elements
    .map((e) => {
      const lf =
        e.label &&
        typeof e.label === "object" &&
        "fontFamily" in e.label &&
        (e.label as { fontFamily?: number }).fontFamily != null
          ? String((e.label as { fontFamily?: number }).fontFamily)
          : "";
      return `${e.id}:${e.fontFamily ?? ""}:${lf}`;
    })
    .join("|");
}

function buildEnvelope(scene: Scene): {
  type: "excalidraw";
  version: 2;
  source: string;
  elements: ReturnType<typeof convertToExcalidrawElements>;
  appState: Record<string, unknown>;
  files: Record<string, SceneBinaryFile>;
} {
  // The skeleton elements come straight from the LLM; cast through `unknown`
  // because the lib's input type is broader than our narrow Scene typing.
  const elements = convertToExcalidrawElements(
    scene.elements as unknown as Parameters<typeof convertToExcalidrawElements>[0],
    { regenerateIds: false },
  );
  const files = (scene.files ?? {}) as Record<string, SceneBinaryFile>;
  return {
    type: "excalidraw",
    version: 2,
    source: "https://excalidraw.com",
    elements,
    appState: {
      viewBackgroundColor: scene.background_color,
      gridSize: null,
    },
    files,
  };
}

function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Treat any non-near-black canvas as a light theme so the Excalidraw chrome
// (toolbar / scrollbars) matches the canvas. Old scenes with #1A1A2E render
// dark; new scenes default to #FFFFFF and render light.
function isLightCanvas(hex: string | null | undefined): boolean {
  const s = (hex ?? "").trim().toLowerCase();
  if (!s) return true;
  // Strip optional '#' and parse RGB.
  const v = s.startsWith("#") ? s.slice(1) : s;
  if (!/^[0-9a-f]{6}$/.test(v)) return true;
  const r = parseInt(v.slice(0, 2), 16);
  const g = parseInt(v.slice(2, 4), 16);
  const b = parseInt(v.slice(4, 6), 16);
  // Perceived luminance — light if brighter than ~50% grey.
  const luma = 0.299 * r + 0.587 * g + 0.114 * b;
  return luma > 140;
}

export function SceneView({ scene, sessionId }: Props) {
  const typographyKey = useMemo(() => sceneTypographyKey(scene), [scene]);
  const envelope = useMemo(() => buildEnvelope(scene), [scene]);
  const lightCanvas = isLightCanvas(scene.background_color);
  const themeName: "light" | "dark" = lightCanvas ? "light" : "dark";
  const [opening, setOpening] = useState(false);
  const [copying, setCopying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const apiRef = useRef<unknown>(null);

  useEffect(() => {
    // When the scene prop changes (re-run), reset the canvas content.
    const api = apiRef.current as
      | { updateScene: (data: Record<string, unknown>) => void }
      | null;
    if (!api) return;
    api.updateScene({
      elements: envelope.elements,
      appState: envelope.appState,
      files: envelope.files,
    });
  }, [envelope]);

  const onDownload = useCallback(() => {
    const json = JSON.stringify(envelope, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    downloadBlob(`scene-${sessionId.slice(0, 8)}.excalidraw`, blob);
  }, [envelope, sessionId]);

  // Single source of truth for "publish if needed, return the URL". The first
  // caller pays the upload cost; later callers (Open, Copy) reuse the cached
  // shareUrl until the scene prop changes.
  const ensureShareUrl = useCallback(async (): Promise<string> => {
    if (shareUrl) return shareUrl;
    const { excalidraw_url } = await publishScene(
      sessionId,
      envelope as unknown as Record<string, unknown>,
    );
    setShareUrl(excalidraw_url);
    return excalidraw_url;
  }, [shareUrl, sessionId, envelope]);

  const onOpenInExcalidraw = useCallback(async () => {
    setOpening(true);
    setError(null);
    setCopied(false);
    try {
      const url = await ensureShareUrl();
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setOpening(false);
    }
  }, [ensureShareUrl]);

  const onCopyShareUrl = useCallback(async () => {
    setCopying(true);
    setError(null);
    try {
      const url = await ensureShareUrl();
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCopying(false);
    }
  }, [ensureShareUrl]);

  // Reset the share link whenever the scene changes (re-run produces a new
  // skeleton; the old URL points at a stale Storage object).
  useEffect(() => {
    setShareUrl(null);
    setCopied(false);
  }, [scene]);

  return (
    <div className="flex flex-col gap-3 min-h-0">
      <div className="flex items-center gap-2 flex-wrap">
        <Button size="sm" variant="secondary" onClick={onDownload}>
          <DownloadSimple size={12} weight="bold" />
          Download .excalidraw
        </Button>
        <Button
          size="sm"
          variant="primary"
          onClick={onOpenInExcalidraw}
          disabled={opening || copying}
        >
          {opening ? (
            <Spinner size={12} weight="bold" className="animate-spin" />
          ) : (
            <ArrowSquareOut size={12} weight="bold" />
          )}
          {opening ? "Uploading…" : "Open in Excalidraw"}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={onCopyShareUrl}
          disabled={opening || copying}
          title="Upload + copy excalidraw.com link"
        >
          {copying ? (
            <Spinner size={12} weight="bold" className="animate-spin" />
          ) : copied ? (
            <Check size={12} weight="bold" />
          ) : (
            <Copy size={12} weight="bold" />
          )}
          {copying ? "Uploading…" : copied ? "Copied" : "Copy share link"}
        </Button>
        {error ? (
          <span className="font-mono text-[11px] text-cinnabar">
            {error}
          </span>
        ) : null}
      </div>

      {shareUrl ? (
        <div className="flex items-center gap-2 rounded-lg border border-cinnabar/40 bg-cinnabar/[0.06] px-2.5 py-1.5">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-cinnabar shrink-0">
            share
          </span>
          <input
            readOnly
            value={shareUrl}
            onFocus={(e) => e.currentTarget.select()}
            className="flex-1 min-w-0 bg-transparent font-mono text-[11px] text-white outline-none truncate"
          />
          <Button
            size="sm"
            variant="secondary"
            onClick={onCopyShareUrl}
            title="Copy excalidraw.com link"
          >
            {copied ? (
              <>
                <Check size={12} weight="bold" />
                Copied
              </>
            ) : (
              <>
                <Copy size={12} weight="bold" />
                Copy
              </>
            )}
          </Button>
        </div>
      ) : null}

      <div
        className="rounded-lg border border-hairline overflow-hidden"
        style={{
          height: 480,
          // Excalidraw paints its own background from appState; leave the
          // surrounding chrome dark so the canvas blends in.
          background: scene.background_color,
        }}
      >
        <Excalidraw
          key={`${sessionId}-${typographyKey}`}
          excalidrawAPI={(api) => {
            apiRef.current = api;
          }}
          initialData={{
            elements: envelope.elements,
            appState: {
              ...envelope.appState,
              viewModeEnabled: true,
              theme: themeName,
            },
            // Excalidraw's BinaryFiles narrows mimeType to a specific union;
            // our looser SceneBinaryFile shape passes a string, so cast here.
            files: envelope.files as unknown as Record<string, never>,
            scrollToContent: true,
          }}
          viewModeEnabled
          theme={themeName}
        />
      </div>

      {scene.notes ? (
        <p className="font-mono text-[11px] text-mist leading-[1.6]">
          critic · {scene.notes}
        </p>
      ) : null}
    </div>
  );
}

export default SceneView;
