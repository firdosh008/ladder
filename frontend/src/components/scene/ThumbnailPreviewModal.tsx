import { useCallback, useState } from "react";
import {
  Image as ImageIcon,
  Spinner,
  CheckCircle,
  Warning,
  PencilSimple,
  Lightning,
} from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/cn";
import {
  runThumbnailStream,
  selectThumbnail,
  refineThumbnail,
  type AgentEvent,
  type ThumbnailVariant,
} from "../../lib/agents";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string;
  variants: ThumbnailVariant[];
  onVariantsGenerated: (variants: ThumbnailVariant[]) => void;
  onGeneratingChange: (generating: boolean) => void;
  onSelected?: (artifactId: string) => void;
};

type Status = "idle" | "generating" | "ready" | "failed";

export function ThumbnailPreviewModal({
  open,
  onOpenChange,
  sessionId,
  variants,
  onVariantsGenerated,
  onGeneratingChange,
  onSelected,
}: Props) {
  const [referenceUrl, setReferenceUrl] = useState("");
  const [status, setStatus] = useState<Status>(
    variants.length > 0 ? "ready" : "idle",
  );
  const [streamText, setStreamText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [refiningId, setRefiningId] = useState<string | null>(null);
  const [refineInput, setRefineInput] = useState("");
  const [refineLoading, setRefineLoading] = useState(false);

  const hasVariants = variants.length > 0;

  const handleGenerate = useCallback(async () => {
    setStatus("generating");
    setError(null);
    setStreamText("");
    onGeneratingChange(true);

    const handle = (ev: AgentEvent) => {
      switch (ev.type) {
        case "agent_start":
          setStreamText((p) => p + `Starting ${ev.agent}…\n`);
          break;
        case "text_delta":
          setStreamText((p) => p + ev.content);
          break;
        case "error":
          setError(ev.message);
          break;
      }
    };

    try {
      const result = await runThumbnailStream(
        sessionId,
        referenceUrl || null,
        handle,
      );
      setStatus("ready");
      onVariantsGenerated(result.variants);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStatus("failed");
    } finally {
      onGeneratingChange(false);
    }
  }, [sessionId, referenceUrl, onVariantsGenerated, onGeneratingChange]);

  const handleSelect = useCallback(
    async (artifactId: string) => {
      try {
        await selectThumbnail(sessionId, artifactId);
        setSelectedId(artifactId);
        onSelected?.(artifactId);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [sessionId, onSelected],
  );

  const handleRefine = useCallback(
    async (artifactId: string) => {
      if (!refineInput.trim()) return;
      setRefineLoading(true);
      setError(null);
      try {
        const result = await refineThumbnail(
          sessionId,
          artifactId,
          refineInput.trim(),
        );
        onVariantsGenerated([
          ...variants,
          {
            artifact_id: result.artifact_id,
            file_url: result.file_url,
            storage_path: result.storage_path,
            width: result.width,
            height: result.height,
          },
        ]);
        setRefineInput("");
        setRefiningId(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setRefineLoading(false);
      }
    },
    [sessionId, refineInput, variants, onVariantsGenerated],
  );

  const handleClose = () => {
    if (status === "generating") return;
    onOpenChange(false);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={handleClose}
    >
      <div
        className="bg-surface border border-hairline rounded-xl p-4 max-w-[820px] w-[92vw] max-h-[85vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <ImageIcon size={14} weight="bold" className="text-cinnabar" />
            <span className="text-[13px] font-medium text-white">
              {hasVariants ? "Thumbnail" : "Generate Thumbnail"}
            </span>
            {hasVariants ? (
              <span className="font-mono text-[10.5px] text-mist">
                ({variants.length} variant{variants.length !== 1 ? "s" : ""})
              </span>
            ) : null}
          </div>
          <button
            onClick={handleClose}
            disabled={status === "generating"}
            className="text-mist hover:text-white text-[11px] transition-colors disabled:opacity-30"
          >
            close
          </button>
        </div>

        {/* Form — when idle (no variants yet) */}
        {!hasVariants && status === "idle" && (
          <>
            <div className="space-y-1.5 mb-3">
              <label className="text-[11px] text-mist font-mono uppercase tracking-[0.15em]">
                Style reference (optional)
              </label>
              <input
                type="url"
                placeholder="Paste a YouTube thumbnail URL to use as reference"
                value={referenceUrl}
                onChange={(e) => setReferenceUrl(e.target.value)}
                className={cn(
                  "w-full h-8 px-2.5 rounded-md",
                  "bg-white/[0.04] border border-hairline",
                  "text-[12px] text-white placeholder:text-white/20",
                  "focus:outline-none focus:border-cinnabar/40 focus:bg-white/[0.06]",
                  "transition-colors",
                )}
              />
            </div>

            <div className="space-y-1 mb-4">
              <p className="text-[11px] text-mist font-mono uppercase tracking-[0.15em]">
                The agent will use
              </p>
              <ul className="text-[11.5px] text-white/70 space-y-0.5 ml-1">
                <li className="flex items-center gap-1.5">
                  <span className="text-cinnabar">&middot;</span> Video title
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="text-cinnabar">&middot;</span> Top 3 talking points
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="text-cinnabar">&middot;</span> Your brand colors
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="text-cinnabar">&middot;</span> Reference style (if provided)
                </li>
              </ul>
            </div>

            <Button
              size="sm"
              variant="primary"
              onClick={handleGenerate}
              className="w-full"
            >
              <Lightning size={11} weight="bold" />
              Generate 3 variants
            </Button>
          </>
        )}

        {/* Generating state */}
        {status === "generating" && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Spinner
                size={13}
                weight="bold"
                className="text-cinnabar animate-spin"
              />
              <span className="text-[12.5px] text-white">
                Generating thumbnail variants&hellip;
              </span>
            </div>
            {streamText ? (
              <pre className="font-mono text-[10.5px] text-mist whitespace-pre-wrap leading-[1.5] max-h-24 overflow-y-auto">
                {streamText}
              </pre>
            ) : null}
          </div>
        )}

        {/* Error */}
        {error ? (
          <div className="flex items-start gap-2 px-2 py-1.5 rounded-md bg-cinnabar/10 border border-cinnabar/20 mt-3">
            <Warning size={12} weight="fill" className="text-cinnabar mt-0.5" />
            <p className="font-mono text-[11px] text-cinnabar leading-[1.5]">
              {error}
            </p>
          </div>
        ) : null}

        {/* New generation form (when variants exist, user can regenerate) */}
        {hasVariants && status !== "generating" && (
          <div className="space-y-3">
            {/* Reference URL + Regenerate button (always show to allow regen) */}
            <div className="flex items-end gap-2">
              <div className="flex-1 space-y-1.5">
                <label className="text-[11px] text-mist font-mono uppercase tracking-[0.15em]">
                  Style reference (optional)
                </label>
                <input
                  type="url"
                  placeholder="YouTube thumbnail reference URL"
                  value={referenceUrl}
                  onChange={(e) => setReferenceUrl(e.target.value)}
                  className={cn(
                    "w-full h-8 px-2.5 rounded-md",
                    "bg-white/[0.04] border border-hairline",
                    "text-[12px] text-white placeholder:text-white/20",
                    "focus:outline-none focus:border-cinnabar/40 focus:bg-white/[0.06]",
                    "transition-colors",
                  )}
                />
              </div>
              <Button
                size="sm"
                variant="primary"
                onClick={handleGenerate}
                className="shrink-0"
              >
                <Lightning size={11} weight="bold" />
                Regenerate
              </Button>
            </div>
          </div>
        )}

        {/* Results — horizontal row of image cards with Select + Refine */}
        {variants.length > 0 && (
          <div className="space-y-3 mt-3">
            <div className="flex items-center gap-2">
              <CheckCircle size={11} weight="fill" className="text-cinnabar" />
              <span className="text-[12px] text-white/85">
                {variants.length} variant{variants.length !== 1 ? "s" : ""}{" "}
                generated
              </span>
            </div>
            <div className="flex gap-3 overflow-x-auto pb-1">
              {variants.map((v) => {
                const isSelected = selectedId === v.artifact_id;
                const isRefining = refiningId === v.artifact_id;
                return (
                  <div
                    key={v.artifact_id}
                    className={cn(
                      "shrink-0 w-[220px] rounded-lg border overflow-hidden",
                      isSelected ? "border-cinnabar" : "border-hairline",
                      "bg-white/[0.02] transition-colors",
                    )}
                  >
                    <a
                      href={v.file_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <img
                        src={v.file_url}
                        alt="Thumbnail variant"
                        className="w-full aspect-video object-cover"
                      />
                    </a>
                    <div className="p-2 space-y-2">
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleSelect(v.artifact_id)}
                          disabled={isSelected}
                          className={cn(
                            "flex-1 h-7 rounded text-[11px] font-medium transition-colors",
                            isSelected
                              ? "bg-cinnabar/15 text-cinnabar border border-cinnabar/30"
                              : "bg-white/[0.04] text-white/80 border border-hairline hover:bg-white/[0.08]",
                          )}
                        >
                          {isSelected ? "Selected" : "Select"}
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setRefiningId(isRefining ? null : v.artifact_id);
                            setRefineInput("");
                          }}
                          className={cn(
                            "h-7 w-7 rounded flex items-center justify-center transition-colors",
                            isRefining
                              ? "bg-cinnabar/15 text-cinnabar border border-cinnabar/30"
                              : "bg-white/[0.04] text-white/60 border border-hairline hover:bg-white/[0.08]",
                          )}
                          title="Refine"
                        >
                          <PencilSimple size={11} weight="bold" />
                        </button>
                      </div>

                      {/* Inline refine input */}
                      {isRefining ? (
                        <div className="space-y-1.5">
                          <input
                            type="text"
                            placeholder="Describe changes…"
                            value={refineInput}
                            onChange={(e) => setRefineInput(e.target.value)}
                            onKeyDown={(e) => {
                              if (
                                e.key === "Enter" &&
                                refineInput.trim()
                              ) {
                                handleRefine(v.artifact_id);
                              }
                            }}
                            className={cn(
                              "w-full h-7 px-2 rounded",
                              "bg-white/[0.04] border border-hairline",
                              "text-[11px] text-white placeholder:text-white/20",
                              "focus:outline-none focus:border-cinnabar/40",
                            )}
                            autoFocus
                          />
                          <button
                            type="button"
                            onClick={() => handleRefine(v.artifact_id)}
                            disabled={!refineInput.trim() || refineLoading}
                            className="w-full h-6 rounded text-[11px] font-medium bg-cinnabar text-white hover:bg-cinnabar/90 disabled:opacity-40 transition-colors"
                          >
                            {refineLoading ? "Refining…" : "Apply"}
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Retry on failure */}
        {status === "failed" && variants.length === 0 ? (
          <Button
            size="sm"
            variant="primary"
            onClick={handleGenerate}
            className="w-full mt-3"
          >
            <Warning size={11} weight="bold" />
            Retry
          </Button>
        ) : null}
      </div>
    </div>
  );
}
