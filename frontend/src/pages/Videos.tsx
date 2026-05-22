import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, MagnifyingGlass, Warning, X } from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Button } from "../components/ui/Button";
import { api, ApiError } from "../lib/api";
import { useVideosKanban } from "../lib/useVideosKanban";
import { useWeeklySuggestion } from "../lib/useWeeklySuggestion";
import {
  WeeklySuggestionBlock,
  ChannelSummaryStrip,
  MyKanbanBoard,
  PerformanceDetailPanel,
  ContextMenu,
} from "../components/videos";
import type { KanbanData, PublishedEntry, WeeklySuggestion } from "../types/videos";
import type { ContextMenuItem } from "../components/videos";

function filterBySearch(data: KanbanData, query: string): KanbanData {
  if (!query.trim()) return data;
  const q = query.toLowerCase();
  return {
    ...data,
    ideas: data.ideas.filter(
      (i) =>
        i.title.toLowerCase().includes(q) ||
        (i.rationale ?? "").toLowerCase().includes(q),
    ),
    in_progress: data.in_progress.filter((s) =>
      s.title.toLowerCase().includes(q),
    ),
    ready: data.ready.filter((r) =>
      r.title.toLowerCase().includes(q),
    ),
    published: data.published.filter((p) =>
      p.title.toLowerCase().includes(q),
    ),
  };
}

function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  return (
    <div className="mb-3 flex items-start gap-2.5 rounded-lg border border-cinnabar/30 bg-cinnabar/[0.05] px-3.5 py-2.5 text-[12.5px] text-cinnabar">
      <Warning size={13} weight="bold" className="mt-0.5 shrink-0" />
      <span className="flex-1 leading-[1.5]">{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 text-cinnabar/70 hover:text-cinnabar transition-colors"
      >
        <X size={12} weight="bold" />
      </button>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="flex gap-4 overflow-x-auto pb-4 -mx-2 px-2">
      {["Ideas", "In Progress", "Ready to Record", "Published"].map((title) => (
        <div key={title} className="min-w-[300px] w-[300px] shrink-0">
          <div className="flex items-center px-1 pb-2.5">
            <div className="inline-flex items-center gap-2 rounded-md px-2 py-1 bg-white/[0.04] border border-hairline">
              <span className="h-1.5 w-1.5 rounded-full bg-hairline" />
              <span className="text-[12.5px] font-semibold text-white/90">
                {title}
              </span>
            </div>
          </div>
          <div className="rounded-xl border border-transparent bg-white/[0.015] p-2 space-y-2 animate-pulse">
            {[1, 2].map((i) => (
              <div
                key={i}
                className="h-[100px] rounded-lg bg-white/[0.03]"
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function VideosPage() {
  const navigate = useNavigate();
  const {
    data: kanbanData,
    loading: kanbanLoading,
    error: kanbanError,
    refresh: refreshKanban,
  } = useVideosKanban();
  const {
    suggestion,
    loading: suggestionLoading,
    save: saveSuggestion,
    dismiss: dismissSuggestion,
    refresh: refreshSuggestion,
  } = useWeeklySuggestion();

  const [search, setSearch] = useState("");
  const [selectedVideo, setSelectedVideo] = useState<PublishedEntry | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [contextMenu, setContextMenu] = useState<{
    items: ContextMenuItem[];
    x: number;
    y: number;
  } | null>(null);
  const [bannerError, setBannerError] = useState<string | null>(null);

  const searchRef = useRef<HTMLInputElement>(null);

  // Keyboard: `/` focuses search.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "/") return;
      const active = document.activeElement;
      const isTextInput =
        active instanceof HTMLInputElement ||
        active instanceof HTMLTextAreaElement ||
        (active instanceof HTMLElement && active.isContentEditable);
      if (isTextInput) return;
      e.preventDefault();
      searchRef.current?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const filteredData = useMemo(
    () => (kanbanData ? filterBySearch(kanbanData, search) : null),
    [kanbanData, search],
  );

  const handleContextMenu = useCallback(
    (items: ContextMenuItem[], x: number, y: number) => {
      setContextMenu({ items, x, y });
    },
    [],
  );

  // ── Mutations ──────────────────────────────────────────────────

  async function handleAddIdea(title: string) {
    setBannerError(null);
    try {
      await api.post("/ideas", {
        title,
        status: "new",
        source_type: "manual",
      });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Failed to add idea";
      setBannerError(msg);
      throw e;
    } finally {
      await refreshKanban();
    }
  }

  async function handleMoveIdea(cardId: string, newPosition: number) {
    setBannerError(null);
    try {
      await api.patch(`/ideas/${cardId}`, { position: newPosition });
    } catch (e) {
      setBannerError(e instanceof ApiError ? e.message : "Failed to move idea");
    } finally {
      await refreshKanban();
    }
  }

  async function handleArchiveIdea(id: string) {
    setBannerError(null);
    try {
      await api.patch(`/ideas/${id}`, { archived: true } as any);
    } catch (e) {
      setBannerError(e instanceof ApiError ? e.message : "Failed to archive idea");
    }
    await refreshKanban();
  }

  async function handleArchiveSession(sessionId: string) {
    setBannerError(null);
    try {
      await api.patch(`/studio-sessions/${sessionId}`, { archived: true } as any);
    } catch (e) {
      setBannerError(
        e instanceof ApiError ? e.message : "Failed to archive session",
      );
    }
    await refreshKanban();
  }

  function handleOpenPublishedDetail(entry: PublishedEntry) {
    setSelectedVideo(entry);
    setPanelOpen(true);
  }

  async function handleSaveSuggestion(ideas: WeeklySuggestion["ideas"]) {
    return saveSuggestion(ideas);
  }

  // ── Render ──────────────────────────────────────────────────────

  const totalCount =
    (kanbanData?.ideas.length ?? 0) +
    (kanbanData?.in_progress.length ?? 0) +
    (kanbanData?.ready.length ?? 0) +
    (kanbanData?.published.length ?? 0);

  return (
    <Shell>
      <PageContainer>
        <PageHeader
          eyebrow="§ /videos · pipeline"
          title="My videos"
          description="Everything in flight — from idea to published."
          right={
            <Button onClick={() => navigate("/make")}>
              <Plus size={13} weight="bold" />
              New video
            </Button>
          }
        />

        {/* Weekly suggestion block */}
        <WeeklySuggestionBlock
          suggestion={suggestion}
          loading={suggestionLoading}
          onSave={handleSaveSuggestion}
          onDismiss={dismissSuggestion}
          onRefresh={refreshSuggestion}
        />

        {/* Channel summary strip */}
        <ChannelSummaryStrip summary={kanbanData?.channel_summary ?? null} />

        {/* Search bar */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[10.5px] text-mist uppercase tracking-[0.15em]">
              All {totalCount}
            </span>
          </div>
          <label className="relative flex items-center">
            <MagnifyingGlass
              size={13}
              weight="bold"
              className="absolute left-2.5 text-mist pointer-events-none"
            />
            <input
              ref={searchRef}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search all columns…  (press /)"
              className="h-8 w-[260px] pl-7 pr-3 rounded-md bg-surface-input text-[12.5px] text-white placeholder:text-mist border border-transparent focus:border-cinnabar focus:outline-none transition-colors duration-150"
            />
          </label>
        </div>

        {/* Error */}
        {kanbanError || bannerError ? (
          <ErrorBanner
            message={kanbanError || bannerError || ""}
            onDismiss={() => setBannerError(null)}
          />
        ) : null}

        {/* Kanban or loading */}
        {kanbanLoading || !filteredData ? (
          <LoadingSkeleton />
        ) : (
          <MyKanbanBoard
            kanbanData={filteredData}
            onAddIdea={handleAddIdea}
            onMoveIdea={handleMoveIdea}
            onArchiveIdea={handleArchiveIdea}
            onArchiveSession={handleArchiveSession}
            onOpenPublishedDetail={handleOpenPublishedDetail}
            onContextMenu={handleContextMenu}
          />
        )}
      </PageContainer>

      {/* Performance detail panel */}
      <PerformanceDetailPanel
        video={selectedVideo}
        open={panelOpen}
        onClose={() => {
          setPanelOpen(false);
          setSelectedVideo(null);
        }}
      />

      {/* Context menu */}
      {contextMenu ? (
        <ContextMenu
          items={contextMenu.items}
          position={{ x: contextMenu.x, y: contextMenu.y }}
          onClose={() => setContextMenu(null)}
        />
      ) : null}
    </Shell>
  );
}
