import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

const fieldBase =
  "w-full bg-surface-input text-[14px] text-white placeholder:text-mist " +
  "rounded-md border border-transparent " +
  "focus:outline-none focus:border-cinnabar " +
  "transition-colors duration-150 ease-out " +
  "disabled:opacity-40 font-sans";

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(fieldBase, "h-9 px-3", className)}
    {...props}
  />
));
Input.displayName = "Input";

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(fieldBase, "py-2.5 px-3 min-h-[80px] resize-y leading-[1.55]", className)}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export function FieldLabel({
  children,
  htmlFor,
  hint,
}: {
  children: React.ReactNode;
  htmlFor?: string;
  hint?: string;
}) {
  return (
    <div className="flex items-center justify-between mb-1.5">
      <label
        htmlFor={htmlFor}
        className="text-[13px] font-semibold text-white font-sans"
      >
        {children}
      </label>
      {hint ? (
        <span className="text-[11px] text-mist font-mono">{hint}</span>
      ) : null}
    </div>
  );
}
