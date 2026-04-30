import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Lightbulb,
  MagnifyingGlass,
  FileText,
  ArrowRight,
  Sparkle,
  TrendUp,
  Clock,
} from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Button } from "../components/ui/Button";
import { Input, Textarea } from "../components/ui/Input";
import { Badge } from "../components/ui/Badge";
import { useIdeas } from "../lib/useIdeas";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/cn";
import {
  ResearchRunPanel,
  clearStoredRun,
  loadStoredRun,
} from "../components/research/ResearchRunPanel";
import {
  ContentExtractPanel,
  type ContentExtractSetup,
} from "../components/extract/ContentExtractPanel";
import { MakeBrandPicker } from "../components/research/MakeBrandPicker";
import type { ResearchSetup } from "../lib/agents";

type Option = "ideas" | "research" | "content";

// Founder-friendly preset durations. 10 min is the default — matches the
// PRD's "essay-length founder video" framing and keeps cost predictable.
// Anything outside this set is still possible by hand-editing on /studio.
const DURATION_OPTIONS: { value: number; label: string; hint: string }[] = [
  { value: 5, label: "5 min", hint: "hot take · 1 sharp claim" },
  { value: 10, label: "10 min", hint: "framework · 2-3 beats" },
  { value: 15, label: "15 min", hint: "essay · with examples" },
  { value: 20, label: "20 min", hint: "founder essay · default" },
  { value: 30, label: "30 min", hint: "deep dive · multi-arc" },
  { value: 45, label: "45 min", hint: "masterclass · full system" },
];

const DEFAULT_DURATION_MIN = 10;

export default function MakePage() {
  const [active, setActive] = useState<Option>("research");
  const [topic, setTopic] = useState("");
  const [duration, setDuration] = useState<number>(() => {
    const restored = loadStoredRun();
    return restored?.durationMin ?? DEFAULT_DURATION_MIN;
  });
  const [content, setContent] = useState("");
  const [researchSetup, setResearchSetup] = useState<ResearchSetup | null>(null);
  const [extractSetup, setExtractSetup] = useState<ContentExtractSetup | null>(null);
  const [hasRestoredRun, setHasRestoredRun] = useState(() => loadStoredRun() !== null);
  const navigate = useNavigate();
  const { ideas, loading: ideasLoading, refresh: refreshIdeas } = useIdeas();
  const { profile } = useAuth();
  const panelRef = useRef<HTMLDivElement>(null);

  function startResearch() {
    const cleaned = topic.trim();
    if (!cleaned) return;
    setExtractSetup(null);
    setResearchSetup({ topic: cleaned, duration_min: duration });
    setHasRestoredRun(false);
    requestAnimationFrame(() => {
      panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function startExtract() {
    const cleaned = content.trim();
    if (cleaned.length < 80) return;
    setResearchSetup(null);
    clearStoredRun();
    setHasRestoredRun(false);
    setExtractSetup({ source_content: cleaned });
    requestAnimationFrame(() => {
      panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  useEffect(() => {
    if (researchSetup || extractSetup || !hasRestoredRun) return;
    requestAnimationFrame(() => {
      panelRef.current?.scrollIntoView({ behavior: "auto", block: "nearest" });
    });
  }, [researchSetup, extractSetup, hasRestoredRun]);

  const handleResearchStartOver = useCallback(() => {
    clearStoredRun();
    setResearchSetup(null);
    setHasRestoredRun(false);
    setTopic("");
  }, []);

  const handleExtractStartOver = useCallback(() => {
    setExtractSetup(null);
    setContent("");
  }, []);

  const handleIdeasChanged = useCallback(() => {
    void refreshIdeas();
  }, [refreshIdeas]);

  const researchPanelVisible = researchSetup !== null || hasRestoredRun;
  const extractPanelVisible = extractSetup !== null;

  const ideasCount = ideas.length;
  const ideasDimmed = !ideasLoading && ideasCount === 0;
  const topIdeas = ideas.slice(0, 3);

  const contentLength = content.trim().length;
  const contentTooShort = contentLength > 0 && contentLength < 80;

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
                disabled={researchSetup !== null}
              />
              <DurationSelect
                value={duration}
                onChange={setDuration}
                disabled={researchSetup !== null}
              />
              <div onClick={(e) => e.stopPropagation()}>
                <MakeBrandPicker compact />
              </div>
              <Button
                size="sm"
                onClick={startResearch}
                disabled={!topic.trim() || researchSetup !== null}
                className="w-full"
              >
                <Sparkle size={12} weight="fill" />
                {researchSetup !== null
                  ? "Running…"
                  : hasRestoredRun
                    ? "New research"
                    : "Research & stream"}
              </Button>
              <p className="text-[11.5px] text-mist font-mono pt-0.5">
                exa · sonnet-4.6 ·{" "}
                <span className="text-white/75">{duration}-min target</span>
                {hasRestoredRun && !researchSetup ? " · last run restored below" : ""}
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
              disabled={extractSetup !== null}
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={startExtract}
              className="w-full mt-2"
              disabled={contentLength < 80 || extractSetup !== null}
              title={
                contentLength < 80 ? "Paste at least ~80 chars of content" : undefined
              }
            >
              {extractSetup !== null ? "Extracting…" : "Extract & build"}
              <ArrowRight size={12} weight="bold" />
            </Button>
            <p className="text-[11px] text-mist font-mono pt-1.5">
              {contentTooShort
                ? `${contentLength}/80 chars`
                : "sonnet-4.6 · auto-saves & opens studio"}
            </p>
          </OptionCard>
        </div>

        {/* Active run panel — only one shows at a time. */}
        {researchPanelVisible || extractPanelVisible ? (
          <div ref={panelRef}>
            {extractPanelVisible ? (
              <ContentExtractPanel
                setup={extractSetup}
                onStartOver={handleExtractStartOver}
                onIdeasChanged={handleIdeasChanged}
              />
            ) : (
              <ResearchRunPanel
                setup={researchSetup}
                onStartOver={handleResearchStartOver}
                onIdeasChanged={handleIdeasChanged}
              />
            )}
          </div>
        ) : null}

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
    </Shell>
  );
}

function DurationSelect({
  value,
  onChange,
  disabled,
}: {
  value: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  const active = DURATION_OPTIONS.find((o) => o.value === value) ?? DURATION_OPTIONS[1];
  return (
    <label
      className={cn(
        "relative flex items-center gap-2 rounded-md bg-surface-input",
        "border border-transparent focus-within:border-cinnabar",
        "transition-colors duration-150 px-3 h-9",
        disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer",
      )}
      onClick={(e) => e.stopPropagation()}
    >
      <span className="sr-only">Target video duration</span>
      <Clock size={13} weight="bold" className="text-mist shrink-0" />
      <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-mist shrink-0">
        length
      </span>
      <span className="text-[13.5px] text-white tabular-nums shrink-0">
        {active.label}
      </span>
      <span className="text-[11.5px] text-mist truncate min-w-0 flex-1">
        · {active.hint}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
        aria-label="Target video duration"
      >
        {DURATION_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label} — {o.hint}
          </option>
        ))}
      </select>
    </label>
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
