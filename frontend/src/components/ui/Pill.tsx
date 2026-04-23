import { forwardRef, type ButtonHTMLAttributes } from "react";
import { CaretDown, Lock } from "@phosphor-icons/react";
import { cn } from "../../lib/cn";

export interface PillProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  locked?: boolean;
  accent?: boolean;
  open?: boolean;
}

/**
 * Editable pill used in the Studio header. Inline dropdown, never a modal.
 * Tap = opens dropdown directly below. Locked pills grey out with lock icon.
 */
export const Pill = forwardRef<HTMLButtonElement, PillProps>(
  ({ className, locked, accent, open, children, ...props }, ref) => (
    <button
      ref={ref}
      disabled={locked}
      data-open={open ? "" : undefined}
      className={cn(
        "group inline-flex items-center gap-1.5 rounded-full px-3 h-7",
        "text-[12px] font-medium font-sans whitespace-nowrap",
        "transition-colors duration-150 ease-out",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cinnabar",
        accent
          ? "bg-cinnabar/[0.12] text-cinnabar hover:bg-cinnabar/[0.18]"
          : "bg-white/[0.06] text-white hover:bg-white/[0.1] border border-hairline",
        locked && "opacity-50 cursor-not-allowed hover:bg-white/[0.06]",
        "data-[open]:ring-1 data-[open]:ring-cinnabar",
        className,
      )}
      {...props}
    >
      {locked ? (
        <Lock size={11} weight="bold" className="opacity-60" />
      ) : null}
      <span>{children}</span>
      {!locked ? (
        <CaretDown
          size={10}
          weight="bold"
          className="opacity-60 transition-transform group-data-[open]:rotate-180"
        />
      ) : null}
    </button>
  ),
);
Pill.displayName = "Pill";
