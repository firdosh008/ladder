import { useEffect, useState } from "react";
import { Pencil, FloppyDisk, X, Plus, Trash } from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/cn";
import { saveOutline, type Outline, type OutlineItem } from "../../lib/agents";

type Props = {
  outline: Outline | null;
  sessionId: string | null;
  /** Apply persisted outline back to the parent's stream state. */
  onSaved: (outline: Outline) => void;
};

/**
 * Inline outline editor.
 *
 * Read mode mirrors the streaming OutlineView. Edit mode swaps each item
 * for label + beat textareas, lets the founder add/remove rows, and POSTs
 * the new outline as a versioned `outline` artifact via `saveOutline`.
 * Previous versions stay in the artifacts table (matches the streaming
 * persist semantics).
 */
export function OutlineEditor({ outline, sessionId, onSaved }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<OutlineItem[]>(outline?.items ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!editing) setDraft(outline?.items ?? []);
  }, [outline, editing]);

  if (!outline) return null;

  const updateItem = (index: number, patch: Partial<OutlineItem>) => {
    setDraft((prev) =>
      prev.map((it, i) => (i === index ? { ...it, ...patch } : it)),
    );
  };

  const addItem = () => {
    setDraft((prev) => [
      ...prev,
      {
        number: prev.length + 1,
        label: "New beat",
        beat: "",
      },
    ]);
  };

  const removeItem = (index: number) => {
    setDraft((prev) =>
      prev
        .filter((_, i) => i !== index)
        .map((it, i) => ({ ...it, number: i + 1 })),
    );
  };

  const cancel = () => {
    setError(null);
    setDraft(outline.items);
    setEditing(false);
  };

  const commit = async () => {
    if (!sessionId) {
      setError("No session yet — wait for the script to finish streaming.");
      return;
    }
    const cleaned: OutlineItem[] = draft
      .map((it, i) => ({
        number: i + 1,
        label: it.label.trim(),
        beat: it.beat.trim(),
      }))
      .filter((it) => it.label || it.beat);
    if (cleaned.length === 0) {
      setError("Outline needs at least one beat.");
      return;
    }
    const next: Outline = { items: cleaned };
    setSaving(true);
    setError(null);
    try {
      await saveOutline(sessionId, next);
      onSaved(next);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <div className="space-y-2.5">
        <div className="flex items-center justify-between gap-2">
          <p className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
            scene outline · {outline.items.length} beats
          </p>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setEditing(true)}
            title="Edit the outline before building the scene"
          >
            <Pencil size={11} weight="bold" />
            Edit
          </Button>
        </div>
        <ol className="space-y-2.5">
          {outline.items.map((it) => (
            <li
              key={it.number}
              className="rounded-md border border-hairline bg-surface p-3"
            >
              <div className="flex items-baseline gap-2.5 mb-1">
                <span className="font-mono text-[10.5px] tabular-nums text-mist tracking-[0.18em] uppercase shrink-0">
                  {String(it.number).padStart(2, "0")}
                </span>
                <span className="font-sans font-semibold text-[13.5px] text-white leading-tight">
                  {it.label}
                </span>
              </div>
              <p className="text-[12.5px] text-white/80 leading-[1.55] pl-[26px]">
                {it.beat}
              </p>
            </li>
          ))}
        </ol>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <p className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-cinnabar">
          editing outline · saves a new version
        </p>
        <div className="flex items-center gap-1.5">
          <Button variant="ghost" size="sm" onClick={cancel} disabled={saving}>
            <X size={11} weight="bold" />
            Cancel
          </Button>
          <Button variant="primary" size="sm" onClick={commit} disabled={saving}>
            <FloppyDisk size={11} weight="bold" />
            {saving ? "Saving…" : "Save outline"}
          </Button>
        </div>
      </div>
      <ol className="space-y-2.5">
        {draft.map((it, i) => (
          <li
            key={i}
            className={cn(
              "rounded-md border border-hairline bg-surface p-3",
              "focus-within:border-cinnabar/40",
            )}
          >
            <div className="flex items-center gap-2.5 mb-1.5">
              <span className="font-mono text-[10.5px] tabular-nums text-mist tracking-[0.18em] uppercase shrink-0">
                {String(i + 1).padStart(2, "0")}
              </span>
              <input
                value={it.label}
                onChange={(e) => updateItem(i, { label: e.target.value })}
                placeholder="Beat label"
                className={cn(
                  "flex-1 bg-transparent border-0 outline-none",
                  "font-sans font-semibold text-[13.5px] text-white leading-tight",
                )}
              />
              <button
                type="button"
                onClick={() => removeItem(i)}
                title="Remove beat"
                className="text-mist hover:text-cinnabar transition-colors"
              >
                <Trash size={12} weight="bold" />
              </button>
            </div>
            <textarea
              value={it.beat}
              onChange={(e) => updateItem(i, { beat: e.target.value })}
              placeholder="What happens in this beat"
              rows={2}
              className={cn(
                "w-full pl-[26px] pr-1 bg-transparent border-0 outline-none resize-none",
                "text-[12.5px] text-white/85 leading-[1.55]",
              )}
            />
          </li>
        ))}
      </ol>
      <button
        type="button"
        onClick={addItem}
        className={cn(
          "w-full flex items-center justify-center gap-1.5 h-8 rounded-md",
          "border border-dashed border-hairline text-mist",
          "hover:text-white hover:border-hairline-strong transition-colors",
          "text-[12px]",
        )}
      >
        <Plus size={11} weight="bold" />
        Add beat
      </button>
      {error ? (
        <p className="font-mono text-[11px] text-cinnabar">{error}</p>
      ) : null}
    </div>
  );
}
