import { useState } from "react";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import { useDroppable } from "@dnd-kit/core";
import { Plus } from "@phosphor-icons/react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "../../lib/cn";
import type { KanbanCard as KanbanCardType, KanbanStatus } from "./types";
import { KanbanCardView } from "./Card";
import { AddCardInline } from "./AddCardInline";

type Props = {
  columnId: KanbanStatus;
  title: string;
  hint?: string;
  cards: KanbanCardType[];
  emptyCopy?: string;
  onAdd: (title: string) => void | Promise<void>;
  onCardClick?: (id: string) => void;
};

// On-brand column-dot colors — stay within tailwind tokens.
const COLUMN_DOT: Record<KanbanStatus, string> = {
  new: "bg-cinnabar",
  scripting: "bg-sienna",
  scene: "bg-bone",
  ready: "bg-cinnabar/70",
  published: "bg-mist",
};

export function KanbanColumnView({
  columnId,
  title,
  hint,
  cards,
  emptyCopy,
  onAdd,
  onCardClick,
}: Props) {
  const [adding, setAdding] = useState(false);
  const { setNodeRef, isOver } = useDroppable({
    id: `column:${columnId}`,
    data: { columnId, type: "column" },
  });

  async function handleSubmit(t: string) {
    await onAdd(t);
  }

  const cardIds = cards.map((c) => c.id);

  return (
    <div className="min-w-[300px] w-[300px] shrink-0 flex flex-col">
      {/* Header — Notion-style status pill */}
      <div className="flex items-center justify-between px-1 pb-2.5">
        <div
          className={cn(
            "inline-flex items-center gap-2 rounded-md px-2 py-1",
            "bg-white/[0.04] border border-hairline",
          )}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full shrink-0",
              COLUMN_DOT[columnId],
            )}
          />
          <span className="text-[12.5px] font-semibold text-white/90 leading-none">
            {title}
          </span>
          <span className="font-mono text-[10.5px] text-mist tabular-nums leading-none">
            {hint ?? cards.length}
          </span>
        </div>
      </div>

      <div
        ref={setNodeRef}
        className={cn(
          "flex-1 flex flex-col gap-2 rounded-xl border p-2 transition-colors duration-200 ease-spring",
          isOver
            ? "border-cinnabar/30 bg-cinnabar/[0.025]"
            : "border-transparent bg-white/[0.015]",
        )}
      >
        <SortableContext items={cardIds} strategy={verticalListSortingStrategy}>
          <AnimatePresence initial={false} mode="popLayout">
            {cards.map((card) => (
              <motion.div
                key={card.id}
                layout
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.96 }}
                transition={{ duration: 0.18, ease: [0.32, 0.72, 0, 1] }}
              >
                <KanbanCardView card={card} onClick={onCardClick} />
              </motion.div>
            ))}
          </AnimatePresence>
        </SortableContext>

        {cards.length === 0 && !adding ? (
          <div className="flex items-center justify-center py-10 px-3">
            <p className="text-[12px] text-mist/70 text-center leading-[1.5]">
              {emptyCopy ?? "—"}
            </p>
          </div>
        ) : null}

        {adding ? (
          <AddCardInline
            onSubmit={handleSubmit}
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
