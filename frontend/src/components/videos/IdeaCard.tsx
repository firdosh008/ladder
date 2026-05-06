import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Archive } from "@phosphor-icons/react";
import type { CSSProperties } from "react";
import { Badge } from "../ui/Badge";
import { cn } from "../../lib/cn";
import type { IdeaEntry } from "../../types/videos";
import type { ContextMenuItem } from "./ContextMenu";

type Props = {
  idea: IdeaEntry;
  onArchive: (id: string) => void;
  onContextMenu: (items: ContextMenuItem[], x: number, y: number) => void;
};

export function IdeaCard({ idea, onArchive, onContextMenu }: Props) {
  const navigate = useNavigate();
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: idea.id });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  function handleContextMenu(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    onContextMenu(
      [
        { label: "Archive", onClick: () => onArchive(idea.id), destructive: true },
        { label: "Duplicate", onClick: () => {} },
      ],
      e.clientX,
      e.clientY,
    );
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onContextMenu={handleContextMenu}
      className={cn(
        "group relative rounded-lg border border-hairline bg-surface px-3.5 py-3",
        "cursor-grab active:cursor-grabbing select-none",
        "transition-all duration-200",
        "hover:border-hairline-strong hover:-translate-y-[1px]",
        "hover:shadow-[0_4px_18px_-10px_rgba(0,0,0,0.6)]",
        isDragging && "opacity-30",
      )}
    >
      {/* Hover actions */}
      <div className="absolute top-1.5 right-1.5 z-10 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
        <button
          type="button"
          aria-label={`Make video from ${idea.title}`}
          title="Make this video"
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/studio/${idea.id}`);
          }}
          onPointerDown={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1 h-6 px-2 rounded text-[11px] text-mist hover:text-cinnabar hover:bg-cinnabar/10 transition-colors"
        >
          Make this video <ArrowRight size={10} weight="bold" />
        </button>
        <button
          type="button"
          aria-label={`Archive ${idea.title}`}
          title="Archive"
          onClick={(e) => {
            e.stopPropagation();
            onArchive(idea.id);
          }}
          onPointerDown={(e) => e.stopPropagation()}
          className="inline-flex items-center justify-center h-6 w-6 rounded text-mist hover:text-cinnabar hover:bg-cinnabar/10 transition-colors"
        >
          <Archive size={12} weight="bold" />
        </button>
      </div>

      {/* Score + title */}
      <div className="flex items-start justify-between gap-2 mb-2 pr-16">
        <span className="text-[13.5px] text-white leading-[1.35] font-medium line-clamp-2">
          {idea.title}
        </span>
        {idea.opportunity_score != null ? (
          <Badge
            tone={idea.opportunity_score > 80 ? "cinnabar" : "neutral"}
            className="shrink-0"
          >
            {idea.opportunity_score}
          </Badge>
        ) : null}
      </div>

      {/* Rationale */}
      {idea.rationale ? (
        <p className="text-[11.5px] text-mist/80 leading-[1.4] line-clamp-2 mb-2">
          {idea.rationale}
        </p>
      ) : null}

      {/* Footer: type badge + source */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          {idea.idea_type ? (
            <span className="text-[10px] font-mono uppercase tracking-[0.12em] text-mist/70 border border-hairline rounded-full px-1.5 py-0.5">
              {idea.idea_type}
            </span>
          ) : null}
        </div>
        <span className="text-[10.5px] font-mono text-mist/60 truncate">
          {idea.source_type}
        </span>
      </div>
    </div>
  );
}
