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
};

/**
 * Full-bleed scene preview. Renders the existing read-only `SceneView`
 * (which carries Download + Copy share inside it)
 * inside a Radix Dialog with a fade + scale transition.
 */
export function ScenePreviewModal({
  open,
  onOpenChange,
  scene,
  sessionId,
}: Props) {
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
            <div className="flex items-center gap-2">
              <Dialog.Title className="font-sans font-semibold text-[13.5px] text-white">
                Scene preview
              </Dialog.Title>
              <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
                read-only · download JSON to edit elsewhere
              </span>
            </div>
            <Dialog.Close
              aria-label="Close preview"
              className={cn(
                "inline-flex items-center justify-center h-8 w-8 rounded-md",
                "text-mist hover:text-white hover:bg-white/[0.04] transition-colors",
              )}
            >
              <X size={14} weight="bold" />
            </Dialog.Close>
          </header>
          <div className="flex-1 min-h-0 overflow-y-auto p-4">
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
