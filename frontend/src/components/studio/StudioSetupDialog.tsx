import { useState, useEffect, forwardRef } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import * as Select from "@radix-ui/react-select";
import {
  X,
  ArrowRight,
  CaretDown,
  Check,
  Clock,
  PencilLine,
  PaintBrush,
} from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/cn";

export type StudioSetupValues = {
  duration: number;
  tool: "excalidraw";
  brandId: string;
};

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  subtitle?: string;
  ctaLabel?: string;
  defaultDuration?: number;
  onConfirm: (v: StudioSetupValues) => void;
};

const DURATION_OPTIONS = [
  { value: 5, label: "5 min · short" },
  { value: 10, label: "10 min · standard" },
  { value: 15, label: "15 min · deep" },
  { value: 20, label: "20 min · recommended" },
  { value: 30, label: "30 min · long-form" },
  { value: 45, label: "45 min · masterclass" },
];

const TOOL_OPTIONS = [
  { value: "excalidraw", label: "Excalidraw · hand-drawn" },
];

// TODO: wire to /brands endpoint once built. For now a single default option —
// the studio will fall back to the user's voice profile.

export function StudioSetupDialog({
  open,
  onOpenChange,
  title,
  subtitle,
  ctaLabel = "Enter studio",
  defaultDuration = 20,
  onConfirm,
}: Props) {
  const [duration, setDuration] = useState(defaultDuration);
  const [tool, setTool] = useState<"excalidraw">("excalidraw");
  const [brandId, setBrandId] = useState("default");

  useEffect(() => {
    if (open) {
      setDuration(defaultDuration);
      setTool("excalidraw");
      setBrandId("default");
    }
  }, [open, defaultDuration]);

  function confirm() {
    onConfirm({ duration, tool, brandId });
    onOpenChange(false);
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            "fixed inset-0 z-40 bg-black/60 backdrop-blur-[3px]",
            "data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-out",
          )}
        />
        <Dialog.Content
          aria-describedby={undefined}
          className={cn(
            "fixed left-1/2 top-1/2 z-50 w-[min(480px,calc(100vw-32px))]",
            "-translate-x-1/2 -translate-y-1/2",
            "rounded-xl border border-hairline bg-ink shadow-diffuse",
            "focus:outline-none",
            "data-[state=open]:animate-scale-in data-[state=closed]:animate-scale-out",
          )}
        >
          {/* Header */}
          <div className="flex items-start justify-between px-6 pt-5 pb-4 border-b border-hairline">
            <div className="min-w-0">
              <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-1.5">
                § studio setup
              </div>
              <Dialog.Title className="font-display text-[20px] leading-[1.15] text-white">
                {title}
              </Dialog.Title>
              {subtitle ? (
                <p className="mt-1 text-[12.5px] text-mist truncate">
                  {subtitle}
                </p>
              ) : null}
            </div>
            <Dialog.Close asChild>
              <button
                type="button"
                aria-label="Close"
                className="text-mist hover:text-white transition-colors -mt-1 -mr-1 p-1"
              >
                <X size={16} weight="bold" />
              </button>
            </Dialog.Close>
          </div>

          {/* Body */}
          <div className="px-6 py-5 space-y-4">
            <Field label="Duration" icon={Clock}>
              <SelectField
                value={String(duration)}
                onValueChange={(v) => setDuration(Number(v))}
                ariaLabel="Duration"
              >
                {DURATION_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={String(o.value)}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectField>
            </Field>

            <Field label="Tool" icon={PencilLine}>
              <SelectField
                value={tool}
                onValueChange={(v) => setTool(v as "excalidraw")}
                ariaLabel="Tool"
              >
                {TOOL_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectField>
            </Field>

          </div>

          {/* Footer */}
          <div className="flex items-center justify-between gap-2 px-6 py-4 border-t border-hairline">
            <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
              ⌘↵ to start
            </span>
            <div className="flex items-center gap-2">
              <Dialog.Close asChild>
                <Button variant="ghost" size="sm">
                  Cancel
                </Button>
              </Dialog.Close>
              <Button size="sm" onClick={confirm}>
                {ctaLabel}
                <ArrowRight size={12} weight="bold" />
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Field({
  label,
  icon: Icon,
  children,
}: {
  label: string;
  icon: React.ElementType;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 mb-1.5 font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist">
        <Icon size={11} weight="bold" />
        {label}
      </div>
      {children}
    </div>
  );
}

function SelectField({
  value,
  onValueChange,
  ariaLabel,
  children,
}: {
  value: string;
  onValueChange: (v: string) => void;
  ariaLabel: string;
  children: React.ReactNode;
}) {
  return (
    <Select.Root value={value} onValueChange={onValueChange}>
      <Select.Trigger
        aria-label={ariaLabel}
        className={cn(
          "w-full h-10 px-3 flex items-center justify-between gap-2",
          "rounded-md bg-surface-input text-[13.5px] text-white font-sans",
          "border border-transparent hover:border-hairline-strong",
          "data-[state=open]:border-cinnabar/60",
          "focus:outline-none focus:border-cinnabar transition-colors",
        )}
      >
        <Select.Value />
        <Select.Icon className="text-mist">
          <CaretDown size={12} weight="bold" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Content
          position="popper"
          sideOffset={6}
          className={cn(
            "z-[60] overflow-hidden rounded-md border border-hairline bg-ink shadow-diffuse",
            "w-[var(--radix-select-trigger-width)]",
            "data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-out",
          )}
        >
          <Select.Viewport className="p-1">{children}</Select.Viewport>
        </Select.Content>
      </Select.Portal>
    </Select.Root>
  );
}

const SelectItem = forwardRef<
  HTMLDivElement,
  { value: string; children: React.ReactNode }
>(({ value, children }, ref) => (
  <Select.Item
    ref={ref}
    value={value}
    className={cn(
      "relative flex items-center justify-between gap-2 h-8 px-2.5 rounded-[5px]",
      "text-[13px] text-white/85 font-sans cursor-pointer select-none outline-none",
      "data-[highlighted]:bg-white/[0.06] data-[highlighted]:text-white",
      "data-[state=checked]:text-white",
    )}
  >
    <Select.ItemText>{children}</Select.ItemText>
    <Select.ItemIndicator>
      <Check size={12} weight="bold" className="text-cinnabar" />
    </Select.ItemIndicator>
  </Select.Item>
));
SelectItem.displayName = "SelectItem";
