import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Image as ImageIcon,
  Palette,
  Clock,
  CaretDown,
  Check,
  CornersOut,
} from "@phosphor-icons/react";
import * as Popover from "@radix-ui/react-popover";
import { cn } from "../../lib/cn";
import { Pill } from "../ui/Pill";
import type { Idea } from "../../lib/useIdeas";

const DEFAULT_BRAND_COLOR = "#E8442A";

// Curated swatch row for the brand-color popover. The native picker is the
// fallback for anything off this list — these are tuned to read on the dark
// Excalidraw canvas (#1A1A2E) without strobing.
const BRAND_SWATCHES: string[] = [
  "#E8442A", // cinnabar (default)
  "#F5A524", // amber
  "#FACC15", // yellow
  "#22C55E", // emerald
  "#06B6D4", // cyan
  "#3B82F6", // blue
  "#8B5CF6", // violet
  "#EC4899", // pink
  "#F5F5F5", // bone (mono accent)
];

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

function normalizeHex(input: string): string | null {
  const v = input.trim();
  if (!v) return null;
  const withHash = v.startsWith("#") ? v : `#${v}`;
  return HEX_RE.test(withHash) ? withHash.toUpperCase() : null;
}

const DURATION_OPTIONS: { value: number; label: string; hint: string }[] = [
  { value: 5, label: "5 min", hint: "hot take" },
  { value: 10, label: "10 min", hint: "framework" },
  { value: 15, label: "15 min", hint: "essay" },
  { value: 20, label: "20 min", hint: "founder essay" },
  { value: 30, label: "30 min", hint: "deep dive" },
  { value: 45, label: "45 min", hint: "masterclass" },
];

type SessionPills = {
  output_type?: string | null;
  brand_id?: string | null;
  brand_color?: string | null;
  thumbnail_selected_id?: string | null;
};

type Props = {
  idea: Idea | null;
  loading: boolean;
  session: SessionPills | null;
  onTitleChange?: (title: string) => Promise<void> | void;
  onDurationChange?: (minutes: number) => void;
  durationLocked?: boolean;
  onBrandColorChange?: (hex: string | null) => Promise<void> | void;
};

export function StudioHeader({
  idea,
  loading,
  session,
  onTitleChange,
  onDurationChange,
  durationLocked,
  onBrandColorChange,
}: Props) {
  return (
    <header
      className={cn(
        "flex items-center gap-3 px-4 h-12 shrink-0",
        "border-b border-hairline bg-night",
      )}
    >
      <Link
        to="/videos"
        className={cn(
          "inline-flex items-center gap-1.5 h-7 px-2 -ml-1 rounded-md",
          "text-[12px] text-mist hover:text-white hover:bg-white/[0.04]",
          "transition-colors",
        )}
      >
        <ArrowLeft size={12} weight="bold" />
        My Videos
      </Link>

      <span className="h-3.5 w-px bg-hairline shrink-0" />

      <EditableTitle
        title={idea?.title ?? (loading ? "Loading…" : "Studio")}
        editable={!!idea && !!onTitleChange}
        onSave={onTitleChange}
      />

      <div className="flex-1" />

      <div className="flex items-center gap-1">
        <OutputPill output={session?.output_type ?? null} />
        <BrandPill
          brandColor={session?.brand_color ?? null}
          onChange={onBrandColorChange}
          enabled={!!onBrandColorChange}
        />
        <DurationPill
          current={idea?.target_duration_min ?? null}
          onChange={onDurationChange}
          locked={!!durationLocked}
        />
        <ThumbnailPill thumbnailId={session?.thumbnail_selected_id ?? null} />
      </div>
    </header>
  );
}

// ─── Title ────────────────────────────────────────────────────────────────

function EditableTitle({
  title,
  editable,
  onSave,
}: {
  title: string;
  editable: boolean;
  onSave?: (title: string) => Promise<void> | void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(title);
  }, [title, editing]);

  useEffect(() => {
    if (editing) {
      requestAnimationFrame(() => {
        inputRef.current?.focus();
        inputRef.current?.select();
      });
    }
  }, [editing]);

  const commit = async () => {
    const next = draft.trim();
    setEditing(false);
    if (!next || next === title) return;
    try {
      await onSave?.(next);
    } catch {
      setDraft(title);
    }
  };

  const cancel = () => {
    setDraft(title);
    setEditing(false);
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    }
  };

  if (!editable) {
    return (
      <span className="font-display italic text-[15px] text-white truncate min-w-0 max-w-[520px]">
        {title}
      </span>
    );
  }

  return editing ? (
    <input
      ref={inputRef}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={onKey}
      className={cn(
        "min-w-[200px] max-w-[560px] h-7 px-2",
        "rounded-md border border-cinnabar/40 bg-white/[0.03]",
        "font-display italic text-[15px] text-white outline-none",
        "focus:ring-1 focus:ring-cinnabar/60",
      )}
    />
  ) : (
    <button
      type="button"
      onClick={() => setEditing(true)}
      title="Click to rename"
      className={cn(
        "inline-flex items-center h-7 px-1.5 -mx-1.5 rounded-md min-w-0",
        "font-display italic text-[15px] text-white truncate max-w-[560px]",
        "hover:bg-white/[0.04] transition-colors text-left",
      )}
    >
      {title}
    </button>
  );
}

// ─── Pill: Output ─────────────────────────────────────────────────────────

function OutputPill({ output }: { output: string | null }) {
  const label = labelize(output) ?? "Excalidraw";
  return (
    <PillPopover
      title="Output format"
      renderTrigger={(open) => (
        <Pill type="button" density="compact" open={open} title="Output format">
          <CornersOut size={10} weight="bold" className="text-mist" />
          {label}
        </Pill>
      )}
    >
      <PopoverBody>
        <p className="text-[12.5px] text-white/85 leading-[1.55]">
          The current output for this video is{" "}
          <span className="font-mono text-cinnabar">{label}</span>. Switching
          output formats ships in a later pass — for now every video lands as
          an Excalidraw scene.
        </p>
      </PopoverBody>
    </PillPopover>
  );
}

// ─── Pill: Brand color ────────────────────────────────────────────────────

function BrandPill({
  brandColor,
  onChange,
  enabled,
}: {
  brandColor: string | null;
  onChange?: (hex: string | null) => Promise<void> | void;
  enabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(brandColor ?? "");
  const [saving, setSaving] = useState(false);

  // Keep the inline input in sync if the underlying session row changes
  // (e.g. another tab patched it, or the pill mounts mid-stream).
  useEffect(() => {
    setDraft(brandColor ?? "");
  }, [brandColor]);

  const swatch = brandColor ?? DEFAULT_BRAND_COLOR;
  const label = brandColor ? brandColor.toUpperCase() : "Pick color";

  const commit = async (hex: string | null) => {
    if (!enabled || !onChange) return;
    if (hex === brandColor) return;
    setSaving(true);
    try {
      await onChange(hex);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Pill type="button" density="compact" open={open} title="Brand color">
          <span
            aria-hidden
            className="inline-block h-3 w-3 rounded-sm border border-white/15"
            style={{ backgroundColor: swatch }}
          />
          {label}
        </Pill>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className={cn(
            "z-30 w-[260px] rounded-md border border-hairline",
            "bg-night shadow-xl overflow-hidden",
            "data-[state=open]:animate-scale-in data-[state=closed]:animate-fade-out",
            "origin-top-right",
          )}
        >
          <PopoverHeader title="Brand color">
            primary accent for excalidraw drawings. takes effect on the next
            scene re-run.
          </PopoverHeader>
          <div className="px-3 py-3 space-y-3">
            <div className="grid grid-cols-9 gap-1.5">
              {BRAND_SWATCHES.map((hex) => {
                const active = brandColor?.toUpperCase() === hex.toUpperCase();
                return (
                  <button
                    key={hex}
                    type="button"
                    title={hex}
                    onClick={() => {
                      setDraft(hex);
                      void commit(hex);
                    }}
                    className={cn(
                      "h-5 w-5 rounded-sm border transition-transform",
                      active
                        ? "border-white ring-1 ring-white/60 scale-110"
                        : "border-white/15 hover:scale-110",
                    )}
                    style={{ backgroundColor: hex }}
                  />
                );
              })}
            </div>

            <div className="flex items-center gap-2">
              <label className="relative inline-flex items-center gap-1.5 cursor-pointer">
                <Palette size={11} weight="bold" className="text-mist" />
                <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-mist">
                  custom
                </span>
                <input
                  type="color"
                  value={normalizeHex(draft) ?? swatch}
                  onChange={(e) => {
                    const v = e.target.value.toUpperCase();
                    setDraft(v);
                  }}
                  onBlur={() => {
                    const v = normalizeHex(draft);
                    if (v) void commit(v);
                  }}
                  className="absolute inset-0 opacity-0 cursor-pointer"
                />
              </label>
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    const v = normalizeHex(draft);
                    if (v) void commit(v);
                  }
                }}
                placeholder="#E8442A"
                className={cn(
                  "flex-1 h-7 px-2 rounded-md bg-white/[0.03] border border-hairline",
                  "font-mono text-[11.5px] text-white outline-none",
                  "focus:ring-1 focus:ring-cinnabar/60",
                )}
              />
              {brandColor ? (
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => {
                    setDraft("");
                    void commit(null);
                  }}
                  className={cn(
                    "h-7 px-2 rounded-md text-[11px] text-mist",
                    "hover:text-white hover:bg-white/[0.04] transition-colors",
                  )}
                  title="Reset to default"
                >
                  reset
                </button>
              ) : null}
            </div>
            {!enabled ? (
              <p className="text-[11px] text-mist">
                color picker activates once the session is created.
              </p>
            ) : null}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

// ─── Pill: Duration ───────────────────────────────────────────────────────

function DurationPill({
  current,
  onChange,
  locked,
}: {
  current: number | null;
  onChange?: (minutes: number) => void;
  locked: boolean;
}) {
  const [open, setOpen] = useState(false);
  const label = current ? `${current} min` : "Set runtime";
  const activeHint = current
    ? (DURATION_OPTIONS.find((o) => o.value === current)?.hint ?? null)
    : null;

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Pill
          type="button"
          density="compact"
          open={open}
          locked={locked}
          title="Target runtime"
        >
          <Clock size={10} weight="bold" className="text-mist" />
          {label}
        </Pill>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className={cn(
            "z-30 min-w-[260px] rounded-md border border-hairline",
            "bg-night shadow-xl overflow-hidden",
            "data-[state=open]:animate-scale-in data-[state=closed]:animate-fade-out",
            "origin-top-right",
          )}
        >
          <PopoverHeader title="Runtime">
            re-runs the script writer + outline planner against the new
            target. previous versions stay in history.
          </PopoverHeader>
          {activeHint ? (
            <div className="px-3 py-1 font-mono text-[9.5px] uppercase tracking-[0.2em] text-mist border-b border-hairline">
              current · {activeHint}
            </div>
          ) : null}
          <ul className="py-1">
            {DURATION_OPTIONS.map((opt) => {
              const isCurrent = opt.value === current;
              return (
                <li key={opt.value}>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      if (!isCurrent && onChange) onChange(opt.value);
                    }}
                    className={cn(
                      "w-full flex items-center gap-2 px-3 py-1.5 text-left transition-colors",
                      isCurrent
                        ? "bg-white/[0.03]"
                        : "hover:bg-white/[0.04] cursor-pointer",
                    )}
                  >
                    <span
                      className={cn(
                        "text-[12.5px] tabular-nums w-[44px] shrink-0",
                        isCurrent ? "text-white" : "text-white/85",
                      )}
                    >
                      {opt.label}
                    </span>
                    <span className="text-[11.5px] text-mist truncate flex-1">
                      {opt.hint}
                    </span>
                    {isCurrent ? (
                      <Check
                        size={11}
                        weight="bold"
                        className="text-cinnabar shrink-0"
                      />
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

// ─── Pill: Thumbnail ──────────────────────────────────────────────────────
// Just a button, no dropdown. The thumbnail generator lives in the action
// row below the outline; this pill mirrors current state and is a no-op
// visual indicator until generation is wired up.

function ThumbnailPill({ thumbnailId }: { thumbnailId: string | null }) {
  return (
    <Pill
      type="button"
      density="compact"
      noCaret
      title={
        thumbnailId
          ? "Thumbnail selected. Generate from the action row below the outline."
          : "No thumbnail yet. Run the thumbnail generator from the action row."
      }
    >
      <ImageIcon size={10} weight="bold" className="text-mist" />
      {thumbnailId ? "Thumbnail set" : "No thumbnail"}
    </Pill>
  );
}

// ─── Pill popover shell ───────────────────────────────────────────────────

function PillPopover({
  renderTrigger,
  title,
  children,
}: {
  renderTrigger: (open: boolean) => React.ReactElement;
  title: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>{renderTrigger(open)}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className={cn(
            "z-30 w-[280px] rounded-md border border-hairline",
            "bg-night shadow-xl overflow-hidden",
            "data-[state=open]:animate-scale-in data-[state=closed]:animate-fade-out",
            "origin-top-right",
          )}
        >
          <PopoverHeader title={title} />
          {children}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function PopoverHeader({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="px-3 pt-2.5 pb-2 border-b border-hairline">
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-mist">
          {title}
        </span>
        <CaretDown size={9} weight="bold" className="text-mist/40 ml-auto" />
      </div>
      {children ? (
        <p className="mt-1 text-[11.5px] text-white/70 leading-[1.5]">
          {children}
        </p>
      ) : null}
    </div>
  );
}

function PopoverBody({ children }: { children: React.ReactNode }) {
  return <div className="px-3 py-3">{children}</div>;
}

// Title-cased labels keep the pill row visually consistent — `excalidraw`
// becomes `Excalidraw`, etc. Returns null for empty inputs.
function labelize(raw: string | null | undefined): string | null {
  if (!raw) return null;
  return raw
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}
