import { useState, type ReactNode } from "react";
import { CaretDown } from "@phosphor-icons/react";
import { cn } from "../../lib/cn";

type Props = {
  /** Stable id used as the scroll-spy anchor. */
  id: string;
  title: string;
  hint?: string;
  /** Right-side adornment (e.g. an inline action button). */
  trailing?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
};

/**
 * Section with an `id` anchor, a click-to-collapse header, and a smooth
 * expand/collapse via grid-rows interpolation. Used inside the studio's
 * scroll container so the SectionNav chips can target each `id`.
 */
export function CollapsibleSection({
  id,
  title,
  hint,
  trailing,
  defaultOpen = true,
  children,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section id={id} className="scroll-mt-14">
      <header className="flex items-center gap-3 mb-3">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className={cn(
            "inline-flex items-center gap-1.5 -mx-1 px-1 rounded",
            "text-left transition-colors",
            "hover:bg-white/[0.03]",
          )}
        >
          <CaretDown
            size={11}
            weight="bold"
            className={cn(
              "text-mist transition-transform duration-200",
              open ? "rotate-0" : "-rotate-90",
            )}
          />
          <h3 className="font-sans font-semibold text-[13px] text-white">
            {title}
          </h3>
          {hint ? (
            <span className="font-mono text-[10.5px] text-mist uppercase tracking-[0.18em]">
              {hint}
            </span>
          ) : null}
        </button>
        <span className="flex-1" />
        {trailing ? <div>{trailing}</div> : null}
      </header>
      <div
        className={cn(
          "grid transition-[grid-template-rows] duration-200 ease-out",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="overflow-hidden">
          <div className="space-y-3">{children}</div>
        </div>
      </div>
    </section>
  );
}
