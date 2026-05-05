import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { Lightbulb, Sparkle } from "@phosphor-icons/react";
import { Shell } from "../components/app/Shell";
import { Badge } from "../components/ui/Badge";
import { ResizableSplit } from "../components/ui/ResizableSplit";
import { useIdeas, type Idea, type IdeaUpdate } from "../lib/useIdeas";
import {
  patchStudioSession,
  applyScenePatch,
  applyScriptPatch,
  insertScriptSection,
  removeScriptSection,
  applyOutlinePatch,
  insertOutlineItem,
  removeOutlineItem,
  saveSceneSkeleton,
  saveScript,
  saveOutline,
  type ThumbnailVariant,
} from "../lib/agents";
import { cn } from "../lib/cn";
import {
  useStudioStream,
  StudioRunStrip,
  ScriptView,
} from "../components/studio/StudioScriptStream";
import { SceneRunPanel } from "../components/scene/SceneRunPanel";
import { ScenePreviewModal } from "../components/scene/ScenePreviewModal";
import { ThumbnailPreviewModal } from "../components/scene/ThumbnailPreviewModal";
import { StudioResearchPanel } from "../components/research/StudioResearchPanel";
import { StudioHeader } from "../components/studio/StudioHeader";
import {
  readStoredBrand,
  writeStoredBrand,
} from "../components/research/MakeBrandPicker";
import { OutlineEditor } from "../components/studio/OutlineEditor";
import { ChatPanel } from "../components/studio/ChatPanel";
import { CollapsibleSection } from "../components/studio/CollapsibleSection";

const EXCALIDRAW_LIVE_URL =
  (import.meta.env.VITE_EXCALIDRAW_CANVAS_URL as string | undefined)?.trim() || "";

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
  const [liveCanvasDuringRun, setLiveCanvasDuringRun] = useState(false);
  const [thumbnailVariants, setThumbnailVariants] = useState<ThumbnailVariant[]>([]);
  const [thumbnailGenerating, setThumbnailGenerating] = useState(false);
  const [thumbnailModalOpen, setThumbnailModalOpen] = useState(false);

  // Reset + hydrate thumbnail variants when idea changes or first load.
  // Only set the ref AFTER thumbnails are actually hydrated — otherwise the
  // ref gets set prematurely while state.thumbnails is still [] (hydration
  // hasn't resolved yet), and the next render skips hydration entirely.
  const thumbnailsHydratedRef = useRef<string | null>(null);
  useEffect(() => {
    // New idea — full reset
    if (thumbnailsHydratedRef.current !== idea.id) {
      setThumbnailVariants([]);
      setThumbnailModalOpen(false);
      thumbnailsHydratedRef.current = null;
    }
    // Not hydrated from DB yet — wait
    if (!state.hydratedFromDb) return;
    // Already hydrated this idea
    if (thumbnailsHydratedRef.current === idea.id) return;
    // DB has thumbnails → hydrate
    if (state.thumbnails.length > 0) {
      setThumbnailVariants(state.thumbnails);
    }
    // Mark as done regardless (empty or populated)
    thumbnailsHydratedRef.current = idea.id;
  }, [idea.id, state.hydratedFromDb, state.thumbnails]);

  const handleDiagramRunActive = useCallback((active: boolean) => {
    setLiveCanvasDuringRun(active);
    if (active) setPreviewOpen(true);
  }, []);

  // Chat patching plumbing — refs avoid stale closures in useCallback deps
  const stateRef = useRef(state);
  stateRef.current = state;
  const dirtySceneRef = useRef(false);
  const dirtyScriptRef = useRef(false);
  const dirtyOutlineRef = useRef(false);

  const onPatchScene = useCallback((patch: any) => {
    const s = stateRef.current;
    if (!s.scene || !s.sessionId) return;
    dirtySceneRef.current = true;
    s.setScene(applyScenePatch(s.scene, patch));
  }, []);

  const onPatchScript = useCallback((patch: any) => {
    const s = stateRef.current;
    if (!s.script || !s.sessionId) return;
    dirtyScriptRef.current = true;
    s.setScript(applyScriptPatch(s.script, patch));
  }, []);

  const onPatchOutline = useCallback((patch: any) => {
    const s = stateRef.current;
    if (!s.outline || !s.sessionId) return;
    dirtyOutlineRef.current = true;
    s.setOutline(applyOutlinePatch(s.outline, patch));
  }, []);

  const onInsertScriptSection = useCallback((args: any) => {
    const s = stateRef.current;
    if (!s.script || !s.sessionId) return;
    dirtyScriptRef.current = true;
    s.setScript(insertScriptSection(s.script, args.section_index, args.new_section));
  }, []);

  const onRemoveScriptSection = useCallback((args: any) => {
    const s = stateRef.current;
    if (!s.script || !s.sessionId) return;
    dirtyScriptRef.current = true;
    s.setScript(removeScriptSection(s.script, args.section_index));
  }, []);

  const onInsertOutlineItem = useCallback((args: any) => {
    const s = stateRef.current;
    if (!s.outline || !s.sessionId) return;
    dirtyOutlineRef.current = true;
    s.setOutline(insertOutlineItem(s.outline, args.item_index, args.new_item));
  }, []);

  const onRemoveOutlineItem = useCallback((args: any) => {
    const s = stateRef.current;
    if (!s.outline || !s.sessionId) return;
    dirtyOutlineRef.current = true;
    s.setOutline(removeOutlineItem(s.outline, args.item_index));
  }, []);

  const onCommit = useCallback(async () => {
    const s = stateRef.current;
    if (!s.sessionId) return;
    try {
      if (dirtySceneRef.current && s.scene) {
        dirtySceneRef.current = false;
        await saveSceneSkeleton(s.sessionId, s.scene);
      }
      if (dirtyScriptRef.current && s.script) {
        dirtyScriptRef.current = false;
        await saveScript(s.sessionId, s.script);
      }
      if (dirtyOutlineRef.current && s.outline) {
        dirtyOutlineRef.current = false;
        await saveOutline(s.sessionId, s.outline);
      }
    } catch (err) {
      console.error("Failed to commit chat patches:", err);
    }
  }, []);

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

  // Optimistic PATCH for brand_id + accent color (derived from brands.primary_color).
  // PATCH only `brand_id` on the API — avoids failing if `studio_sessions.brand_color`
  // hasn't been migrated yet; scene crew resolves accent from brands.primary_color anyway.
  const onBrandSessionPatch = useCallback(
    async (patch: {
      brand_id: string | null;
      brand_color: string | null;
    }) => {
      const sid = state.sessionId;
      if (!sid) return;
      const previousBrandId = state.session?.brand_id ?? null;
      const previousColor = state.session?.brand_color ?? null;
      state.patchSession(patch);
      // Mirror the explicit choice to the /make picker default so the next
      // research run starts with the same brand pre-selected.
      writeStoredBrand({
        brand_id: patch.brand_id,
        brand_color: patch.brand_color,
      });
      try {
        await patchStudioSession(sid, { brand_id: patch.brand_id });
      } catch {
        state.patchSession({
          brand_id: previousBrandId,
          brand_color: previousColor,
        });
      }
    },
    [state],
  );

  // When a fresh session lands without a brand, apply the founder's /make
  // default exactly once. Subsequent in-session edits override it.
  const autoBrandAppliedRef = useRef(false);
  useEffect(() => {
    if (autoBrandAppliedRef.current) return;
    if (!state.sessionId) return;
    const sess = state.session;
    if (!sess) return;
    if (sess.brand_id) {
      autoBrandAppliedRef.current = true;
      return;
    }
    const stored = readStoredBrand();
    if (!stored?.brand_id) return;
    autoBrandAppliedRef.current = true;
    void onBrandSessionPatch({
      brand_id: stored.brand_id,
      brand_color: stored.brand_color,
    });
  }, [state.sessionId, state.session, onBrandSessionPatch]);

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
        onBrandSessionPatch={state.sessionId ? onBrandSessionPatch : undefined}
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
            onDiagramRunActive={handleDiagramRunActive}
            thumbnailVariants={thumbnailVariants}
            thumbnailGenerating={thumbnailGenerating}
            onThumbnailOpen={() => setThumbnailModalOpen(true)}
          />
        }
        right={<ChatPanel sessionId={state.sessionId} hasScene={!!state.scene} onRegenerateScene={() => {}} onPatchScene={onPatchScene} onPatchScript={onPatchScript} onInsertScriptSection={onInsertScriptSection} onRemoveScriptSection={onRemoveScriptSection} onPatchOutline={onPatchOutline} onInsertOutlineItem={onInsertOutlineItem} onRemoveOutlineItem={onRemoveOutlineItem} onCommit={onCommit} />}
      />
      <ScenePreviewModal
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        scene={state.scene}
        sessionId={state.sessionId}
        liveCanvasDuringRun={liveCanvasDuringRun}
        liveCanvasUrl={EXCALIDRAW_LIVE_URL || undefined}
        onSceneChange={state.setScene}
      />
      {state.sessionId ? (
        <ThumbnailPreviewModal
          open={thumbnailModalOpen}
          onOpenChange={setThumbnailModalOpen}
          sessionId={state.sessionId}
          variants={thumbnailVariants}
          onVariantsGenerated={setThumbnailVariants}
          onGeneratingChange={setThumbnailGenerating}
          onSelected={(artifactId) => {
            state.patchSession({ thumbnail_selected_id: artifactId });
          }}
        />
      ) : null}
    </>
  );
}

function LeftPane({
  idea,
  state,
  onPreviewScene,
  onDiagramRunActive,
  thumbnailVariants,
  thumbnailGenerating,
  onThumbnailOpen,
}: {
  idea: Idea;
  state: ReturnType<typeof useStudioStream>;
  onPreviewScene: () => void;
  onDiagramRunActive?: (active: boolean) => void;
  thumbnailVariants: ThumbnailVariant[];
  thumbnailGenerating: boolean;
  onThumbnailOpen: () => void;
}) {
  return (
    <section className="flex flex-col min-h-0 bg-night h-full">
      <div className="flex-1 min-h-0 overflow-y-auto px-6 pb-6 space-y-6">
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
          title="Outline"
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
          scriptReady={!!state.script}
          onPreview={onPreviewScene}
          sceneAccentHex={state.session?.brand_color ?? null}
          onSceneReady={state.setScene}
          onDiagramRunActive={onDiagramRunActive}
          thumbnailVariants={thumbnailVariants}
          thumbnailGenerating={thumbnailGenerating}
          onThumbnailOpen={onThumbnailOpen}
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

