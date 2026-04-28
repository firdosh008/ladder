import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "../../lib/cn";

type Props = {
  left: ReactNode;
  right: ReactNode;
  /** localStorage key for persisting the left-pane percentage. */
  storageKey?: string;
  /** Default left-pane percentage when nothing is stored. */
  defaultLeftPct?: number;
  /** Hard floor / ceiling so neither pane can collapse beyond use. */
  minLeftPct?: number;
  maxLeftPct?: number;
  className?: string;
};

export function ResizableSplit({
  left,
  right,
  storageKey,
  defaultLeftPct = 65,
  minLeftPct = 35,
  maxLeftPct = 80,
  className,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);
  const [leftPct, setLeftPct] = useState<number>(() => {
    if (typeof window === "undefined" || !storageKey) return defaultLeftPct;
    const stored = window.localStorage.getItem(storageKey);
    const parsed = stored ? Number(stored) : NaN;
    if (!Number.isFinite(parsed)) return defaultLeftPct;
    return Math.min(maxLeftPct, Math.max(minLeftPct, parsed));
  });

  useEffect(() => {
    if (!storageKey || typeof window === "undefined") return;
    window.localStorage.setItem(storageKey, String(leftPct));
  }, [leftPct, storageKey]);

  const onPointerMove = useCallback(
    (e: PointerEvent) => {
      if (!draggingRef.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const pct = ((e.clientX - rect.left) / rect.width) * 100;
      setLeftPct(Math.min(maxLeftPct, Math.max(minLeftPct, pct)));
    },
    [minLeftPct, maxLeftPct],
  );

  const onPointerUp = useCallback(() => {
    draggingRef.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
  }, [onPointerMove]);

  const onPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      e.preventDefault();
      draggingRef.current = true;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
    },
    [onPointerMove, onPointerUp],
  );

  return (
    <div
      ref={containerRef}
      className={cn("flex-1 min-h-0 flex w-full", className)}
    >
      <div
        className="min-w-0 min-h-0 flex flex-col"
        style={{ width: `${leftPct}%` }}
      >
        {left}
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={Math.round(leftPct)}
        aria-valuemin={minLeftPct}
        aria-valuemax={maxLeftPct}
        onPointerDown={onPointerDown}
        onDoubleClick={() => setLeftPct(defaultLeftPct)}
        className={cn(
          "group relative w-px shrink-0 bg-hairline cursor-col-resize",
          "hover:bg-cinnabar/60 transition-colors",
        )}
        title="Drag to resize · double-click to reset"
      >
        {/* widened hit-area for easier grabbing */}
        <span className="absolute inset-y-0 -left-1.5 -right-1.5" />
      </div>
      <div className="flex-1 min-w-0 min-h-0 flex flex-col">{right}</div>
    </div>
  );
}
