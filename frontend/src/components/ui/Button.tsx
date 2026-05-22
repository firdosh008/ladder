import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "../../lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "destructive";
type Size = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  asChild?: boolean;
}

const base =
  "inline-flex items-center justify-center gap-1.5 font-sans font-semibold whitespace-nowrap select-none " +
  "transition-colors duration-150 ease-out focus-visible:outline-none " +
  "focus-visible:ring-1 focus-visible:ring-cinnabar focus-visible:ring-offset-0 " +
  "disabled:opacity-40 disabled:pointer-events-none active:translate-y-[0.5px]";

const variants: Record<Variant, string> = {
  primary: "bg-cinnabar text-white hover:bg-cinnabar-dim",
  secondary: "bg-white/[0.06] text-white hover:bg-white/[0.09] border border-hairline",
  ghost: "text-white/85 hover:text-white hover:bg-white/[0.04]",
  destructive: "bg-sienna text-white hover:bg-[#6F3A2D]",
};

const sizes: Record<Size, string> = {
  sm: "h-7 px-2.5 text-[12.5px] rounded-md",
  md: "h-8 px-3 text-[13px] rounded-md",
  lg: "h-10 px-4 text-[14px] rounded-lg",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { className, variant = "primary", size = "md", asChild = false, ...props },
    ref,
  ) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref as never}
        className={cn(base, variants[variant], sizes[size], className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
