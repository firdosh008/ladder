import { useState } from "react";
import {
  FileText,
  Lightbulb,
  YoutubeLogo,
  FileMd,
  ClipboardText,
  Trash,
  Graph,
} from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { useAccumulated, useKnowledge } from "../../lib/useKnowledge";
import { cn } from "../../lib/cn";
import type { AccumulatedEntry } from "../../lib/useKnowledge";

const ICON_MAP: Record<string, typeof Lightbulb> = {
  idea: Lightbulb,
  script: FileText,
  yt_transcript: YoutubeLogo,
  skill_file: FileMd,
  extract: ClipboardText,
};

export default function AccumulatedFeed() {
  const { entries, loading, error, refresh, removeEntry } = useAccumulated();
  const { deleteKnowledge } = useKnowledge();
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  async function handleDelete(id: string) {
    if (confirmDelete !== id) {
      setConfirmDelete(id);
      setTimeout(() => setConfirmDelete(null), 3000);
      return;
    }
    try {
      await deleteKnowledge(id);
      removeEntry(id);
    } catch {
      refresh();
    }
    setConfirmDelete(null);
  }

  return (
    <div className="space-y-3">
      <h3 className="text-[13px] text-white font-medium">
        Auto-accumulated knowledge
      </h3>

      {loading && entries.length === 0 && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-16 rounded-lg bg-white/[0.04] animate-pulse"
            />
          ))}
        </div>
      )}

      {!loading && !error && entries.length === 0 && (
        <div className="rounded-lg border border-hairline bg-surface p-8 text-center">
          <Graph size={20} className="text-mist mx-auto mb-2" />
          <p className="text-[13px] text-white mb-1">
            No knowledge accumulated yet
          </p>
          <p className="text-[12px] text-mist">
            Generated scripts and processed sources will appear here
            automatically.
          </p>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-hairline bg-surface p-4 text-center">
          <p className="text-[12.5px] text-sienna mb-2">{error}</p>
          <button
            onClick={refresh}
            className="text-[12px] text-cinnabar hover:underline"
          >
            Retry
          </button>
        </div>
      )}

      {entries.length > 0 && (
        <div className="space-y-1.5">
          {entries.map((entry) => (
            <AccumulatedEntryRow
              key={entry.id}
              entry={entry}
              confirmDelete={confirmDelete === entry.id}
              onDelete={() => handleDelete(entry.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AccumulatedEntryRow({
  entry,
  confirmDelete,
  onDelete,
}: {
  entry: AccumulatedEntry;
  confirmDelete: boolean;
  onDelete: () => void;
}) {
  const Icon = ICON_MAP[entry.source_type] ?? Lightbulb;
  const label =
    entry.source_type === "yt_transcript"
      ? "Transcript"
      : entry.source_type === "skill_file"
        ? "Skill file"
        : entry.source_type === "extract"
          ? "Extracted"
          : entry.source_type === "idea"
            ? "Idea"
            : "Script";

  const content = (
    <div className="flex items-start gap-3 flex-1 min-w-0">
      <div className="shrink-0 mt-0.5 text-mist">
        <Icon size={15} weight="regular" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          {entry.session_id ? (
            <Link
              to={`/studio/${entry.session_id}`}
              className="text-[13px] text-white font-medium truncate hover:text-cinnabar transition-colors"
            >
              {entry.source_title || `Untitled ${label}`}
            </Link>
          ) : (
            <span className="text-[13px] text-white font-medium truncate">
              {entry.source_title || `Untitled ${label}`}
            </span>
          )}
          <code className="font-mono text-[10px] text-mist bg-white/[0.06] rounded px-1.5 py-0.5 shrink-0">
            {label}
          </code>
        </div>
        {entry.summary && (
          <p className="text-[12.5px] text-white/55 line-clamp-2">
            {entry.summary}
          </p>
        )}
        <p className="font-mono text-[10.5px] text-mist mt-1">
          {entry.created_at
            ? new Date(entry.created_at).toLocaleDateString()
            : ""}
        </p>
      </div>
    </div>
  );

  return (
    <div className="rounded-lg border border-hairline bg-white/[0.02] px-4 py-3 flex items-start gap-3">
      {entry.session_id ? (
        <Link
          to={`/studio/${entry.session_id}`}
          className="flex items-start gap-3 flex-1 min-w-0 hover:bg-white/[0.02] -mx-2 -my-1 px-2 py-1 rounded transition-colors"
        >
          {content}
        </Link>
      ) : (
        <div className="flex-1 min-w-0">{content}</div>
      )}
      <button
        onClick={onDelete}
        className={cn(
          "shrink-0 p-1.5 rounded transition-colors mt-0.5",
          confirmDelete
            ? "bg-sienna/20 text-sienna"
            : "text-mist hover:text-white hover:bg-white/[0.06]",
        )}
        title={confirmDelete ? "Click again to confirm" : "Remove from graph"}
      >
        <Trash size={13} weight="regular" />
      </button>
    </div>
  );
}
