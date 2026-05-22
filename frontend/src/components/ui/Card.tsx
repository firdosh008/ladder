import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "../../lib/cn";

export const Card = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        "rounded-xl border border-hairline bg-surface p-5",
        "transition-colors duration-150 ease-out",
        "hover:border-l-[3px] hover:border-l-cinnabar hover:pl-[calc(1.25rem-2px)]",
        className,
      )}
      {...props}
    />
  ),
);
Card.displayName = "Card";

export function CardTitle({
  className,
  ...props
}: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        "font-sans font-semibold text-[18px] leading-tight text-white",
        className,
      )}
      {...props}
    />
  );
}

export function CardDescription({
  className,
  ...props
}: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("text-[13px] leading-[1.55] text-mist", className)}
      {...props}
    />
  );
}
