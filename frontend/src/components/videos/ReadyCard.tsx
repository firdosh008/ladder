import { ArrowSquareOut, VideoCamera } from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { cn } from "../../lib/cn";
import type { ReadyEntry } from "../../types/videos";
import type { ContextMenuItem } from "./ContextMenu";

function fmtDuration(min: number | null | undefined): string {
  if (min == null) return "--";
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

type Props = {
  entry: ReadyEntry;
  onContextMenu: (items: ContextMenuItem[], x: number, y: number) => void;
};

export function ReadyCard({ entry, onContextMenu }: Props) {
  function handleContextMenu(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    onContextMenu(
      [
        { label: "Use as template", onClick: () => {} },
        { label: "Archive", onClick: () => {}, destructive: true },
      ],
      e.clientX,
      e.clientY,
    );
  }

  function openExcalidraw() {
    if (entry.excalidraw_url) {
      window.open(entry.excalidraw_url, "_blank", "noopener,noreferrer");
    }
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
      {/* Thumbnail */}
      <div className="mb-3 rounded-md overflow-hidden bg-surface-input aspect-video flex items-center justify-center">
        {entry.thumbnail_url ? (
          <img
            src={entry.thumbnail_url}
            alt={entry.title}
            className="w-full h-full object-cover"
            loading="lazy"
          />
        ) : (
          <VideoCamera size={20} weight="bold" className="text-mist/40" />
        )}
      </div>

      {/* Title */}
      <span className="text-[13.5px] text-white leading-[1.35] font-medium line-clamp-2 block mb-2">
        {entry.title}
      </span>

      {/* Meta */}
      <div className="flex items-center justify-between gap-2 mb-3">
        {entry.idea_type ? (
          <Badge tone="neutral">{entry.idea_type}</Badge>
        ) : null}
        <span className="text-[10.5px] font-mono text-mist/70">
          {fmtDuration(entry.target_duration_min)}
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          onClick={openExcalidraw}
          disabled={!entry.excalidraw_url}
          className="flex-1"
        >
          Open Excalidraw
          <ArrowSquareOut size={11} weight="bold" />
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() =>
            window.open("https://loom.com/record", "_blank", "noopener,noreferrer")
          }
          className="shrink-0"
        >
          <VideoCamera size={11} weight="bold" />
          Loom
        </Button>
      </div>
    </div>
  );
}
