import { forwardRef, type ButtonHTMLAttributes } from "react";
import { CaretDown, Lock } from "@phosphor-icons/react";
import { cn } from "../../lib/cn";

export interface PillProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  locked?: boolean;
  accent?: boolean;
  open?: boolean;
  /** Compact density used in dense headers — h-6 vs default h-7. */
  density?: "default" | "compact";
  /** Hide the trailing caret — used when the pill is a plain button (no popover). */
  noCaret?: boolean;
}

/**
 * Editable pill used in the Studio header. Inline dropdown, never a modal.
 * Tap = opens dropdown directly below. Locked pills grey out with lock icon.
 */
export const Pill = forwardRef<HTMLButtonElement, PillProps>(
  (
    {
      className,
      locked,
      accent,
      open,
      density = "default",
      noCaret,
      children,
      ...props
    },
    ref,
  ) => (
    <button
      ref={ref}
      disabled={locked}
      data-open={open ? "" : undefined}
      className={cn(
        "group inline-flex items-center gap-1 rounded-full",
        "font-medium font-sans whitespace-nowrap select-none",
        "transition-colors duration-150 ease-out",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cinnabar/60",
        density === "compact"
          ? "h-6 px-2 text-[11.5px]"
          : "h-7 px-3 text-[12px]",
        accent
          ? "bg-cinnabar/[0.12] text-cinnabar hover:bg-cinnabar/[0.18]"
          : "bg-white/[0.04] text-white/85 hover:text-white hover:bg-white/[0.07] border border-hairline",
        locked && "opacity-50 cursor-not-allowed hover:bg-white/[0.04]",
        "data-[open]:text-white data-[open]:bg-white/[0.07] data-[open]:border-hairline-strong",
        className,
      )}
      {...props}
    >
      {locked ? (
        <Lock size={10} weight="bold" className="opacity-60" />
      ) : null}
      <span className="inline-flex items-center gap-1">{children}</span>
      {!locked && !noCaret ? (
        <CaretDown
          size={9}
          weight="bold"
          className="opacity-50 transition-transform group-data-[open]:rotate-180"
        />
      ) : null}
    </button>
  ),
);
Pill.displayName = "Pill";
