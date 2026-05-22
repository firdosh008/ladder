import { cn } from "../../lib/cn";

/**
 * H2 section heading per design-sys.md: Playfair Display 700 at 28px,
 * with a 3px Cinnabar bottom border. Inline-block so the border doesn't
 * run the full container width.
 */
export function SectionHeading({
  children,
  className,
  as: Tag = "h2",
  mono,
}: {
  children: React.ReactNode;
  className?: string;
  as?: "h1" | "h2" | "h3";
  mono?: string;
}) {
  return (
    <div className="flex items-baseline gap-4">
      <Tag
        className={cn(
          "font-display font-bold text-[28px] text-white leading-none",
          "pb-2 border-b-[3px] border-cinnabar inline-block",
          className,
        )}
      >
        {children}
      </Tag>
      {mono ? (
        <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-mist">
          {mono}
        </span>
      ) : null}
    </div>
  );
}
