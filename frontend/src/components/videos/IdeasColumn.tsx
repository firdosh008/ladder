import { useState, useMemo } from "react";
import {
  DndContext,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  closestCenter,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  sortableKeyboardCoordinates,
} from "@dnd-kit/sortable";
import { Plus } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "../../lib/cn";
import type { IdeaEntry } from "../../types/videos";
import type { ContextMenuItem } from "./ContextMenu";
import { IdeaCard } from "./IdeaCard";
import { AddCardInline } from "../kanban/AddCardInline";
import { computePosition } from "../kanban/position";
import { useDroppable } from "@dnd-kit/core";

type Props = {
  ideas: IdeaEntry[];
  onAdd: (title: string) => Promise<void>;
  onMove: (cardId: string, newPosition: number) => void;
  onArchive: (id: string) => void;
  onContextMenu: (items: ContextMenuItem[], x: number, y: number) => void;
};

export function IdeasColumn({
  ideas,
  onAdd,
  onMove,
  onArchive,
  onContextMenu,
}: Props) {
  const [adding, setAdding] = useState(false);
  const { setNodeRef, isOver } = useDroppable({
    id: "column:ideas",
    data: { columnId: "ideas", type: "column" },
  });

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  const cardIds = useMemo(() => ideas.map((i) => i.id), [ideas]);

  function onDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    if (!over) return;
    const cardId = String(active.id);

    const sorted = [...ideas].sort((a, b) => (a.position ?? 1e12) - (b.position ?? 1e12));

    let toIndex: number;
    if (String(over.id).startsWith("column:")) {
      toIndex = sorted.length;
    } else {
      const overIdx = sorted.findIndex((c) => c.id === String(over.id));
      if (overIdx === -1) {
        toIndex = sorted.length;
      } else {
        const fromIdx = sorted.findIndex((c) => c.id === cardId);
        toIndex = fromIdx < overIdx ? overIdx + 1 : overIdx;
      }
    }

    const neighbours = sorted
      .filter((c) => c.id !== cardId)
      .map((c) => ({ position: c.position ?? 1e12 }));
    const clampedIndex = Math.max(0, Math.min(neighbours.length, toIndex));
    const newPosition = computePosition(neighbours, clampedIndex);

    const current = ideas.find((c) => c.id === cardId);
    if (current && Math.abs((current.position ?? 1e12) - newPosition) < 1e-9) return;

    onMove(cardId, newPosition);
  }

  async function handleAdd(title: string) {
    await onAdd(title);
    setAdding(false);
  }

  return (
    <div className="min-w-[300px] w-[300px] shrink-0 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-1 pb-2.5">
        <div className="inline-flex items-center gap-2 rounded-md px-2 py-1 bg-white/[0.04] border border-hairline">
          <span className="h-1.5 w-1.5 rounded-full shrink-0 bg-cinnabar" />
          <span className="text-[12.5px] font-semibold text-white/90 leading-none">
            Ideas
          </span>
          <span className="font-mono text-[10.5px] text-mist tabular-nums leading-none">
            {ideas.length}
          </span>
        </div>
      </div>

      <div
        ref={setNodeRef}
        className={cn(
          "flex-1 flex flex-col gap-2 rounded-xl border p-2 transition-colors duration-200",
          isOver
            ? "border-cinnabar/30 bg-cinnabar/[0.025]"
            : "border-transparent bg-white/[0.015]",
        )}
      >
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={onDragEnd}
        >
          <SortableContext items={cardIds} strategy={verticalListSortingStrategy}>
            <AnimatePresence initial={false} mode="popLayout">
              {ideas.map((idea) => (
                <motion.div
                  key={idea.id}
                  layout
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.96 }}
                  transition={{ duration: 0.18, ease: [0.32, 0.72, 0, 1] }}
                >
                  <IdeaCard
                    idea={idea}
                    onArchive={onArchive}
                    onContextMenu={onContextMenu}
                  />
                </motion.div>
              ))}
            </AnimatePresence>
          </SortableContext>
        </DndContext>

        {ideas.length === 0 && !adding ? (
          <div className="flex items-center justify-center py-10 px-3">
            <p className="text-[12px] text-mist/70 text-center leading-[1.5]">
              No ideas yet. Tap + to capture one.
            </p>
          </div>
        ) : null}

        {adding ? (
          <AddCardInline
            onSubmit={handleAdd}
            onCancel={() => setAdding(false)}
          />
        ) : (
          <button
            type="button"
            onClick={() => setAdding(true)}
            className={cn(
              "group mt-auto inline-flex items-center gap-1.5 rounded-md px-2.5 py-2",
              "text-[12.5px] text-mist hover:text-white",
              "hover:bg-white/[0.035] transition-colors duration-150",
            )}
          >
            <Plus size={12} weight="bold" />
            <span>New idea</span>
          </button>
        )}
      </div>
    </div>
  );
}
