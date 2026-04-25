import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Excalidraw,
  convertToExcalidrawElements,
} from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";
import { DownloadSimple, ArrowSquareOut, Spinner } from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { publishScene, type Scene } from "../../lib/agents";

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

const EXCALIDRAW_OPEN_BASE = "https://excalidraw.com/#url=";

function buildEnvelope(scene: Scene): {
  type: "excalidraw";
  version: 2;
  source: string;
  elements: ReturnType<typeof convertToExcalidrawElements>;
  appState: Record<string, unknown>;
  files: Record<string, never>;
} {
  // The skeleton elements come straight from the LLM; cast through `unknown`
  // because the lib's input type is broader than our narrow Scene typing.
  const elements = convertToExcalidrawElements(
    scene.elements as unknown as Parameters<typeof convertToExcalidrawElements>[0],
    { regenerateIds: false },
  );
  return {
    type: "excalidraw",
    version: 2,
    source: "https://excalidraw.com",
    elements,
    appState: {
      viewBackgroundColor: scene.background_color,
      gridSize: null,
    },
    files: {},
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

export function SceneView({ scene, sessionId }: Props) {
  const envelope = useMemo(() => buildEnvelope(scene), [scene]);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
    });
  }, [envelope]);

  const onDownload = useCallback(() => {
    const json = JSON.stringify(envelope, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    downloadBlob(`scene-${sessionId.slice(0, 8)}.excalidraw`, blob);
  }, [envelope, sessionId]);

  const onOpenInExcalidraw = useCallback(async () => {
    setOpening(true);
    setError(null);
    try {
      const { public_url } = await publishScene(
        sessionId,
        envelope as unknown as Record<string, unknown>,
      );
      const url = `${EXCALIDRAW_OPEN_BASE}${encodeURIComponent(public_url)}`;
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setOpening(false);
    }
  }, [envelope, sessionId]);

  return (
    <div className="flex flex-col gap-3 min-h-0">
      <div className="flex items-center gap-2">
        <Button size="sm" variant="secondary" onClick={onDownload}>
          <DownloadSimple size={12} weight="bold" />
          Download .excalidraw
        </Button>
        <Button
          size="sm"
          variant="primary"
          onClick={onOpenInExcalidraw}
          disabled={opening}
        >
          {opening ? (
            <Spinner size={12} weight="bold" className="animate-spin" />
          ) : (
            <ArrowSquareOut size={12} weight="bold" />
          )}
          {opening ? "Uploading…" : "Open in Excalidraw"}
        </Button>
        {error ? (
          <span className="font-mono text-[11px] text-cinnabar">
            {error}
          </span>
        ) : null}
      </div>

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
          excalidrawAPI={(api) => {
            apiRef.current = api;
          }}
          initialData={{
            elements: envelope.elements,
            appState: {
              ...envelope.appState,
              viewModeEnabled: true,
              theme: "dark",
            },
            scrollToContent: true,
          }}
          viewModeEnabled
          theme="dark"
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
