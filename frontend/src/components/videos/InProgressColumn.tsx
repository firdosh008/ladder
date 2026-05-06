import { cn } from "../../lib/cn";
import type { InProgressEntry } from "../../types/videos";
import type { ContextMenuItem } from "./ContextMenu";
import { SessionCard } from "./SessionCard";

type Props = {
  entries: InProgressEntry[];
  onArchive: (sessionId: string) => void;
  onContextMenu: (items: ContextMenuItem[], x: number, y: number) => void;
};

export function InProgressColumn({ entries, onArchive, onContextMenu }: Props) {
  const sorted = [...entries].sort(
    (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
  );

  return (
    <div className="min-w-[300px] w-[300px] shrink-0 flex flex-col">
      <div className="flex items-center justify-between px-1 pb-2.5">
        <div className="inline-flex items-center gap-2 rounded-md px-2 py-1 bg-white/[0.04] border border-hairline">
          <span className="h-1.5 w-1.5 rounded-full shrink-0 bg-sienna" />
          <span className="text-[12.5px] font-semibold text-white/90 leading-none">
            In Progress
          </span>
          <span className="font-mono text-[10.5px] text-mist tabular-nums leading-none">
            {entries.length}
          </span>
        </div>
      </div>

      <div
        className={cn(
          "flex-1 flex flex-col gap-2 rounded-xl border p-2",
          "border-transparent bg-white/[0.015]",
        )}
      >
        {sorted.length === 0 ? (
          <div className="flex items-center justify-center py-10 px-3">
            <p className="text-[12px] text-mist/70 text-center leading-[1.5]">
              No videos in progress. Start one from Ideas.
            </p>
          </div>
        ) : (
          sorted.map((entry) => (
            <SessionCard
              key={entry.session_id}
              entry={entry}
              onArchive={onArchive}
              onContextMenu={onContextMenu}
            />
          ))
        )}
      </div>
    </div>
  );
}
