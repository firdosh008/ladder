import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Lightbulb,
  MagnifyingGlass,
  FileText,
  ArrowRight,
  Sparkle,
  TrendUp,
} from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Button } from "../components/ui/Button";
import { Input, Textarea } from "../components/ui/Input";
import { Badge } from "../components/ui/Badge";
import { useIdeas } from "../lib/useIdeas";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/cn";
import { ResearchStreamDrawer } from "../components/research/ResearchStreamDrawer";
import type { ResearchSetup } from "../lib/agents";

type Option = "ideas" | "research" | "content";

export default function MakePage() {
  const [active, setActive] = useState<Option>("research");
  const [topic, setTopic] = useState("");
  const [content, setContent] = useState("");
  const [researchSetup, setResearchSetup] = useState<ResearchSetup | null>(null);
  const navigate = useNavigate();
  const { ideas, loading: ideasLoading, refresh: refreshIdeas } = useIdeas();
  const { profile } = useAuth();

  function startResearch() {
    const cleaned = topic.trim();
    if (!cleaned) return;
    setResearchSetup({ topic: cleaned });
  }

  const handleResearchClose = useCallback(
    (open: boolean) => {
      if (!open) {
        setResearchSetup(null);
        void refreshIdeas();
      }
    },
    [refreshIdeas],
  );

  const ideasCount = ideas.length;
  const ideasDimmed = !ideasLoading && ideasCount === 0;
  const topIdeas = ideas.slice(0, 3);

  return (
    <Shell>
      <PageContainer>
        <PageHeader
          eyebrow="§ /make · entry"
          title="What are we making?"
          description="Pick a starting point. The studio loads instantly — no queue, no generate button."
          right={
            <div className="flex items-center gap-2">
              <Badge tone="cinnabar">
                <TrendUp size={10} weight="bold" />
                {ideasLoading ? "…" : `${ideasCount} ready`}
              </Badge>
            </div>
          }
        />

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Option 1 — Pick from your ideas */}
          <OptionCard
            active={active === "ideas"}
            onClick={() => setActive("ideas")}
            icon={Lightbulb}
            index="01"
            title="Pick from your ideas"
            subtitle={
              ideasLoading
                ? "Loading…"
                : ideasCount === 0
                  ? "No ideas yet — add one in /videos"
                  : `${ideasCount} idea${ideasCount === 1 ? "" : "s"} · sorted by score`
            }
            dimmed={ideasDimmed}
          >
            <ul className="space-y-1.5 pt-1 min-h-[66px]">
              {topIdeas.length === 0 && !ideasLoading ? (
                <li className="text-[12.5px] text-mist font-mono">
                  — empty —
                </li>
              ) : (
                topIdeas.map((idea) => (
                  <li
                    key={idea.id}
                    className="flex items-center gap-2.5 text-[12.5px] text-white/75"
                  >
                    <span
                      className={cn(
                        "font-mono mono-tab shrink-0 tabular-nums text-[10.5px]",
                        (idea.opportunity_score ?? 0) >= 90
                          ? "text-cinnabar"
                          : "text-mist",
                      )}
                    >
                      {idea.opportunity_score ?? "—"}
                    </span>
                    <span className="truncate">{idea.title}</span>
                  </li>
                ))
              )}
            </ul>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate("/videos")}
              className="w-full mt-4"
              disabled={ideasDimmed}
            >
              Browse all {ideasCount}
              <ArrowRight size={12} weight="bold" />
            </Button>
          </OptionCard>

          {/* Option 2 — Research and generate */}
          <OptionCard
            active={active === "research"}
            onClick={() => setActive("research")}
            icon={MagnifyingGlass}
            index="02"
            title="Research and generate"
            subtitle="Ladder runs a targeted search · 3–5 ideas back in ~15s"
            recommended
          >
            <div className="space-y-2">
              <Input
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="e.g. why AI agents replace SaaS"
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && topic.trim()) {
                    e.preventDefault();
                    startResearch();
                  }
                }}
              />
              <Button
                size="sm"
                onClick={startResearch}
                disabled={!topic.trim()}
                className="w-full"
              >
                <Sparkle size={12} weight="fill" />
                Research & stream
              </Button>
              <p className="text-[11.5px] text-mist font-mono pt-0.5">
                exa · sonnet-4.6
              </p>
            </div>
          </OptionCard>

          {/* Option 3 — Paste content */}
          <OptionCard
            active={active === "content"}
            onClick={() => setActive("content")}
            icon={FileText}
            index="03"
            title="Turn content into a video"
            subtitle="Paste a post, doc, or thread · duration derived from depth"
          >
            <Textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Paste an article, tweet thread, or Notion doc…"
              className="min-h-[88px] text-[12.5px]"
              onClick={(e) => e.stopPropagation()}
            />
            <Button
              variant="secondary"
              size="sm"
              disabled
              className="w-full mt-2"
              title="Content extraction crew ships next"
            >
              Extract & build
              <ArrowRight size={12} weight="bold" />
            </Button>
            <p className="text-[11px] text-mist font-mono pt-1.5">
              extract crew ships next
            </p>
          </OptionCard>
        </div>

        {/* Quiet metadata row */}
        <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
          <span>session · fresh</span>
          <span className="h-3 w-px bg-hairline" />
          <span>
            alias ·{" "}
            <span className="text-white/80">
              {profile?.forwarding_alias ?? "not configured"}
            </span>
          </span>
        </div>
      </PageContainer>

      <ResearchStreamDrawer
        open={researchSetup !== null}
        onOpenChange={handleResearchClose}
        setup={researchSetup}
        onIdeaSaved={() => void refreshIdeas()}
      />
    </Shell>
  );
}

function OptionCard({
  active,
  onClick,
  icon: Icon,
  index,
  title,
  subtitle,
  children,
  dimmed,
  recommended,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ElementType;
  index: string;
  title: string;
  subtitle: string;
  children: React.ReactNode;
  dimmed?: boolean;
  recommended?: boolean;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        "group relative rounded-xl border bg-surface p-5",
        "transition-all duration-150 ease-out cursor-pointer",
        active
          ? "border-cinnabar/50 bg-cinnabar/[0.035]"
          : "border-hairline hover:border-hairline-strong",
        dimmed && "opacity-50",
      )}
    >
      {/* active indicator rail */}
      {active ? (
        <span className="absolute left-0 top-4 bottom-4 w-[2px] rounded-r-full bg-cinnabar" />
      ) : null}

      <div className="flex items-start justify-between mb-4">
        <div
          className={cn(
            "h-9 w-9 rounded-md grid place-items-center border",
            active
              ? "bg-cinnabar/[0.15] border-cinnabar/40 text-cinnabar"
              : "bg-white/[0.03] border-hairline text-white/70 group-hover:text-white",
          )}
        >
          <Icon size={16} weight={active ? "fill" : "regular"} />
        </div>
        <div className="flex items-center gap-1.5">
          {recommended ? (
            <Badge tone="cinnabar" className="h-[18px]">
              recommended
            </Badge>
          ) : null}
          <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
            {index}
          </span>
        </div>
      </div>

      <div className="mb-4">
        <h3 className="font-sans font-semibold text-[16px] text-white leading-tight mb-1">
          {title}
        </h3>
        <p className="text-[12.5px] text-mist leading-[1.5]">{subtitle}</p>
      </div>

      {children}
    </div>
  );
}
