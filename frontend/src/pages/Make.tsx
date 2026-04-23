import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Lightbulb,
  MagnifyingGlass,
  FileText,
  ArrowRight,
  Sparkle,
  Clock,
  TrendUp,
} from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Button } from "../components/ui/Button";
import { Input, Textarea } from "../components/ui/Input";
import { Badge } from "../components/ui/Badge";
import { cn } from "../lib/cn";

type Option = "ideas" | "research" | "content";

const STATE = {
  ideasCount: 7,
  lastSessionAgo: "2h ago",
  topScore: 91,
};

export default function MakePage() {
  const [active, setActive] = useState<Option>("research");
  const [topic, setTopic] = useState("");
  const [content, setContent] = useState("");
  const navigate = useNavigate();

  const ideasDimmed = STATE.ideasCount === 0;

  return (
    <Shell>
      <PageContainer>
        <PageHeader
          eyebrow="§ /make · entry"
          title="What are we making?"
          description="Pick a starting point. The studio loads instantly — no queue, no generate button."
          right={
            <div className="flex items-center gap-2">
              <Badge tone="neutral">
                <Clock size={10} weight="bold" className="text-mist" />
                {STATE.lastSessionAgo}
              </Badge>
              <Badge tone="cinnabar">
                <TrendUp size={10} weight="bold" />
                {STATE.ideasCount} ready
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
              STATE.ideasCount === 0
                ? "No ideas yet — try research"
                : `${STATE.ideasCount} ideas · sorted by score`
            }
            dimmed={ideasDimmed}
          >
            <ul className="space-y-1.5 pt-1">
              {SAMPLE_IDEAS.slice(0, 3).map((idea) => (
                <li
                  key={idea.title}
                  className="flex items-center gap-2.5 text-[12.5px] text-white/75"
                >
                  <span
                    className={cn(
                      "font-mono mono-tab shrink-0 tabular-nums text-[10.5px]",
                      idea.score >= 90 ? "text-cinnabar" : "text-mist",
                    )}
                  >
                    {idea.score}
                  </span>
                  <span className="truncate">{idea.title}</span>
                </li>
              ))}
            </ul>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => navigate("/videos")}
              className="w-full mt-4"
              disabled={ideasDimmed}
            >
              Browse all {STATE.ideasCount}
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
              />
              <Button
                size="sm"
                onClick={() => navigate("/studio/new")}
                disabled={!topic.trim()}
                className="w-full"
              >
                <Sparkle size={12} weight="fill" />
                Research & stream
              </Button>
              <p className="text-[11.5px] text-mist font-mono pt-0.5">
                gpt-4o · ~$0.03
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
              onClick={() => navigate("/studio/extract")}
              disabled={content.trim().length < 60}
              className="w-full mt-2"
            >
              Extract & build
              <ArrowRight size={12} weight="bold" />
            </Button>
            {content.trim().length > 0 && content.trim().length < 60 ? (
              <p className="text-[11px] text-mist font-mono pt-1.5">
                {60 - content.trim().length} more chars to extract
              </p>
            ) : null}
          </OptionCard>
        </div>

        {/* Contextual intelligence strip */}
        <div className="mt-8 rounded-xl border border-hairline bg-surface/50 px-5 py-4">
          <div className="flex items-start gap-3">
            <Sparkle
              size={14}
              weight="fill"
              className="text-cinnabar mt-0.5 shrink-0"
            />
            <div className="flex-1 text-[13px] leading-[1.55] text-white/80">
              <span className="text-white">
                "AI agents" is performing 4.2× above average
              </span>{" "}
              in adjacent niches this week.{" "}
              <button
                onClick={() => {
                  setActive("research");
                  setTopic("AI agents replacing SaaS");
                }}
                className="text-cinnabar hover:underline underline-offset-2"
              >
                Use as a starting point →
              </button>
            </div>
            <button className="text-mist hover:text-white transition-colors text-[18px] leading-none shrink-0">
              ×
            </button>
          </div>
        </div>

        {/* Quiet metadata row */}
        <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
          <span>session · fresh</span>
          <span className="h-3 w-px bg-hairline" />
          <span>alias · alex+ladder@ingest.ladder.so</span>
          <span className="h-3 w-px bg-hairline" />
          <span>keys · 3/4 configured</span>
        </div>
      </PageContainer>
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

const SAMPLE_IDEAS = [
  { title: "Why AI agents will replace SaaS", score: 91 },
  { title: "The new creator stack in 2026", score: 87 },
  { title: "How I scripted 30 videos in a day", score: 83 },
];
