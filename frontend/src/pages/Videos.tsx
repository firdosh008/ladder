import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, X, Warning } from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Button } from "../components/ui/Button";
import { useIdeas, type Idea } from "../lib/useIdeas";
import {
  KanbanBoard,
  KANBAN_COLUMNS,
  POSITION_STEP,
  type KanbanCard,
  type KanbanStatus,
  type KanbanMoveEvent,
} from "../components/kanban";
import { CardDetailSheet } from "../components/kanban/CardDetailSheet";
import { Toolbar } from "../components/kanban/Toolbar";

const VALID_STATUSES: KanbanStatus[] = ["new", "scripting", "scene", "ready", "published"];

function isKanbanStatus(s: string): s is KanbanStatus {
  return (VALID_STATUSES as string[]).includes(s);
}

const EMPTY_COPY: Partial<Record<KanbanStatus, string>> = {
  new: "No ideas yet. Tap + to capture one.",
  scripting: "Drag an idea here to start scripting.",
  scene: "Scripts move here once the outline lands.",
  ready: "Scenes move here once approved.",
  published: "Published videos sync here.",
};

function ErrorBanner({
  message,
  onDismiss,
}: {
  message: string;
  onDismiss: () => void;
}) {
  const missingPosition =
    message.includes("ideas.position") ||
    message.includes("'position' column");
  const friendly = missingPosition
    ? "The 'position' migration hasn't been applied to Supabase yet. Run the SQL in supabase/migrations/20260424000001_idea_position.sql (paste into the Supabase SQL editor), then hard-refresh."
    : message;

  return (
    <div className="mb-3 flex items-start gap-2.5 rounded-lg border border-cinnabar/30 bg-cinnabar/[0.05] px-3.5 py-2.5 text-[12.5px] text-cinnabar">
      <Warning size={13} weight="bold" className="mt-0.5 shrink-0" />
      <span className="flex-1 leading-[1.5]">{friendly}</span>
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

function formatAge(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const secs = Math.max(0, Math.floor((now - then) / 1000));
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d`;
  return `${Math.floor(days / 7)}w`;
}

export default function VideosPage() {
  const navigate = useNavigate();
  const {
    ideas,
    loading,
    error,
    createIdea,
    updateIdea,
    deleteIdea,
    patchLocal,
    refresh,
  } = useIdeas();

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<KanbanStatus | "all">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
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

  const visibleColumns = useMemo(
    () =>
      statusFilter === "all"
        ? KANBAN_COLUMNS
        : KANBAN_COLUMNS.filter((c) => c.id === statusFilter),
    [statusFilter],
  );

  const cards = useMemo<KanbanCard[]>(() => {
    const q = search.trim().toLowerCase();
    return ideas
      .filter((idea) => isKanbanStatus(idea.status))
      .filter((idea) => {
        if (!q) return true;
        return (
          idea.title.toLowerCase().includes(q) ||
          (idea.body ?? "").toLowerCase().includes(q)
        );
      })
      .map<KanbanCard>((idea) => ({
        id: idea.id,
        columnId: idea.status as KanbanStatus,
        position: idea.position ?? 1e12,
        title: idea.title,
        score: idea.opportunity_score,
        subtitle: idea.source_type,
        meta: formatAge(idea.created_at),
      }));
  }, [ideas, search]);

  const totalCount = ideas.length;

  async function onAdd(columnId: KanbanStatus, title: string) {
    setBannerError(null);
    const sameColumn = ideas.filter((i) => i.status === columnId);
    const maxPos = sameColumn.reduce(
      (m, i) => (i.position != null && i.position > m ? i.position : m),
      0,
    );
    try {
      await createIdea({
        title,
        status: columnId,
        position: maxPos + POSITION_STEP,
      });
    } catch (e) {
      setBannerError(e instanceof Error ? e.message : "Failed to add idea");
      throw e; // let AddCardInline display the error inline too
    }
  }

  async function onMove(e: KanbanMoveEvent) {
    setBannerError(null);
    // Optimistic update so UI feels instant.
    patchLocal(e.cardId, {
      status: e.toColumnId,
      position: e.newPosition,
    });
    try {
      await updateIdea(e.cardId, {
        status: e.toColumnId,
        position: e.newPosition,
      });
    } catch (err) {
      setBannerError(err instanceof Error ? err.message : "Failed to move card");
      await refresh();
    }
  }

  function onCardClick(cardId: string) {
    setSelectedId(cardId);
    setSheetOpen(true);
  }

  const selectedIdea: Idea | null = useMemo(
    () => (selectedId ? ideas.find((i) => i.id === selectedId) ?? null : null),
    [ideas, selectedId],
  );

  async function onSheetSave(id: string, patch: Partial<Idea>) {
    await updateIdea(id, patch);
  }

  async function onSheetDelete(id: string) {
    await deleteIdea(id);
    setSelectedId(null);
  }

  return (
    <Shell>
      <PageContainer>
        <PageHeader
          eyebrow="§ /videos · pipeline"
          title="My videos"
          description="Everything in flight — from idea to published. Drag cards across columns to advance them."
          right={
            <Button onClick={() => navigate("/make")}>
              <Plus size={13} weight="bold" />
              New video
            </Button>
          }
        />

        <Toolbar
          ref={searchRef}
          search={search}
          onSearchChange={setSearch}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          columns={KANBAN_COLUMNS}
          totalCount={totalCount}
        />

        {error || bannerError ? (
          <ErrorBanner
            message={error || bannerError || ""}
            onDismiss={() => setBannerError(null)}
          />
        ) : null}

        {loading ? (
          <p className="py-10 text-center text-[12px] text-mist font-mono">
            loading…
          </p>
        ) : (
          <KanbanBoard
            columns={visibleColumns}
            cards={cards}
            onMove={onMove}
            onAdd={onAdd}
            onCardClick={onCardClick}
            emptyCopyByColumn={EMPTY_COPY}
          />
        )}
      </PageContainer>

      <CardDetailSheet
        idea={selectedIdea}
        open={sheetOpen && !!selectedIdea}
        onClose={() => setSheetOpen(false)}
        onSave={onSheetSave}
        onDelete={onSheetDelete}
      />
    </Shell>
  );
}
