import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Image as ImageIcon,
  Sparkle,
  Lightbulb,
  Clock,
  CaretDown,
  Check,
} from "@phosphor-icons/react";
import { Shell } from "../components/app/Shell";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { useIdeas, type Idea, type IdeaUpdate } from "../lib/useIdeas";
import {
  useStudioStream,
  StudioRunStrip,
  ScriptView,
  OutlineView,
} from "../components/studio/StudioScriptStream";
import { SceneRunPanel } from "../components/scene/SceneRunPanel";
import { StudioResearchPanel } from "../components/research/StudioResearchPanel";
import { cn } from "../lib/cn";

// Mirror of /make's preset durations so the founder sees a stable set
// across both surfaces. Out-of-range custom values are still accepted
// by the backend (3-60), but only these are exposed in the picker.
const DURATION_OPTIONS: { value: number; label: string; hint: string }[] = [
  { value: 5, label: "5 min", hint: "hot take" },
  { value: 10, label: "10 min", hint: "framework" },
  { value: 15, label: "15 min", hint: "essay" },
  { value: 20, label: "20 min", hint: "founder essay" },
  { value: 30, label: "30 min", hint: "deep dive" },
  { value: 45, label: "45 min", hint: "masterclass" },
];

export default function StudioPage() {
  const { id } = useParams();
  const { ideas, loading, updateIdea, patchLocal } = useIdeas();
  const idea = useMemo<Idea | null>(
    () => (id ? ideas.find((i) => i.id === id) ?? null : null),
    [ideas, id],
  );

  return (
    <Shell unconstrained>
      <StudioHeader idea={idea} loading={loading} />
      <div className="flex-1 grid grid-cols-[1fr_1fr_380px] min-h-0 divide-x divide-hairline">
        {idea ? (
          <StudioBody
            ideaId={idea.id}
            idea={idea}
            updateIdea={updateIdea}
            patchLocal={patchLocal}
          />
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

function StudioBody({
  ideaId,
  idea,
  updateIdea,
  patchLocal,
}: {
  ideaId: string;
  idea: Idea;
  updateIdea: (id: string, patch: IdeaUpdate) => Promise<Idea>;
  patchLocal: (id: string, patch: IdeaUpdate) => void;
}) {
  // Honour the founder-chosen runtime stored on the idea row. The backend
  // also has its own fallback chain (URL → idea row → 20-min default), so
  // this is mostly belt-and-braces — but it keeps the WS URL self-describing
  // when an admin reads access logs.
  const state = useStudioStream(ideaId, idea.target_duration_min ?? undefined);

  // Picking a new runtime: optimistically update the local cache so the
  // badge + the WS query string flip immediately, persist it via PATCH,
  // and force-fresh the studio stream so the next script/outline are
  // generated against the new target. We snapshot the previous value so
  // we can roll back if the PATCH fails (rare, but keeps the UI honest).
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

  const isRunning = state.status === "running" || state.status === "loading";

  return (
    <>
      <ScriptPanelLive
        idea={idea}
        state={state}
        onDurationChange={onDurationChange}
        durationLocked={isRunning}
      />
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
  onDurationChange,
  durationLocked,
}: {
  idea: Idea;
  state: ReturnType<typeof useStudioStream>;
  onDurationChange: (minutes: number) => void;
  durationLocked: boolean;
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
        <IdeaHeader
          idea={idea}
          onDurationChange={onDurationChange}
          durationLocked={durationLocked}
        />
        <StudioResearchPanel idea={idea} />
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

function IdeaHeader({
  idea,
  onDurationChange,
  durationLocked,
}: {
  idea: Idea;
  onDurationChange: (minutes: number) => void;
  durationLocked: boolean;
}) {
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
        <DurationControl
          current={idea.target_duration_min}
          onChange={onDurationChange}
          locked={durationLocked}
        />
      </div>
      {idea.rationale ? (
        <p className="mt-3 text-[13px] text-white/75 leading-[1.6]">
          {idea.rationale}
        </p>
      ) : null}
    </div>
  );
}

function DurationControl({
  current,
  onChange,
  locked,
}: {
  current: number | null;
  onChange: (minutes: number) => void;
  locked: boolean;
}) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClickOutside);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const label = current ? `${current} min` : "set runtime";
  const activeHint = current
    ? (DURATION_OPTIONS.find((o) => o.value === current)?.hint ?? null)
    : null;

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cn(
          "inline-flex items-center gap-1 rounded h-[18px] px-1.5",
          "text-[10.5px] font-mono font-semibold tabular-nums",
          "bg-transparent text-mist border border-hairline",
          "hover:text-white hover:border-hairline-strong transition-colors",
          open && "text-white border-hairline-strong bg-white/[0.03]",
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={
          locked
            ? "regenerating now — picking a new runtime starts another fresh run"
            : "change target runtime · regenerates the script"
        }
      >
        <Clock size={10} weight="bold" />
        <span>{label}</span>
        <CaretDown size={9} weight="bold" className="opacity-70" />
      </button>

      {open ? (
        <div
          className={cn(
            "absolute z-20 top-full mt-1.5 left-0 min-w-[220px]",
            "rounded-md border border-hairline bg-night shadow-xl",
            "overflow-hidden",
          )}
          role="listbox"
        >
          <div className="px-3 pt-2.5 pb-1.5 border-b border-hairline">
            <div className="font-mono text-[9.5px] uppercase tracking-[0.2em] text-mist">
              change runtime
            </div>
            <div className="mt-0.5 text-[11px] text-white/70 leading-[1.45]">
              re-runs the script writer + outline planner against the new
              target. previous versions stay in history.
            </div>
            {activeHint ? (
              <div className="mt-1 font-mono text-[9.5px] text-mist">
                current · {activeHint}
              </div>
            ) : null}
          </div>
          <ul className="py-1">
            {DURATION_OPTIONS.map((opt) => {
              const isCurrent = opt.value === current;
              return (
                <li key={opt.value}>
                  <button
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      if (!isCurrent) onChange(opt.value);
                    }}
                    className={cn(
                      "w-full flex items-center gap-2 px-3 py-1.5",
                      "text-left transition-colors",
                      isCurrent
                        ? "bg-white/[0.03]"
                        : "hover:bg-white/[0.04] cursor-pointer",
                    )}
                  >
                    <span
                      className={cn(
                        "text-[12.5px] tabular-nums w-[44px] shrink-0",
                        isCurrent ? "text-white" : "text-white/85",
                      )}
                    >
                      {opt.label}
                    </span>
                    <span className="text-[11.5px] text-mist truncate flex-1">
                      {opt.hint}
                    </span>
                    {isCurrent ? (
                      <Check size={11} weight="bold" className="text-cinnabar shrink-0" />
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
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
