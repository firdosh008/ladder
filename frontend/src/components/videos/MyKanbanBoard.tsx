import type { KanbanData } from "../../types/videos";
import type { PublishedEntry } from "../../types/videos";
import type { ContextMenuItem } from "./ContextMenu";
import { IdeasColumn } from "./IdeasColumn";
import { InProgressColumn } from "./InProgressColumn";
import { ReadyColumn } from "./ReadyColumn";
import { PublishedColumn } from "./PublishedColumn";

type Props = {
  kanbanData: KanbanData;
  onAddIdea: (title: string) => Promise<void>;
  onMoveIdea: (cardId: string, newPosition: number) => void;
  onArchiveIdea: (id: string) => void;
  onArchiveSession: (sessionId: string) => void;
  onOpenPublishedDetail: (entry: PublishedEntry) => void;
  onContextMenu: (items: ContextMenuItem[], x: number, y: number) => void;
};

export function MyKanbanBoard({
  kanbanData,
  onAddIdea,
  onMoveIdea,
  onArchiveIdea,
  onArchiveSession,
  onOpenPublishedDetail,
  onContextMenu,
}: Props) {
  return (
    <div className="flex gap-4 overflow-x-auto pb-4 -mx-2 px-2">
      <IdeasColumn
        ideas={kanbanData.ideas}
        onAdd={onAddIdea}
        onMove={onMoveIdea}
        onArchive={onArchiveIdea}
        onContextMenu={onContextMenu}
      />
      <InProgressColumn
        entries={kanbanData.in_progress}
        onArchive={onArchiveSession}
        onContextMenu={onContextMenu}
      />
      <ReadyColumn
        entries={kanbanData.ready}
        onContextMenu={onContextMenu}
      />
      <PublishedColumn
        entries={kanbanData.published}
        youtubeConnected={kanbanData.youtube_connected}
        onCardClick={onOpenPublishedDetail}
      />
    </div>
  );
}
