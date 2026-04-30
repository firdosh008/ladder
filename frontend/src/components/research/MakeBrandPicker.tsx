import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  CaretDown,
  Check,
  Plus,
  Trademark,
} from "@phosphor-icons/react";
import * as Popover from "@radix-ui/react-popover";
import { cn } from "../../lib/cn";
import { supabase } from "../../lib/supabase";

/**
 * Compact brand picker for /make. Mirrors the studio header's brand pill but
 * doesn't talk to a studio session — selection is persisted to localStorage
 * as the founder's "default brand for the next session" so it threads into
 * the studio crew once they pick a draft.
 *
 * Custom-font registration in Excalidraw 0.18 is private API; the brand
 * accent (primary_color) is the only thing that flows end-to-end into the
 * scene crew today, which is why this picker focuses on that.
 */

const DEFAULT_BRAND_COLOR = "#E8442A";
const STORAGE_KEY = "ladder:make:default_brand";
const HEX_RE = /^#[0-9a-fA-F]{6}$/;

type BrandRow = {
  id: string;
  name: string;
  primary_color: string | null;
};

export type StoredBrand = {
  brand_id: string | null;
  brand_color: string | null;
};

function normalizeHex(input: string | null | undefined): string | null {
  if (input == null || !String(input).trim()) return null;
  const v = String(input).trim();
  const withHash = v.startsWith("#") ? v : `#${v}`;
  return HEX_RE.test(withHash) ? withHash.toUpperCase() : null;
}

export function readStoredBrand(): StoredBrand | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredBrand;
    if (!parsed || typeof parsed !== "object") return null;
    return {
      brand_id: parsed.brand_id ?? null,
      brand_color: parsed.brand_color ?? null,
    };
  } catch {
    return null;
  }
}

export function writeStoredBrand(value: StoredBrand | null): void {
  if (typeof window === "undefined") return;
  if (!value || (!value.brand_id && !value.brand_color)) {
    window.localStorage.removeItem(STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

type Props = {
  /** Compact mode shrinks padding/text — use when sitting inside a tile UI. */
  compact?: boolean;
};

export function MakeBrandPicker({ compact }: Props) {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<BrandRow[]>([]);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "error">(
    "idle",
  );
  const [stored, setStored] = useState<StoredBrand | null>(() =>
    readStoredBrand(),
  );

  const load = useCallback(async () => {
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
    void load();
  }, [load]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [open, load]);

  const apply = (brand: BrandRow | null) => {
    if (!brand) {
      writeStoredBrand(null);
      setStored(null);
    } else {
      const next: StoredBrand = {
        brand_id: brand.id,
        brand_color: normalizeHex(brand.primary_color),
      };
      writeStoredBrand(next);
      setStored(next);
    }
    setOpen(false);
  };

  const selectedBrand = stored?.brand_id
    ? rows.find((r) => String(r.id) === String(stored.brand_id))
    : null;
  const swatch =
    normalizeHex(selectedBrand?.primary_color) ??
    stored?.brand_color ??
    DEFAULT_BRAND_COLOR;
  const label = stored?.brand_id
    ? selectedBrand?.name ?? "Brand"
    : "Pick a brand";

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          className={cn(
            "inline-flex items-center gap-2 rounded-md bg-surface-input",
            "border border-transparent hover:border-hairline-strong",
            "transition-colors",
            compact ? "px-2.5 h-8" : "px-3 h-9",
            "text-left",
          )}
          title="Brand colour applied to the next studio session"
        >
          <Trademark size={11} weight="bold" className="text-mist shrink-0" />
          <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-mist shrink-0">
            brand
          </span>
          <span
            aria-hidden
            className="h-3 w-3 rounded-sm border border-white/15 shrink-0"
            style={{ backgroundColor: swatch }}
          />
          <span
            className={cn(
              "truncate flex-1 min-w-0",
              compact ? "text-[12.5px]" : "text-[13px]",
              stored?.brand_id ? "text-white" : "text-mist",
            )}
          >
            {label}
          </span>
          <CaretDown size={10} weight="bold" className="text-mist shrink-0" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          onCloseAutoFocus={(e) => e.preventDefault()}
          className={cn(
            "z-30 max-w-[min(320px,calc(100vw-24px))] rounded-md border border-hairline",
            "bg-night shadow-xl overflow-hidden flex flex-col max-h-[min(360px,50vh)]",
            "data-[state=open]:animate-scale-in data-[state=closed]:animate-fade-out",
            "origin-top-left",
          )}
        >
          <div className="px-3 pt-2.5 pb-2 border-b border-hairline">
            <div className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-mist">
              Pick a brand
            </div>
            <p className="mt-1 text-[11.5px] text-white/70 leading-[1.5]">
              applies to the next studio session — accent flows into the scene
              crew so the canvas matches your brand swatch.
            </p>
          </div>
          {loadState === "loading" ? (
            <div className="px-3 py-3 font-mono text-[11px] text-mist">
              loading brands…
            </div>
          ) : loadState === "error" ? (
            <div className="px-3 py-3 text-[12px] text-mist">
              Couldn&apos;t load brands. Check your connection or try again.
            </div>
          ) : rows.length === 0 ? (
            <div className="px-3 py-3">
              <p className="text-[12px] text-white/80 leading-[1.55]">
                No brands yet. Create one from Settings using the link below.
              </p>
            </div>
          ) : (
            <ul className="py-1 overflow-y-auto min-h-0">
              <li>
                <button
                  type="button"
                  onPointerDown={(e) => e.preventDefault()}
                  onClick={() => apply(null)}
                  className={cn(
                    "w-full flex items-center gap-2 px-3 py-1.5 text-left transition-colors",
                    !stored?.brand_id
                      ? "bg-white/[0.03]"
                      : "hover:bg-white/[0.04]",
                  )}
                >
                  <span className="text-[11.5px] text-mist italic flex-1">
                    No brand
                  </span>
                  {!stored?.brand_id ? (
                    <Check
                      size={11}
                      weight="bold"
                      className="text-cinnabar shrink-0"
                    />
                  ) : null}
                </button>
              </li>
              {rows.map((b) => {
                const isSel = stored?.brand_id === String(b.id);
                const dot = normalizeHex(b.primary_color) ?? DEFAULT_BRAND_COLOR;
                return (
                  <li key={b.id}>
                    <button
                      type="button"
                      onPointerDown={(e) => e.preventDefault()}
                      onClick={() => apply(b)}
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
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export default MakeBrandPicker;
