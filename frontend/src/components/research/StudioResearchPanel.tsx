import { useMemo, useState } from "react";
import { CaretDown, CaretRight, Globe } from "@phosphor-icons/react";
import { cn } from "../../lib/cn";
import type { Source, SourcePlatform } from "../../lib/agents";
import { readIdeaResearchSnapshot } from "../../lib/researchSnapshot";
import { SourcePreview } from "./SourcePreview";

/**
 * Inline panel rendered on the Studio page that shows the founder *what*
 * was actually scraped to seed this idea. Reads from the per-idea
 * sessionStorage snapshot written by ResearchRunPanel.
 *
 * Behaviour:
 *   - Collapsed by default with a one-line summary (e.g. "12 sources · 4
 *     platforms").
 *   - Expanded view groups sources by platform and renders them through
 *     the same SourcePreview cards as /make.
 *   - Renders nothing if there is no snapshot for this idea (refreshed in a
 *     fresh tab, opened from /videos kanban, etc.). Honest empty.
 */

// Visual platforms first (YT / X / IG) so they anchor the top of the
// expanded panel; reddit + web sink below since they're text-heavy.
const PLATFORM_ORDER: SourcePlatform[] = [
  "youtube",
  "x",
  "instagram",
  "reddit",
  "web",
];

const PLATFORM_LABEL: Record<SourcePlatform, string> = {
  youtube: "YouTube",
  reddit: "Reddit",
  x: "X",
  instagram: "Instagram",
  web: "Web",
};

const PLATFORM_DOT: Record<SourcePlatform, string> = {
  web: "bg-white/40",
  reddit: "bg-[#ff7a3d]",
  youtube: "bg-[#ff5c5c]",
  x: "bg-white",
  instagram: "bg-[#f06292]",
};

export function StudioResearchPanel({ ideaId }: { ideaId: string }) {
  const [open, setOpen] = useState(false);

  const snapshot = useMemo(
    () => (ideaId ? readIdeaResearchSnapshot(ideaId) : null),
    [ideaId],
  );

  const grouped = useMemo(() => {
    if (!snapshot) return null;
    const map = new Map<SourcePlatform, Source[]>();
    for (const src of snapshot.sources) {
      const platform = (src.platform ?? "web") as SourcePlatform;
      const list = map.get(platform) ?? [];
      list.push(src);
      map.set(platform, list);
    }
    return map;
  }, [snapshot]);

  if (!snapshot || !grouped || snapshot.sources.length === 0) {
    return null;
  }

  const platforms = PLATFORM_ORDER.filter((p) => (grouped.get(p)?.length ?? 0) > 0);

  return (
    <section className="rounded-xl border border-hairline bg-surface/70 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-left hover:bg-white/[0.02] transition-colors"
        aria-expanded={open}
      >
        {open ? (
          <CaretDown size={11} weight="bold" className="text-mist" />
        ) : (
          <CaretRight size={11} weight="bold" className="text-mist" />
        )}
        <Globe size={12} weight="bold" className="text-mist" />
        <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist">
          research sources
        </span>
        <span className="font-mono text-[11px] text-white/85 tabular-nums">
          {snapshot.sources.length}
        </span>
        <div className="flex items-center gap-1.5 ml-2">
          {platforms.map((p) => (
            <span
              key={p}
              className="inline-flex items-center gap-1 font-mono text-[10px] text-mist"
              title={`${grouped.get(p)?.length ?? 0} ${PLATFORM_LABEL[p]} sources`}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full", PLATFORM_DOT[p])} />
              {grouped.get(p)?.length ?? 0}
            </span>
          ))}
        </div>
        <div className="flex-1" />
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-mist">
          {open ? "hide" : "show"}
        </span>
      </button>

      {open ? (
        <div className="border-t border-hairline px-4 py-4 space-y-4 bg-black/15">
          {snapshot.topic ? (
            <div className="font-mono text-[10.5px] text-mist">
              from research on{" "}
              <span className="text-white/90">"{snapshot.topic}"</span>
            </div>
          ) : null}
          {platforms.map((platform) => {
            const items = grouped.get(platform) ?? [];
            if (items.length === 0) return null;
            return (
              <div key={platform}>
                <div className="flex items-center gap-2 mb-2">
                  <span
                    className={cn("h-1.5 w-1.5 rounded-full", PLATFORM_DOT[platform])}
                  />
                  <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-white/80">
                    {PLATFORM_LABEL[platform]}
                  </span>
                  <span className="font-mono text-[10px] tabular-nums text-mist">
                    · {items.length}
                  </span>
                </div>
                <ol className="grid grid-cols-1 gap-1.5">
                  {items.map((source, i) => (
                    <li key={source.url + i}>
                      <SourcePreview
                        source={source}
                        index={i + 1}
                        variant="gallery"
                      />
                    </li>
                  ))}
                </ol>
              </div>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
