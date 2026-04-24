import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft,
  Image as ImageIcon,
  Sparkle,
  Cpu,
  Lightbulb,
} from "@phosphor-icons/react";
import { Shell } from "../components/app/Shell";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { useIdeas, type Idea } from "../lib/useIdeas";

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
        <ScriptPanel idea={idea} loading={loading} />
        <ScenePanel />
        <ChatPanel />
      </div>
    </Shell>
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

function ScriptPanel({ idea, loading }: { idea: Idea | null; loading: boolean }) {
  return (
    <section className="flex flex-col min-h-0 bg-night">
      <PanelHeader title="Script" hint="stream_script · not yet wired" />
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-5">
        {loading ? (
          <p className="font-mono text-[11.5px] text-mist">loading idea…</p>
        ) : !idea ? (
          <EmptyBlock
            icon={Lightbulb}
            title="No idea loaded."
            body="Go back to /videos and pick one, or run a research sweep from /make."
          />
        ) : (
          <>
            <div>
              <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-2">
                idea
              </div>
              <h2 className="font-display text-[26px] text-white leading-[1.15] tracking-tight">
                {idea.title}
              </h2>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {typeof idea.opportunity_score === "number" ? (
                  <Badge tone="cinnabar">
                    score {idea.opportunity_score}
                  </Badge>
                ) : null}
                {typeof idea.outlier_score === "number" ? (
                  <Badge tone="muted">
                    {idea.outlier_score.toFixed(1)}× outlier
                  </Badge>
                ) : null}
                {idea.idea_type ? (
                  <Badge tone="muted">{idea.idea_type}</Badge>
                ) : null}
              </div>
            </div>
            {idea.rationale ? (
              <div>
                <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-2">
                  rationale
                </div>
                <p className="text-[14px] text-white/85 leading-[1.6]">
                  {idea.rationale}
                </p>
              </div>
            ) : null}
            {idea.body ? (
              <div>
                <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-2">
                  your notes
                </div>
                <p className="text-[14px] text-white/85 leading-[1.6] whitespace-pre-wrap">
                  {idea.body}
                </p>
              </div>
            ) : null}
            {idea.source_content ? (
              <div>
                <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-2">
                  research topic
                </div>
                <p className="text-[13.5px] text-mist italic leading-[1.6]">
                  {idea.source_content}
                </p>
              </div>
            ) : null}
            <EmptyBlock
              icon={Sparkle}
              title="Script crew ships next."
              body="stream_script will auto-run here on studio load and write talking points + transitions section-by-section."
            />
          </>
        )}
      </div>
    </section>
  );
}

function ScenePanel() {
  return (
    <section className="flex flex-col min-h-0 bg-night">
      <PanelHeader title="Scene" hint="build_scene · not yet wired" />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <EmptyBlock
          icon={Cpu}
          title="Scene outline + Excalidraw build coming."
          body="Once the Scene crew lands, the outline will generate alongside the script and 'Approve and build' will produce a shareable Excalidraw URL."
        />
      </div>
    </section>
  );
}

function ChatPanel() {
  return (
    <aside className="flex flex-col min-h-0 bg-night">
      <PanelHeader title="Sharpen" hint="sharpen_this · not yet wired" />
      <div className="flex-1 overflow-y-auto px-6 py-6">
        <EmptyBlock
          icon={Sparkle}
          title="AI chat ships with the Studio vertical."
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
