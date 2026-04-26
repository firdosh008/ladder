import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Image as ImageIcon,
  Sparkle,
  Lightbulb,
} from "@phosphor-icons/react";
import { Shell } from "../components/app/Shell";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { useIdeas, type Idea } from "../lib/useIdeas";
import {
  useStudioStream,
  StudioRunStrip,
  ScriptView,
  OutlineView,
} from "../components/studio/StudioScriptStream";
import { SceneRunPanel } from "../components/scene/SceneRunPanel";
import { StudioResearchPanel } from "../components/research/StudioResearchPanel";

export default function StudioPage() {
  const { id } = useParams();
  const { ideas, loading } = useIdeas();
  const idea = useMemo<Idea | null>(
    () => (id ? ideas.find((i) => i.id === id) ?? null : null),
    [ideas, id],
  );

  return (
    <Shell unconstrained>
      <StudioHeader idea={idea} loading={loading} />
      <div className="flex-1 grid grid-cols-[1fr_1fr_380px] min-h-0 divide-x divide-hairline">
        {idea ? (
          <StudioBody ideaId={idea.id} idea={idea} />
        ) : (
          <>
            <ScriptShell loading={loading} idea={null} />
            <ScenePlaceholder />
            <ChatPlaceholder />
          </>
        )}
      </div>
    </Shell>
  );
}

function StudioBody({ ideaId, idea }: { ideaId: string; idea: Idea }) {
  const state = useStudioStream(ideaId);
  return (
    <>
      <ScriptPanelLive idea={idea} state={state} />
      <ScenePanelLive state={state} />
      <ChatPlaceholder />
    </>
  );
}

function StudioHeader({ idea, loading }: { idea: Idea | null; loading: boolean }) {
  const title = idea?.title ?? (loading ? "Loading…" : "Studio");
  return (
    <header className="flex items-center gap-3 px-5 h-12 border-b border-hairline bg-night shrink-0">
      <Link
        to="/videos"
        className="inline-flex items-center gap-1.5 h-7 px-2 rounded-md text-[12.5px] text-mist hover:text-white hover:bg-white/[0.04] transition-colors"
      >
        <ArrowLeft size={12} weight="bold" />
        Pipeline
      </Link>

      <span className="h-4 w-px bg-hairline" />

      <div className="flex items-center gap-1.5 min-w-0">
        <span className="font-display italic text-[15px] text-white truncate max-w-[520px]">
          {title}
        </span>
        {idea?.source_type ? (
          <Badge tone="muted" className="ml-1">
            {idea.source_type}
          </Badge>
        ) : null}
      </div>

      <div className="flex-1" />

      <Button size="sm" variant="ghost" disabled title="Scene crew ships next">
        <ImageIcon size={12} weight="regular" />
        Thumbnail
      </Button>
    </header>
  );
}

function ScriptPanelLive({
  idea,
  state,
}: {
  idea: Idea;
  state: ReturnType<typeof useStudioStream>;
}) {
  return (
    <section className="flex flex-col min-h-0 bg-night">
      <PanelHeader
        title="Script"
        hint={
          state.status === "ready"
            ? state.hydratedFromDb
              ? "stream_script · hydrated"
              : "stream_script · ready"
            : state.status === "failed"
              ? "stream_script · failed"
              : "stream_script · streaming"
        }
      />
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
        <IdeaHeader idea={idea} />
        <StudioResearchPanel ideaId={idea.id} />
        <StudioRunStrip state={state} />
        <ScriptView script={state.script} state={state} />
      </div>
    </section>
  );
}

function ScenePanelLive({ state }: { state: ReturnType<typeof useStudioStream> }) {
  const outlineReady = !!state.outline;
  return (
    <section className="flex flex-col min-h-0 bg-night">
      <PanelHeader
        title="Scene"
        hint={
          state.scene
            ? "scene · ready"
            : outlineReady
              ? "scene · build available"
              : state.status === "failed"
                ? "outline · failed"
                : "outline · pending"
        }
      />
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
        <OutlineView outline={state.outline} state={state} />
        <SceneRunPanel
          sessionId={state.sessionId}
          initialScene={state.scene}
          outlineReady={outlineReady}
        />
      </div>
    </section>
  );
}

function IdeaHeader({ idea }: { idea: Idea }) {
  return (
    <div>
      <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-2">
        idea
      </div>
      <h2 className="font-display text-[24px] text-white leading-[1.15] tracking-tight">
        {idea.title}
      </h2>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {typeof idea.opportunity_score === "number" ? (
          <Badge tone="cinnabar">score {idea.opportunity_score}</Badge>
        ) : null}
        {typeof idea.outlier_score === "number" ? (
          <Badge tone="muted">{idea.outlier_score.toFixed(1)}× outlier</Badge>
        ) : null}
        {idea.idea_type ? <Badge tone="muted">{idea.idea_type}</Badge> : null}
      </div>
      {idea.rationale ? (
        <p className="mt-3 text-[13px] text-white/75 leading-[1.6]">
          {idea.rationale}
        </p>
      ) : null}
    </div>
  );
}

function ScriptShell({ idea, loading }: { idea: Idea | null; loading: boolean }) {
  return (
    <section className="flex flex-col min-h-0 bg-night">
      <PanelHeader title="Script" hint="stream_script · waiting" />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        {loading ? (
          <p className="font-mono text-[11.5px] text-mist">loading idea…</p>
        ) : !idea ? (
          <EmptyBlock
            icon={Lightbulb}
            title="No idea loaded."
            body="Go back to /videos and pick one, or run a research sweep from /make."
          />
        ) : null}
      </div>
    </section>
  );
}

function ScenePlaceholder() {
  return (
    <section className="flex flex-col min-h-0 bg-night">
      <PanelHeader title="Scene" hint="outline · waiting" />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <p className="font-mono text-[11.5px] text-mist">
          · pick an idea to see the outline ·
        </p>
      </div>
    </section>
  );
}

function ChatPlaceholder() {
  return (
    <aside className="flex flex-col min-h-0 bg-night">
      <PanelHeader title="Sharpen" hint="sharpen_this · not yet wired" />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <EmptyBlock
          icon={Sparkle}
          title="AI chat ships next."
          body="Text refinement, screenshot-to-edit on Excalidraw, and skill.md injection — all scoped to this idea."
        />
      </div>
    </aside>
  );
}

function PanelHeader({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex items-center gap-3 h-10 px-5 border-b border-hairline bg-night shrink-0">
      <span className="font-sans font-semibold text-[13px] text-white">
        {title}
      </span>
      {hint ? (
        <span className="font-mono text-[10.5px] text-mist uppercase tracking-[0.18em]">
          {hint}
        </span>
      ) : null}
    </div>
  );
}

function EmptyBlock({
  icon: Icon,
  title,
  body,
}: {
  icon: React.ElementType;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-6">
      <Icon size={16} className="text-mist mb-2" />
      <p className="text-[13.5px] text-white mb-1">{title}</p>
      <p className="text-[12px] text-mist font-mono leading-[1.6]">{body}</p>
    </div>
  );
}
