import { useState } from "react";
import { Plus, X, Check, Trash } from "@phosphor-icons/react";
import { useKnowledge, type KnowledgeNode } from "../../lib/useKnowledge";
import { cn } from "../../lib/cn";

export default function ManualKnowledgeForm() {
  const { nodes, loading, error, createKnowledge, deleteKnowledge, refresh } =
    useKnowledge({ source_type: "manual" });

  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [tagInput, setTagInput] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  function addTag() {
    const t = tagInput.trim();
    if (t && !tags.includes(t)) {
      setTags((prev) => [...prev, t]);
      setTagInput("");
    }
  }

  function removeTag(t: string) {
    setTags((prev) => prev.filter((x) => x !== t));
  }

  async function handleSave() {
    if (!content.trim()) return;
    setSaving(true);
    setSaveError(null);
    setSavedOk(false);
    try {
      await createKnowledge({
        title: title.trim() || undefined,
        content_chunk: content.trim(),
        topic_tags: tags.length > 0 ? tags : undefined,
      });
      setTitle("");
      setContent("");
      setTags([]);
      setTagInput("");
      setShowForm(false);
      setSavedOk(true);
      setTimeout(() => setSavedOk(false), 2000);
    } catch (e: any) {
      setSaveError(e?.message ?? "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    setShowForm(false);
    setTitle("");
    setContent("");
    setTags([]);
    setTagInput("");
    setSaveError(null);
  }

  async function handleDelete(id: string) {
    if (confirmDelete !== id) {
      setConfirmDelete(id);
      setTimeout(() => setConfirmDelete(null), 3000);
      return;
    }
    try {
      await deleteKnowledge(id);
    } catch {
      refresh();
    }
    setConfirmDelete(null);
  }

  const manualNodes = nodes;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-[13px] text-white font-medium">
          Manual knowledge
        </h3>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className={cn(
              "inline-flex items-center gap-1.5 h-8 px-3 rounded-md",
              "bg-white/[0.06] border border-hairline",
              "text-[12.5px] text-white font-medium",
              "hover:bg-white/[0.1] transition-colors",
            )}
          >
            <Plus size={12} weight="bold" />
            Add knowledge
          </button>
        )}
      </div>

      {showForm && (
        <div className="rounded-lg border border-hairline bg-white/[0.02] p-4 space-y-3">
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title (optional)"
            className="w-full bg-white/[0.06] border border-hairline rounded-md px-3 h-9 text-[13px] text-white placeholder:text-mist focus:outline-none focus:border-white/20"
          />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Paste a framework, SOP, positioning statement, documentation, case study, or any IP you want the system to know..."
            rows={6}
            className="w-full bg-white/[0.06] border border-hairline rounded-md px-3 py-2.5 text-[13px] text-white placeholder:text-mist focus:outline-none focus:border-white/20 resize-y"
          />
          <div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={tagInput}
                onChange={(e) => setTagInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addTag();
                  }
                }}
                placeholder="Add tags (comma-separated)"
                className="flex-1 bg-white/[0.06] border border-hairline rounded-md px-3 h-8 text-[12.5px] text-white placeholder:text-mist focus:outline-none focus:border-white/20"
              />
              <button
                type="button"
                onClick={addTag}
                className="text-[12px] text-mist hover:text-white transition-colors"
              >
                add
              </button>
            </div>
            {tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {tags.map((t) => (
                  <span
                    key={t}
                    className="inline-flex items-center gap-1 font-mono text-[11px] text-white/85 bg-white/[0.08] border border-hairline rounded px-2 py-0.5"
                  >
                    {t}
                    <button
                      onClick={() => removeTag(t)}
                      className="text-mist hover:text-white"
                    >
                      <X size={10} weight="bold" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
          {saveError && (
            <p className="text-[12px] text-sienna">{saveError}</p>
          )}
          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={handleSave}
              disabled={saving || !content.trim()}
              className={cn(
                "inline-flex items-center gap-1.5 h-8 px-4 rounded-md text-[12.5px] font-medium transition-colors",
                savedOk
                  ? "bg-green-600/20 text-green-400 border border-green-600/30"
                  : "bg-cinnabar hover:bg-cinnabar-hover text-white",
                "disabled:opacity-40 disabled:cursor-not-allowed",
              )}
            >
              {savedOk && <Check size={12} weight="bold" />}
              {savedOk ? "Saved" : saving ? "Saving..." : "Save"}
            </button>
            <button
              onClick={handleCancel}
              className="h-8 px-3 rounded-md text-[12.5px] text-mist hover:text-white transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Manual entries list */}
      {loading && manualNodes.length === 0 && (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-16 rounded-lg bg-white/[0.04] animate-pulse"
            />
          ))}
        </div>
      )}

      {!loading && !error && manualNodes.length === 0 && (
        <div className="rounded-lg border border-hairline bg-surface p-6 text-center">
          <p className="text-[13px] text-mist">
            No manual knowledge yet. Add frameworks, SOPs, or documentation to
            teach the system your internal IP.
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

      {manualNodes.length > 0 && (
        <div className="space-y-1.5">
          {manualNodes.map((node) => (
            <ManualEntry
              key={node.id}
              node={node}
              confirmDelete={confirmDelete === node.id}
              onDelete={() => handleDelete(node.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ManualEntry({
  node,
  confirmDelete,
  onDelete,
}: {
  node: KnowledgeNode;
  confirmDelete: boolean;
  onDelete: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const content = node.content_chunk || "";
  const long = content.length > 200;
  const display = expanded || !long ? content : content.slice(0, 200) + "…";

  return (
    <div className="rounded-lg border border-hairline bg-white/[0.02] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[13px] text-white font-medium truncate">
              {node.title || content.slice(0, 80)}
            </span>
            {node.topic_tags && node.topic_tags.length > 0 && (
              <span className="flex gap-1">
                {node.topic_tags.map((t) => (
                  <code
                    key={t}
                    className="font-mono text-[10.5px] text-mist bg-white/[0.06] rounded px-1.5 py-0.5"
                  >
                    {t}
                  </code>
                ))}
              </span>
            )}
          </div>
          <p className="text-[12.5px] text-white/60 whitespace-pre-wrap">
            {display}
          </p>
          {long && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="text-[11.5px] text-cinnabar hover:underline mt-0.5"
            >
              {expanded ? "Show less" : "Show more"}
            </button>
          )}
          <p className="font-mono text-[10.5px] text-mist mt-1.5">
            {node.created_at
              ? new Date(node.created_at).toLocaleDateString()
              : ""}
          </p>
        </div>
        <button
          onClick={onDelete}
          className={cn(
            "shrink-0 p-1.5 rounded transition-colors",
            confirmDelete
              ? "bg-sienna/20 text-sienna"
              : "text-mist hover:text-white hover:bg-white/[0.06]",
          )}
          title={confirmDelete ? "Click again to confirm" : "Delete"}
        >
          <Trash size={13} weight="regular" />
        </button>
      </div>
    </div>
  );
}
