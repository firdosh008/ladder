import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { CSSProperties } from "react";
import { Trash, ArrowSquareOut } from "@phosphor-icons/react";
import { useNavigate } from "react-router-dom";
import { Badge } from "../ui/Badge";
import { cn } from "../../lib/cn";
import type { KanbanCard as KanbanCardType } from "./types";

type Props = {
  card: KanbanCardType;
  onClick?: (id: string) => void;
  onDelete?: (id: string) => void | Promise<void>;
};

export function KanbanCardView({ card, onClick, onDelete }: Props) {
  const navigate = useNavigate();
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: card.id });

  const style: CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  function handleDelete(e: React.MouseEvent | React.PointerEvent | React.KeyboardEvent) {
    e.stopPropagation();
    if (!onDelete) return;
    if (!window.confirm(`Delete "${card.title}"? This cannot be undone.`)) return;
    void onDelete(card.id);
  }

  function handleOpenStudio(e: React.MouseEvent | React.PointerEvent | React.KeyboardEvent) {
    e.stopPropagation();
    navigate(`/studio/${card.id}`);
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={(e) => {
        if (isDragging) return;
        if (e.detail !== 1) return;
        onClick?.(card.id);
      }}
      className={cn(
        "group relative rounded-lg border border-hairline bg-surface px-3.5 py-3",
        "cursor-grab active:cursor-grabbing select-none",
        "transition-all duration-200 ease-spring",
        "hover:border-hairline-strong hover:-translate-y-[1px]",
        "hover:shadow-[0_4px_18px_-10px_rgba(0,0,0,0.6)]",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-cinnabar",
        isDragging && "opacity-30",
      )}
    >
      <div className="absolute top-1.5 right-1.5 z-10 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity duration-150">
        <button
          type="button"
          aria-label={`Open ${card.title} in Studio`}
          title="Open in Studio"
          onClick={handleOpenStudio}
          onPointerDown={(e) => e.stopPropagation()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              handleOpenStudio(e);
            }
          }}
          className={cn(
            "inline-flex items-center justify-center h-6 w-6 rounded",
            "text-mist hover:text-cinnabar hover:bg-cinnabar/10",
            "transition-colors duration-150",
          )}
        >
          <ArrowSquareOut size={12} weight="bold" />
        </button>
        {onDelete ? (
          <button
            type="button"
            aria-label={`Delete ${card.title}`}
            title="Delete"
            onClick={handleDelete}
            onPointerDown={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                handleDelete(e);
              }
            }}
            className={cn(
              "inline-flex items-center justify-center h-6 w-6 rounded",
              "text-mist hover:text-cinnabar hover:bg-cinnabar/10",
              "transition-colors duration-150",
            )}
          >
            <Trash size={12} weight="bold" />
          </button>
        ) : null}
      </div>
      <div className="flex items-start justify-between gap-2 mb-2.5 pr-12">
        <span className="text-[13.5px] text-white leading-[1.35] font-medium line-clamp-2 tracking-[-0.005em]">
          {card.title}
        </span>
        {card.score != null ? (
          <Badge
            tone={card.score >= 90 ? "cinnabar" : "neutral"}
            className="shrink-0"
          >
            {card.score}
          </Badge>
        ) : null}
      </div>
      {(card.subtitle || card.meta) ? (
        <div className="flex items-center justify-between font-mono text-[10.5px] text-mist/80">
          <span className="truncate">{card.subtitle ?? ""}</span>
          <span className="shrink-0">{card.meta ?? ""}</span>
        </div>
      ) : null}
    </div>
  );
}

/** Non-sortable render used inside <DragOverlay>. */
export function KanbanCardOverlay({ card }: { card: KanbanCardType }) {
  return (
    <div
      className={cn(
        "w-full rounded-lg border border-hairline-strong bg-surface-raised px-3.5 py-3",
        "shadow-[0_18px_40px_-12px_rgba(0,0,0,0.8),0_6px_14px_-6px_rgba(232,68,42,0.18)]",
        "rotate-[1.5deg] cursor-grabbing",
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-2.5 pr-12">
        <span className="text-[13.5px] text-white leading-[1.35] font-medium line-clamp-2 tracking-[-0.005em]">
          {card.title}
        </span>
        {card.score != null ? (
          <Badge
            tone={card.score >= 90 ? "cinnabar" : "neutral"}
            className="shrink-0"
          >
            {card.score}
          </Badge>
        ) : null}
      </div>
      {(card.subtitle || card.meta) ? (
        <div className="flex items-center justify-between font-mono text-[10.5px] text-mist/80">
          <span className="truncate">{card.subtitle ?? ""}</span>
          <span className="shrink-0">{card.meta ?? ""}</span>
        </div>
      ) : null}
    </div>
  );
}
