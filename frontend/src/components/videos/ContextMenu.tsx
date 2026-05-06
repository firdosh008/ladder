import { useEffect } from "react";
import { createPortal } from "react-dom";
import { cn } from "../../lib/cn";

export type ContextMenuItem = {
  label: string;
  onClick: () => void;
  destructive?: boolean;
};

type Props = {
  items: ContextMenuItem[];
  position: { x: number; y: number };
  onClose: () => void;
};

export function ContextMenu({ items, position, onClose }: Props) {
  useEffect(() => {
    function handler() {
      onClose();
    }
    window.addEventListener("click", handler);
    window.addEventListener("scroll", handler, true);
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") onClose();
    });
    return () => {
      window.removeEventListener("click", handler);
      window.removeEventListener("scroll", handler, true);
    };
  }, [onClose]);

  // Adjust so the menu doesn't overflow the viewport.
  const menuHeight = items.length * 36 + 8;
  const maxY = window.innerHeight - menuHeight - 8;
  const maxX = window.innerWidth - 180;

  return createPortal(
    <div
      className="fixed z-[100] min-w-[160px] rounded-lg border border-hairline bg-night shadow-[0_12px_40px_-12px_rgba(0,0,0,0.8)] py-1 overflow-hidden"
      style={{
        left: Math.min(position.x, maxX),
        top: Math.min(position.y, maxY),
      }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {items.map((item, i) => (
        <button
          key={i}
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            item.onClick();
          }}
          className={cn(
            "w-full text-left px-3.5 py-2 text-[12.5px] transition-colors",
            item.destructive
              ? "text-cinnabar hover:bg-cinnabar/10"
              : "text-white/80 hover:bg-white/[0.06] hover:text-white",
          )}
        >
          {item.label}
        </button>
      ))}
    </div>,
    document.body,
  );
}
