import { useCallback, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Lightbulb, Sparkle } from "@phosphor-icons/react";
import { Shell } from "../components/app/Shell";
import { Badge } from "../components/ui/Badge";
import { ResizableSplit } from "../components/ui/ResizableSplit";
import { useIdeas, type Idea, type IdeaUpdate } from "../lib/useIdeas";
import { patchStudioSession } from "../lib/agents";
import { cn } from "../lib/cn";
import {
  useStudioStream,
  StudioRunStrip,
  ScriptView,
} from "../components/studio/StudioScriptStream";
import { SceneRunPanel } from "../components/scene/SceneRunPanel";
import { ScenePreviewModal } from "../components/scene/ScenePreviewModal";
import { StudioResearchPanel } from "../components/research/StudioResearchPanel";
import { StudioHeader } from "../components/studio/StudioHeader";
import { OutlineEditor } from "../components/studio/OutlineEditor";
import { ChatPanel } from "../components/studio/ChatPanel";
import { SectionNav, type SectionDef } from "../components/studio/SectionNav";
import { CollapsibleSection } from "../components/studio/CollapsibleSection";

export default function StudioPage() {
  const { id } = useParams();
  const { ideas, loading, updateIdea, patchLocal } = useIdeas();
  const idea = useMemo<Idea | null>(
    () => (id ? ideas.find((i) => i.id === id) ?? null : null),
    [ideas, id],
  );

  return (
    <Shell unconstrained>
      {idea ? (
        <StudioBody
          idea={idea}
          loading={loading}
          updateIdea={updateIdea}
          patchLocal={patchLocal}
        />
      ) : (
        <StudioEmpty loading={loading} />
      )}
    </Shell>
  );
}

function StudioBody({
  idea,
  loading,
  updateIdea,
  patchLocal,
}: {
  idea: Idea;
  loading: boolean;
  updateIdea: (id: string, patch: IdeaUpdate) => Promise<Idea>;
  patchLocal: (id: string, patch: IdeaUpdate) => void;
}) {
  const state = useStudioStream(idea.id, idea.target_duration_min ?? undefined);
  const [previewOpen, setPreviewOpen] = useState(false);

  const onTitleChange = useCallback(
    async (next: string) => {
      const previous = idea.title;
      patchLocal(idea.id, { title: next });
      try {
        await updateIdea(idea.id, { title: next });
      } catch {
        patchLocal(idea.id, { title: previous });
      }
    },
    [idea.id, idea.title, patchLocal, updateIdea],
  );

  const onDurationChange = useCallback(
    async (newMin: number) => {
      if (newMin === idea.target_duration_min) return;
      const previous = idea.target_duration_min;
      patchLocal(idea.id, { target_duration_min: newMin });
      state.regenerate();
      try {
        await updateIdea(idea.id, { target_duration_min: newMin });
      } catch {
        patchLocal(idea.id, { target_duration_min: previous });
      }
    },
    [idea.id, idea.target_duration_min, patchLocal, state, updateIdea],
  );

  // Optimistic-then-confirmed brand color update. The session row is
  // patched server-side; the next scene re-run picks up the new color
  // automatically (the WS loader passes brand_color into the designer).
  const onBrandColorChange = useCallback(
    async (hex: string | null) => {
      const sid = state.sessionId;
      if (!sid) return;
      const previous = state.session?.brand_color ?? null;
      state.patchSession({ brand_color: hex });
      try {
        await patchStudioSession(sid, { brand_color: hex });
      } catch {
        state.patchSession({ brand_color: previous });
      }
    },
    [state],
  );

  const isRunning = state.status === "running" || state.status === "loading";

  return (
    <>
      <StudioHeader
        idea={idea}
        loading={loading}
        session={state.session}
        onTitleChange={onTitleChange}
        onDurationChange={onDurationChange}
        durationLocked={isRunning}
        onBrandColorChange={state.sessionId ? onBrandColorChange : undefined}
      />
      <ResizableSplit
        storageKey="ladder.studio.splitPct"
        defaultLeftPct={65}
        minLeftPct={40}
        maxLeftPct={78}
        left={
          <LeftPane
            idea={idea}
            state={state}
            onPreviewScene={() => setPreviewOpen(true)}
          />
        }
        right={<ChatPanel sessionId={state.sessionId} />}
      />
      <ScenePreviewModal
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        scene={state.scene}
        sessionId={state.sessionId}
      />
    </>
  );
}

function LeftPane({
  idea,
  state,
  onPreviewScene,
}: {
  idea: Idea;
  state: ReturnType<typeof useStudioStream>;
  onPreviewScene: () => void;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);

  const sections: SectionDef[] = [
    {
      id: "studio-script",
      label: "Script",
      status: state.script ? "ready" : state.status === "running" ? "live" : "—",
    },
    {
      id: "studio-outline",
      label: "Outline",
      status: state.outline
        ? `${state.outline.items.length} beats`
        : state.status === "running"
          ? "next"
          : "—",
    },
    {
      id: "studio-scene",
      label: "Scene",
      status: state.scene ? "ready" : state.outline ? "build" : "—",
    },
  ];

  return (
    <section className="flex flex-col min-h-0 bg-night h-full">
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 space-y-6"
      >
        <SectionNav sections={sections} scrollRootRef={scrollRef} />

        <div className="pt-2">
          <IdeaSummary idea={idea} />
        </div>

        <StudioResearchPanel idea={idea} />

        <CollapsibleSection
          id="studio-script"
          title="Script"
          hint={scriptHint(state)}
        >
          <StudioRunStrip state={state} />
          <ScriptView script={state.script} state={state} />
        </CollapsibleSection>

        <CollapsibleSection
          id="studio-outline"
          title="Scene outline"
          hint={outlineHint(state)}
        >
          {state.outline ? (
            <OutlineEditor
              outline={state.outline}
              sessionId={state.sessionId}
              onSaved={state.setOutline}
            />
          ) : (
            <p className="font-mono text-[11.5px] text-mist">
              · outline lands once the script settles ·
            </p>
          )}
        </CollapsibleSection>

        {/* Scroll-spy anchor for "Scene". Visible only as a one-line hint —
            the actual action row lives in the sticky footer below. */}
        <section id="studio-scene" className="scroll-mt-14 -mt-2">
          <div className="flex items-center gap-2 text-mist">
            <span className="h-px flex-1 bg-hairline" />
            <span className="font-mono text-[10px] uppercase tracking-[0.22em]">
              scene controls pinned below
            </span>
            <span className="h-px flex-1 bg-hairline" />
          </div>
        </section>
      </div>

      <div
        className={cn(
          "shrink-0 border-t border-hairline",
          "bg-night/90 backdrop-blur supports-[backdrop-filter]:bg-night/75",
          "px-5 py-2.5",
        )}
      >
        <SceneRunPanel
          sessionId={state.sessionId}
          initialScene={state.scene}
          outlineReady={!!state.outline}
          onPreview={onPreviewScene}
        />
      </div>
    </section>
  );
}

function scriptHint(state: ReturnType<typeof useStudioStream>) {
  if (state.status === "ready") {
    return state.hydratedFromDb
      ? "stream_script · hydrated"
      : "stream_script · ready";
  }
  if (state.status === "failed") return "stream_script · failed";
  return "stream_script · streaming";
}

function outlineHint(state: ReturnType<typeof useStudioStream>) {
  if (state.outline) return "outline · ready · editable";
  if (state.status === "failed") return "outline · failed";
  return "outline · pending";
}

function IdeaSummary({ idea }: { idea: Idea }) {
  return (
    <div>
      <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-2">
        idea
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {typeof idea.opportunity_score === "number" ? (
          <Badge tone="cinnabar">score {idea.opportunity_score}</Badge>
        ) : null}
        {typeof idea.outlier_score === "number" ? (
          <Badge tone="muted">{idea.outlier_score.toFixed(1)}× outlier</Badge>
        ) : null}
        {idea.idea_type ? <Badge tone="muted">{idea.idea_type}</Badge> : null}
        {idea.source_type ? <Badge tone="muted">{idea.source_type}</Badge> : null}
      </div>
      {idea.rationale ? (
        <p className="mt-3 text-[13px] text-white/75 leading-[1.6]">
          {idea.rationale}
        </p>
      ) : null}
    </div>
  );
}

function StudioEmpty({ loading }: { loading: boolean }) {
  return (
    <>
      <StudioHeader idea={null} loading={loading} session={null} />
      <div className="flex-1 grid place-items-center px-6 py-10">
        <div className="rounded-xl border border-hairline bg-surface p-6 max-w-[420px] text-center">
          {loading ? (
            <>
              <Sparkle size={16} className="text-mist mx-auto mb-2" />
              <p className="font-mono text-[11.5px] text-mist">loading idea…</p>
            </>
          ) : (
            <>
              <Lightbulb size={16} className="text-mist mx-auto mb-2" />
              <p className="text-[13.5px] text-white mb-1">No idea loaded.</p>
              <p className="text-[12px] text-mist font-mono leading-[1.6]">
                Go back to /videos and pick one, or run a research sweep from
                /make.
              </p>
            </>
          )}
        </div>
      </div>
    </>
  );
}

