import { useMemo, useState } from "react";
import {
  DndContext,
  DragOverlay,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  closestCenter,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { createPortal } from "react-dom";
import type {
  KanbanCard as KanbanCardType,
  KanbanColumn,
  KanbanMoveEvent,
  KanbanStatus,
} from "./types";
import { KanbanColumnView } from "./Column";
import { KanbanCardOverlay } from "./Card";
import { computePosition } from "./position";

export type KanbanBoardProps = {
  columns: KanbanColumn[];
  cards: KanbanCardType[];
  onMove: (e: KanbanMoveEvent) => void | Promise<void>;
  onAdd: (columnId: KanbanStatus, title: string) => void | Promise<void>;
  onCardClick?: (cardId: string) => void;
  onCardDelete?: (cardId: string) => void | Promise<void>;
  isLoading?: boolean;
  emptyCopyByColumn?: Partial<Record<KanbanStatus, string>>;
};

export function KanbanBoard({
  columns,
  cards,
  onMove,
  onAdd,
  onCardClick,
  onCardDelete,
  emptyCopyByColumn,
}: KanbanBoardProps) {
  const [activeId, setActiveId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const cardsByColumn = useMemo(() => {
    const map = new Map<KanbanStatus, KanbanCardType[]>();
    for (const col of columns) map.set(col.id, []);
    for (const card of cards) {
      const arr = map.get(card.columnId);
      if (arr) arr.push(card);
    }
    for (const arr of map.values()) arr.sort((a, b) => a.position - b.position);
    return map;
  }, [cards, columns]);

  const activeCard = activeId
    ? cards.find((c) => c.id === activeId) ?? null
    : null;

  function cardColumn(id: string): KanbanStatus | null {
    return cards.find((c) => c.id === id)?.columnId ?? null;
  }

  function resolveColumn(overId: string): KanbanStatus | null {
    if (overId.startsWith("column:")) {
      return overId.slice("column:".length) as KanbanStatus;
    }
    return cardColumn(overId);
  }

  function onDragStart(e: DragStartEvent) {
    setActiveId(String(e.active.id));
  }

  function onDragEnd(e: DragEndEvent) {
    setActiveId(null);
    const { active, over } = e;
    if (!over) return;

    const cardId = String(active.id);
    const fromColumnId = cardColumn(cardId);
    const toColumnId = resolveColumn(String(over.id));
    if (!fromColumnId || !toColumnId) return;

    const toColumnCards = cardsByColumn.get(toColumnId) ?? [];

    // Compute drop index
    let toIndex: number;
    if (String(over.id).startsWith("column:")) {
      toIndex = toColumnCards.length; // dropped on empty area → append
    } else {
      const overIndex = toColumnCards.findIndex((c) => c.id === String(over.id));
      if (overIndex === -1) {
        toIndex = toColumnCards.length;
      } else if (fromColumnId === toColumnId) {
        // intra-column: dnd-kit gives the index of the card we swapped with.
        const fromIndex = toColumnCards.findIndex((c) => c.id === cardId);
        toIndex = fromIndex < overIndex ? overIndex + 1 : overIndex;
      } else {
        toIndex = overIndex;
      }
    }

    // Exclude the card itself when computing neighbours for intra-column move.
    const neighbours =
      fromColumnId === toColumnId
        ? toColumnCards.filter((c) => c.id !== cardId)
        : toColumnCards;

    const clampedIndex = Math.max(
      0,
      Math.min(neighbours.length, fromColumnId === toColumnId && toIndex > 0 ? toIndex - 1 : toIndex),
    );

    const newPosition = computePosition(neighbours, clampedIndex);

    // No-op if same column and the computed position matches the current one.
    const current = cards.find((c) => c.id === cardId);
    if (
      fromColumnId === toColumnId &&
      current &&
      Math.abs(current.position - newPosition) < 1e-9
    ) {
      return;
    }

    void onMove({ cardId, fromColumnId, toColumnId, newPosition });
  }

  function announcement(event: string, id?: string, col?: string): string {
    const title = id ? cards.find((c) => c.id === id)?.title ?? id : "";
    if (event === "start") return `Picked up card "${title}"`;
    if (event === "over" && col) return `"${title}" is over "${col}"`;
    if (event === "end" && col) return `Dropped "${title}" into "${col}"`;
    return "Drag cancelled";
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onDragCancel={() => setActiveId(null)}
      accessibility={{
        announcements: {
          onDragStart: ({ active }) => announcement("start", String(active.id)),
          onDragOver: ({ active, over }) =>
            announcement(
              "over",
              String(active.id),
              over ? resolveColumn(String(over.id)) ?? "" : "",
            ),
          onDragEnd: ({ active, over }) =>
            announcement(
              "end",
              String(active.id),
              over ? resolveColumn(String(over.id)) ?? "" : "",
            ),
          onDragCancel: () => "Drag cancelled",
        },
      }}
    >
      <div className="flex gap-4 overflow-x-auto pb-4 -mx-2 px-2">
        {columns.map((col) => (
          <KanbanColumnView
            key={col.id}
            columnId={col.id}
            title={col.title}
            hint={col.hint}
            cards={cardsByColumn.get(col.id) ?? []}
            emptyCopy={emptyCopyByColumn?.[col.id]}
            onAdd={(t) => onAdd(col.id, t)}
            onCardClick={onCardClick}
            onCardDelete={onCardDelete}
          />
        ))}
      </div>

      {typeof document !== "undefined"
        ? createPortal(
            <DragOverlay dropAnimation={null}>
              {activeCard ? <KanbanCardOverlay card={activeCard} /> : null}
            </DragOverlay>,
            document.body,
          )
        : null}
    </DndContext>
  );
}
