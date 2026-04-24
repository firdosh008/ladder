import { useEffect, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useNavigate } from "react-router-dom";
import { X, Trash, ArrowRight, Link as LinkIcon } from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { Textarea } from "../ui/Input";
import { cn } from "../../lib/cn";
import type { Idea } from "../../lib/useIdeas";
import type { KanbanStatus } from "./types";
import { KANBAN_COLUMNS } from "./types";

export type CardDetailSheetProps = {
  idea: Idea | null;
  open: boolean;
  onClose: () => void;
  onSave: (id: string, patch: Partial<Idea>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

type Editable = {
  title: string;
  body: string;
  status: KanbanStatus;
  opportunity_score: number | null;
  rationale: string;
};

function seedFrom(idea: Idea | null): Editable {
  return {
    title: idea?.title ?? "",
    body: idea?.body ?? "",
    status: (idea?.status as KanbanStatus) ?? "new",
    opportunity_score: idea?.opportunity_score ?? null,
    rationale: idea?.rationale ?? "",
  };
}

export function CardDetailSheet({
  idea,
  open,
  onClose,
  onSave,
  onDelete,
}: CardDetailSheetProps) {
  const navigate = useNavigate();
  const [edit, setEdit] = useState<Editable>(() => seedFrom(idea));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setEdit(seedFrom(idea));
    setErr(null);
  }, [idea?.id]);

  const original = seedFrom(idea);
  const dirty = JSON.stringify(original) !== JSON.stringify(edit);

  function requestClose() {
    if (dirty && !window.confirm("Discard unsaved changes?")) return;
    onClose();
  }

  async function save() {
    if (!idea) return;
    setBusy(true);
    setErr(null);
    try {
      const patch: Partial<Idea> = {};
      if (edit.title !== original.title) patch.title = edit.title;
      if (edit.body !== original.body) patch.body = edit.body || null;
      if (edit.status !== original.status) patch.status = edit.status;
      if (edit.opportunity_score !== original.opportunity_score) {
        patch.opportunity_score = edit.opportunity_score;
      }
      if (edit.rationale !== original.rationale) {
        patch.rationale = edit.rationale || null;
      }
      await onSave(idea.id, patch);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setBusy(false);
    }
  }

  async function del() {
    if (!idea) return;
    if (!window.confirm("Delete this idea? This cannot be undone.")) return;
    setBusy(true);
    setErr(null);
    try {
      await onDelete(idea.id);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to delete");
      setBusy(false);
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) requestClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay
          className={cn(
            "fixed inset-0 z-40 bg-black/60 backdrop-blur-[2px]",
            "data-[state=open]:animate-fade-in data-[state=closed]:animate-fade-out",
          )}
        />
        <Dialog.Content
          className={cn(
            "fixed right-0 top-0 bottom-0 w-full sm:w-[480px] z-50",
            "bg-night border-l border-hairline overflow-y-auto focus:outline-none",
            "flex flex-col",
            "data-[state=open]:animate-slide-in-right data-[state=closed]:animate-slide-out-right",
          )}
          aria-describedby={undefined}
        >
          {idea ? (
            <>
              {/* Header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-hairline">
                <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist">
                  idea · #{idea.id.slice(0, 8)}
                </span>
                <Dialog.Close asChild>
                  <button
                    type="button"
                    onClick={requestClose}
                    className="text-mist hover:text-white transition-colors"
                    aria-label="Close"
                  >
                    <X size={16} weight="bold" />
                  </button>
                </Dialog.Close>
              </div>

              {/* Title */}
              <div className="px-6 pt-5 pb-3">
                <Dialog.Title asChild>
                  <input
                    value={edit.title}
                    onChange={(e) =>
                      setEdit((s) => ({ ...s, title: e.target.value }))
                    }
                    placeholder="Untitled idea"
                    className={cn(
                      "w-full font-display text-[22px] text-white bg-transparent outline-none",
                      "border-b border-transparent focus:border-hairline pb-1",
                    )}
                  />
                </Dialog.Title>
              </div>

              {/* Status segmented */}
              <div className="px-6 py-4 border-t border-hairline">
                <Label>status</Label>
                <div className="flex flex-wrap gap-1.5">
                  {KANBAN_COLUMNS.map((col) => {
                    const active = edit.status === col.id;
                    return (
                      <button
                        key={col.id}
                        type="button"
                        onClick={() =>
                          setEdit((s) => ({ ...s, status: col.id }))
                        }
                        className={cn(
                          "rounded-full px-3 h-7 text-[12px] transition-colors",
                          active
                            ? "bg-cinnabar text-white border border-cinnabar"
                            : "bg-transparent text-mist border border-hairline hover:text-white hover:border-hairline-strong",
                        )}
                      >
                        {col.title}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Score */}
              <div className="px-6 py-4 border-t border-hairline">
                <Label>opportunity score</Label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={edit.opportunity_score ?? ""}
                  onChange={(e) => {
                    const v = e.target.value;
                    setEdit((s) => ({
                      ...s,
                      opportunity_score:
                        v === ""
                          ? null
                          : Math.max(0, Math.min(100, Number(v))),
                    }));
                  }}
                  placeholder="—"
                  className={cn(
                    "w-24 h-9 px-3 rounded-md bg-surface-input text-[14px] text-white",
                    "border border-transparent focus:border-cinnabar focus:outline-none",
                  )}
                />
              </div>

              {/* Body */}
              <div className="px-6 py-4 border-t border-hairline">
                <Label>body</Label>
                <Textarea
                  value={edit.body}
                  onChange={(e) =>
                    setEdit((s) => ({ ...s, body: e.target.value }))
                  }
                  placeholder="Longer notes…"
                  className="min-h-[120px]"
                />
              </div>

              {/* Rationale */}
              <div className="px-6 py-4 border-t border-hairline">
                <Label>rationale</Label>
                <Textarea
                  value={edit.rationale}
                  onChange={(e) =>
                    setEdit((s) => ({ ...s, rationale: e.target.value }))
                  }
                  placeholder="Why this one?"
                  className="min-h-[80px]"
                />
              </div>

              {/* Source */}
              <div className="px-6 py-4 border-t border-hairline">
                <Label>source</Label>
                <div className="flex flex-wrap items-center gap-2 font-mono text-[11.5px] text-mist">
                  <span className="rounded-full border border-hairline px-2 py-0.5 text-white/80">
                    {idea.source_type}
                  </span>
                  <span>·</span>
                  <span>created {new Date(idea.created_at).toLocaleString()}</span>
                  {idea.source_content_url ? (
                    <>
                      <span>·</span>
                      <a
                        href={idea.source_content_url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-cinnabar hover:underline underline-offset-2"
                      >
                        <LinkIcon size={10} weight="bold" />
                        source
                      </a>
                    </>
                  ) : null}
                </div>
              </div>

              <div className="flex-1" />

              {err ? (
                <div className="mx-6 mb-3 rounded border border-cinnabar/40 bg-cinnabar/[0.06] text-cinnabar px-3 py-2 text-[12px]">
                  {err}
                </div>
              ) : null}

              {/* Footer */}
              <div className="sticky bottom-0 bg-night border-t border-hairline px-6 py-4 flex items-center justify-between gap-2">
                {edit.status !== "new" ? (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() =>
                      navigate(`/studio/new?ideaId=${encodeURIComponent(idea.id)}`)
                    }
                  >
                    Open in Studio
                    <ArrowRight size={12} weight="bold" />
                  </Button>
                ) : (
                  <span />
                )}

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={del}
                    disabled={busy}
                    className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-md text-[12.5px] text-mist hover:text-cinnabar transition-colors disabled:opacity-40"
                  >
                    <Trash size={12} weight="bold" />
                    Delete
                  </button>
                  <Button
                    size="sm"
                    onClick={() => void save()}
                    disabled={busy || !dirty}
                  >
                    {busy ? "Saving…" : dirty ? "Save" : "Saved"}
                    {dirty && !busy ? (
                      <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-white/80" />
                    ) : null}
                  </Button>
                </div>
              </div>
            </>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-2">
      {children}
    </div>
  );
}
