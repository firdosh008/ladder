import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft,
  Image as ImageIcon,
  Clock,
  CaretDown,
  Check,
  CornersOut,
  Plus,
  Trademark,
} from "@phosphor-icons/react";
import * as Popover from "@radix-ui/react-popover";
import { cn } from "../../lib/cn";
import { supabase } from "../../lib/supabase";
import { Pill } from "../ui/Pill";
import type { Idea } from "../../lib/useIdeas";

const DEFAULT_BRAND_COLOR = "#E8442A";

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

function normalizeHex(input: string | null | undefined): string | null {
  if (input == null || !String(input).trim()) return null;
  const v = String(input).trim();
  const withHash = v.startsWith("#") ? v : `#${v}`;
  return HEX_RE.test(withHash) ? withHash.toUpperCase() : null;
}

type BrandRow = {
  id: string;
  name: string;
  primary_color: string | null;
};

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
  /** Session branding: only `brand_id` is PATCHed server-side (`brand_color` column may not exist remotely). Optimistic accent can still be merged locally via `brand_color`. */
  onBrandSessionPatch?: (patch: {
    brand_id: string | null;
    brand_color: string | null;
  }) => Promise<void> | void;
};

export function StudioHeader({
  idea,
  loading,
  session,
  onTitleChange,
  onDurationChange,
  durationLocked,
  onBrandSessionPatch,
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
        <BrandPickPill
          selectedBrandId={session?.brand_id ?? null}
          brandColorAccent={session?.brand_color ?? null}
          onChange={onBrandSessionPatch}
          enabled={!!onBrandSessionPatch}
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

// ─── Pill: Brand (from `brands` table) ─────────────────────────────────────

function BrandPickPill({
  selectedBrandId,
  brandColorAccent,
  onChange,
  enabled,
}: {
  selectedBrandId: string | null;
  brandColorAccent: string | null;
  onChange?: (patch: {
    brand_id: string | null;
    brand_color: string | null;
  }) => Promise<void> | void;
  enabled: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<BrandRow[]>([]);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "error">(
    "idle",
  );
  const [saving, setSaving] = useState(false);

  const loadBrands = useCallback(async () => {
    setLoadState("loading");
    const { data: auth } = await supabase.auth.getSession();
    const uid = auth.session?.user?.id;
    if (!uid) {
      setRows([]);
      setLoadState("idle");
      return;
    }
    const { data, error } = await supabase
      .from("brands")
      .select("id,name,primary_color")
      .eq("user_id", uid)
      .order("name");

    if (error) {
      setLoadState("error");
      setRows([]);
      return;
    }
    setRows((data as BrandRow[]) ?? []);
    setLoadState("idle");
  }, []);

  useEffect(() => {
    void loadBrands();
  }, [loadBrands]);

  useEffect(() => {
    if (!open) return;
    void loadBrands();
  }, [open, loadBrands]);

  const selectedBrandIdNormalized =
    selectedBrandId != null && String(selectedBrandId).trim() !== ""
      ? String(selectedBrandId)
      : null;

  const selected = rows.find((b) => String(b.id) === selectedBrandIdNormalized);
  const resolvedHex =
    normalizeHex(selected?.primary_color) ?? brandColorAccent ?? null;
  const swatchColor = resolvedHex ?? DEFAULT_BRAND_COLOR;
  const label = selectedBrandIdNormalized
    ? (selected?.name ?? "Brand")
    : "Pick a brand";

  const apply = async (brand: BrandRow | null) => {
    if (!enabled || !onChange) return;
    setSaving(true);
    try {
      if (!brand) {
        await onChange({ brand_id: null, brand_color: null });
      } else {
        await onChange({
          brand_id: brand.id,
          brand_color: normalizeHex(brand.primary_color),
        });
      }
    } finally {
      setSaving(false);
      setOpen(false);
    }
  };

  const sameSelection = (brand: BrandRow | null) => {
    if (!brand && !selectedBrandIdNormalized) return true;
    if (!brand || !selectedBrandIdNormalized) return false;
    return String(brand.id) === selectedBrandIdNormalized;
  };

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Pill
          type="button"
          density="compact"
          open={open}
          title={
            enabled
              ? "Brand for this studio session"
              : "Available once the studio session exists"
          }
        >
          <Trademark size={10} weight="bold" className="text-mist shrink-0" />
          <span
            aria-hidden
            className="inline-block h-3 w-3 rounded-sm border border-white/15 shrink-0"
            style={{ backgroundColor: swatchColor }}
          />
          <span className="truncate max-w-[140px]">{label}</span>
        </Pill>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          onCloseAutoFocus={(e) => e.preventDefault()}
          className={cn(
            "z-30 max-w-[min(320px,calc(100vw-24px))] rounded-md border border-hairline",
            "bg-night shadow-xl overflow-hidden flex flex-col max-h-[min(360px,50vh)]",
            "data-[state=open]:animate-scale-in data-[state=closed]:animate-fade-out",
            "origin-top-right",
          )}
        >
          <PopoverHeader title="Pick a brand">
            links your saved brand profile; accent follows each brand&apos;s
            primary swatch where set — applies on the next scene re-run.
          </PopoverHeader>
          {loadState === "loading" ? (
            <div className="px-3 py-3 font-mono text-[11px] text-mist">
              loading brands…
            </div>
          ) : loadState === "error" ? (
            <PopoverBody>
              <p className="text-[12px] text-mist">
                Couldn&apos;t load brands. Check your connection or try again.
              </p>
            </PopoverBody>
          ) : rows.length === 0 ? (
            <PopoverBody>
              <p className="text-[12px] text-white/80 leading-[1.55] mb-2">
                No brands yet. Create one from Settings using the link below.
              </p>
              {!enabled ? (
                <p className="text-[11px] text-mist">
                  brand picker activates once the session is created.
                </p>
              ) : null}
            </PopoverBody>
          ) : (
            <ul className="py-1 overflow-y-auto min-h-0">
              <li>
                <button
                  type="button"
                  disabled={saving || !enabled}
                  onPointerDown={(e) => e.preventDefault()}
                  onClick={() => {
                    if (sameSelection(null)) setOpen(false);
                    else void apply(null);
                  }}
                  className={cn(
                    "w-full flex items-center gap-2 px-3 py-1.5 text-left transition-colors",
                    !selectedBrandIdNormalized
                      ? "bg-white/[0.03]"
                      : "hover:bg-white/[0.04]",
                  )}
                >
                  <span className="text-[11.5px] text-mist italic flex-1">
                    No brand
                  </span>
                  {!selectedBrandIdNormalized ? (
                    <Check
                      size={11}
                      weight="bold"
                      className="text-cinnabar shrink-0"
                    />
                  ) : null}
                </button>
              </li>
              {rows.map((b) => {
                const isSel = selectedBrandIdNormalized === String(b.id);
                const dot = normalizeHex(b.primary_color) ?? DEFAULT_BRAND_COLOR;
                return (
                  <li key={b.id}>
                    <button
                      type="button"
                      disabled={saving || !enabled}
                      onPointerDown={(e) => e.preventDefault()}
                      onClick={() => {
                        if (sameSelection(b)) setOpen(false);
                        else void apply(b);
                      }}
                      className={cn(
                        "w-full flex items-center gap-2 px-3 py-1.5 text-left transition-colors",
                        isSel ? "bg-white/[0.03]" : "hover:bg-white/[0.04]",
                      )}
                    >
                      <span
                        aria-hidden
                        className="h-4 w-4 rounded-sm border border-white/15 shrink-0"
                        style={{ backgroundColor: dot }}
                      />
                      <span
                        className={cn(
                          "text-[12.5px] truncate flex-1",
                          isSel ? "text-white" : "text-white/85",
                        )}
                      >
                        {b.name}
                      </span>
                      {isSel ? (
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
          )}
          <div className="border-t border-hairline shrink-0">
            <Link
              to="/settings?tab=brands"
              onPointerDown={(e) => e.preventDefault()}
              onClick={() => setOpen(false)}
              className={cn(
                "flex items-center gap-2 px-3 py-2 w-full text-left",
                "text-[12.5px] text-white/90 hover:bg-white/[0.04] transition-colors",
              )}
            >
              <Plus size={14} weight="bold" className="text-cinnabar shrink-0" />
              <span>Add brand in Settings</span>
            </Link>
          </div>
          {!enabled && rows.length > 0 ? (
            <div className="px-3 py-2 border-t border-hairline">
              <p className="text-[11px] text-mist">
                brand picker activates once the session is created.
              </p>
            </div>
          ) : null}
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
