import { useNavigate } from "react-router-dom";
import { ArrowRight } from "@phosphor-icons/react";
import { cn } from "../../lib/cn";
import type { InProgressEntry } from "../../types/videos";
import type { ContextMenuItem } from "./ContextMenu";

const STAGES = [
  { key: "has_script" as const, label: "Script" },
  { key: "has_outline" as const, label: "Outline" },
  { key: "has_scene" as const, label: "Scene" },
  { key: "has_thumbnail" as const, label: "Thumbnail" },
];

function formatAge(iso: string): string {
  const then = new Date(iso).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d`;
  return `${Math.floor(days / 7)}w`;
}

type Props = {
  entry: InProgressEntry;
  onArchive: (sessionId: string) => void;
  onContextMenu: (items: ContextMenuItem[], x: number, y: number) => void;
};

export function SessionCard({ entry, onArchive, onContextMenu }: Props) {
  const navigate = useNavigate();
  const completedCount = STAGES.filter((s) => entry[s.key]).length;

  function handleContextMenu(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    onContextMenu(
      [
        { label: "Archive", onClick: () => onArchive(entry.session_id), destructive: true },
        { label: "Duplicate", onClick: () => {} },
        { label: "Use as template", onClick: () => {} },
      ],
      e.clientX,
      e.clientY,
    );
  }

  return (
    <div
      onContextMenu={handleContextMenu}
      className={cn(
        "group relative rounded-lg border border-hairline bg-surface px-3.5 py-3",
        "transition-all duration-200",
        "hover:border-hairline-strong hover:-translate-y-[1px]",
        "hover:shadow-[0_4px_18px_-10px_rgba(0,0,0,0.6)]",
      )}
    >
      {/* Hover action */}
      <div className="absolute top-1.5 right-1.5 z-10 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/studio/${entry.idea_id}`);
          }}
          className="inline-flex items-center gap-1 h-6 px-2 rounded text-[11px] text-mist hover:text-cinnabar hover:bg-cinnabar/10 transition-colors"
        >
          Continue <ArrowRight size={10} weight="bold" />
        </button>
      </div>

      {/* Title */}
      <div className="flex items-start gap-2 mb-3 pr-20">
        {entry.brand_color ? (
          <span
            className="h-3 w-3 rounded-full shrink-0 mt-[3px]"
            style={{ backgroundColor: entry.brand_color }}
          />
        ) : null}
        <span className="text-[13.5px] text-white leading-[1.35] font-medium line-clamp-2">
          {entry.title}
        </span>
      </div>

      {/* Progress dots */}
      <div className="flex items-center gap-1.5 mb-2">
        {STAGES.map((s) => (
          <div key={s.key} className="flex items-center gap-1">
            <span
              className={cn(
                "h-2 w-2 rounded-full",
                entry[s.key] ? "bg-cinnabar" : "bg-hairline",
              )}
            />
            <span
              className={cn(
                "text-[10px] font-mono",
                entry[s.key] ? "text-white/70" : "text-mist/50",
              )}
            >
              {s.label}
            </span>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between font-mono text-[10.5px] text-mist/60">
        <span>
          {completedCount}/{STAGES.length} complete
        </span>
        <span>{formatAge(entry.updated_at)} ago</span>
      </div>
    </div>
  );
}
