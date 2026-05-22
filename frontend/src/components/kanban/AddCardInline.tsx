import { useRef, useState, type KeyboardEvent } from "react";
import { cn } from "../../lib/cn";

export function AddCardInline({
  onSubmit,
  onCancel,
}: {
  onSubmit: (title: string) => void | Promise<void>;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  async function submit() {
    const t = title.trim();
    if (!t) return;
    setBusy(true);
    setErr(null);
    try {
      await onSubmit(t);
      setTitle("");
      inputRef.current?.focus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setBusy(false);
    }
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
    if (e.key === "Escape") {
      e.preventDefault();
      onCancel();
    }
  }

  return (
    <div
      className={cn(
        "rounded-lg border border-cinnabar/30 bg-surface px-3.5 py-3",
        "transition-all duration-200 ease-spring",
      )}
    >
      <textarea
        ref={inputRef}
        autoFocus
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onKeyDown={onKey}
        placeholder="Capture an idea…"
        rows={1}
        disabled={busy}
        className={cn(
          "w-full bg-transparent text-[13.5px] text-white placeholder:text-mist",
          "font-medium leading-[1.35] tracking-[-0.005em] outline-none resize-none",
        )}
      />
      {err ? (
        <p className="mt-1.5 text-[11px] text-cinnabar font-mono">{err}</p>
      ) : null}
      <div className="flex items-center justify-between mt-2">
        <span className="font-mono text-[10.5px] text-mist/70">
          enter to save · esc to cancel
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onCancel}
            className="h-6 px-2 text-[11.5px] text-mist hover:text-white transition-colors"
          >
            cancel
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || !title.trim()}
            className={cn(
              "h-6 px-2.5 rounded text-[11.5px] font-medium",
              "bg-cinnabar text-white hover:bg-cinnabar-dim",
              "disabled:opacity-40 disabled:pointer-events-none transition-colors",
            )}
          >
            {busy ? "saving…" : "add"}
          </button>
        </div>
      </div>
    </div>
  );
}
