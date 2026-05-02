import { Suspense, lazy } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "@phosphor-icons/react";
import { cn } from "../../lib/cn";
import type { Scene } from "../../lib/agents";

const SceneView = lazy(() => import("./SceneView"));

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scene: Scene | null;
  sessionId: string | null;
  /** Backend MCP canvas URL (e.g. http://127.0.0.1:3000) — iframe shows live drawing during generation. */
  liveCanvasUrl?: string;
  /** True while scene WS run is in progress — switches modal body to live iframe when URL is set. */
  liveCanvasDuringRun?: boolean;
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
}: Props) {
  const trimmedLiveUrl = liveCanvasUrl?.trim() ?? "";
  const showLive = !!trimmedLiveUrl && liveCanvasDuringRun && open;

  const showSceneSnapshot =
    !!scene &&
    !!sessionId &&
    (!liveCanvasDuringRun || !trimmedLiveUrl);

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
            </div>
            <Dialog.Close
              aria-label="Close preview"
              className={cn(
                "inline-flex items-center justify-center h-8 w-8 rounded-md shrink-0",
                "text-mist hover:text-white hover:bg-white/[0.04] transition-colors",
              )}
            >
              <X size={14} weight="bold" />
            </Dialog.Close>
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
