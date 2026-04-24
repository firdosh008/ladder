import * as Tabs from "@radix-ui/react-tabs";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Graph,
  Rss,
  FileMd,
  Lightbulb,
  Copy,
  Check,
  ArrowRight,
} from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Badge } from "../components/ui/Badge";
import { cn } from "../lib/cn";
import { useAuth, type Profile } from "../lib/auth";

const TABS = [
  { id: "know", label: "What I know", icon: Lightbulb },
  { id: "graph", label: "Knowledge graph", icon: Graph },
  { id: "sources", label: "Sources", icon: Rss },
  { id: "insights", label: "Insights", icon: FileMd },
];

const PROFILE_FIELDS: {
  key: keyof Profile;
  label: string;
  hint: string;
  multiline?: boolean;
}[] = [
  { key: "display_name", label: "Display name", hint: "Shown on dashboard + signatures." },
  { key: "positioning", label: "Positioning", hint: "One sentence on what you do and for whom.", multiline: true },
  { key: "audience", label: "Audience", hint: "Who the videos are for." },
  { key: "voice", label: "Voice", hint: "How you sound. Auto-refined from script edits.", multiline: true },
  { key: "things_to_avoid", label: "Things to avoid", hint: "Topics, phrasings, or framings to skip.", multiline: true },
];

export default function LibraryPage() {
  return (
    <Shell>
      <PageContainer>
        <PageHeader
          eyebrow="§ /library · memory"
          title="What you know"
          description="Your ingested work — posts, docs, newsletters, uploaded .md frameworks. Chunked, embedded, strictly scoped to you."
        />

        <Tabs.Root defaultValue="know">
          <Tabs.List className="flex items-center gap-1 border-b border-hairline mb-6">
            {TABS.map((t) => {
              const Icon = t.icon;
              return (
                <Tabs.Trigger
                  key={t.id}
                  value={t.id}
                  className={cn(
                    "group inline-flex items-center gap-2 px-3 h-9 text-[13px]",
                    "text-mist hover:text-white transition-colors relative",
                    "data-[state=active]:text-white",
                  )}
                >
                  <Icon size={13} weight="regular" />
                  <span>{t.label}</span>
                  <span
                    className={cn(
                      "absolute left-2 right-2 -bottom-px h-[2px] rounded-full bg-cinnabar",
                      "opacity-0 group-data-[state=active]:opacity-100 transition-opacity",
                    )}
                  />
                </Tabs.Trigger>
              );
            })}
          </Tabs.List>

          <Tabs.Content value="know">
            <KnowTab />
          </Tabs.Content>
          <Tabs.Content value="graph">
            <GraphTab />
          </Tabs.Content>
          <Tabs.Content value="sources">
            <SourcesTab />
          </Tabs.Content>
          <Tabs.Content value="insights">
            <InsightsTab />
          </Tabs.Content>
        </Tabs.Root>
      </PageContainer>
    </Shell>
  );
}

function completenessFor(profile: Profile | null): {
  pct: number;
  filled: number;
  total: number;
} {
  const keys: (keyof Profile)[] = [
    "display_name",
    "positioning",
    "audience",
    "voice",
    "things_to_avoid",
    "creators_followed",
  ];
  if (!profile) return { pct: 0, filled: 0, total: keys.length };
  const filled = keys.filter((k) => {
    const v = profile[k];
    if (Array.isArray(v)) return v.length > 0;
    return typeof v === "string" && v.trim().length > 0;
  }).length;
  return {
    pct: Math.round((filled / keys.length) * 100),
    filled,
    total: keys.length,
  };
}

function KnowTab() {
  const { profile, loading } = useAuth();
  const { pct, filled, total } = useMemo(
    () => completenessFor(profile),
    [profile],
  );
  const creators = profile?.creators_followed ?? [];

  return (
    <div className="space-y-4 max-w-[1100px]">
      <div className="rounded-xl border border-hairline bg-surface p-5">
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-1">
              profile completeness
            </div>
            <div className="font-display text-[28px] text-white leading-none tabular-nums">
              {pct}%
            </div>
          </div>
          <Link
            to="/settings"
            className="inline-flex items-center gap-1.5 text-[12.5px] text-mist hover:text-white transition-colors"
          >
            Edit in settings
            <ArrowRight size={11} weight="bold" />
          </Link>
        </div>
        <div className="h-1 rounded-full bg-white/[0.04] overflow-hidden">
          <div
            className="h-full bg-cinnabar transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
        <p className="mt-3 font-mono text-[10.5px] uppercase tracking-[0.18em] text-mist">
          {filled} / {total} fields filled
        </p>
      </div>

      <div className="rounded-xl border border-hairline bg-surface">
        <div className="px-5 py-3 border-b border-hairline flex items-center justify-between">
          <span className="text-[13px] text-white font-medium">
            What the agents see about you
          </span>
          <span className="font-mono text-[10.5px] text-mist uppercase tracking-[0.18em]">
            interpolated into every prompt
          </span>
        </div>
        {loading && !profile ? (
          <div className="px-5 py-8 font-mono text-[11.5px] text-mist">
            loading profile…
          </div>
        ) : (
          <ul className="divide-y divide-hairline">
            {PROFILE_FIELDS.map(({ key, label, hint, multiline }) => {
              const raw = profile?.[key];
              const value =
                typeof raw === "string" && raw.trim().length > 0
                  ? raw
                  : null;
              return (
                <li
                  key={key as string}
                  className="px-5 py-3.5 grid grid-cols-[180px_1fr] gap-4 items-start"
                >
                  <div>
                    <div className="text-[13px] text-white">{label}</div>
                    <div className="font-mono text-[11px] text-mist mt-0.5">
                      {hint}
                    </div>
                  </div>
                  <div
                    className={cn(
                      "text-[13px] leading-[1.55]",
                      value ? "text-white/85" : "text-mist italic",
                      multiline ? "whitespace-pre-wrap" : "truncate",
                    )}
                  >
                    {value ?? "not yet set"}
                  </div>
                </li>
              );
            })}
            <li className="px-5 py-3.5 grid grid-cols-[180px_1fr] gap-4 items-start">
              <div>
                <div className="text-[13px] text-white">Creators you sound closest to</div>
                <div className="font-mono text-[11px] text-mist mt-0.5">
                  Seeds the voice profile.
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {creators.length === 0 ? (
                  <span className="text-[13px] text-mist italic">not yet set</span>
                ) : (
                  creators.map((c) => (
                    <span
                      key={c}
                      className="font-mono text-[11px] text-white/85 border border-hairline rounded px-2 py-0.5"
                    >
                      {c}
                    </span>
                  ))
                )}
              </div>
            </li>
          </ul>
        )}
      </div>
    </div>
  );
}

function GraphTab() {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-10 text-center max-w-[1100px]">
      <Graph size={20} className="text-cinnabar mx-auto mb-3" />
      <p className="text-[14px] text-white mb-1">
        Knowledge graph ships with the embedding pipeline.
      </p>
      <p className="text-[12.5px] text-mist font-mono">
        pgvector · 1536d · per-user scoped
      </p>
    </div>
  );
}

function SourcesTab() {
  const { profile } = useAuth();
  const alias = profile?.forwarding_alias ?? null;
  const [copied, setCopied] = useState(false);

  function copy() {
    if (!alias) return;
    navigator.clipboard.writeText(alias);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className="space-y-4 max-w-[1100px]">
      <div
        className={cn(
          "rounded-xl border p-5",
          alias
            ? "border-cinnabar/30 bg-cinnabar/[0.04]"
            : "border-hairline bg-surface",
        )}
      >
        <div className="flex items-center justify-between mb-1">
          <span
            className={cn(
              "font-mono text-[10.5px] uppercase tracking-[0.22em]",
              alias ? "text-cinnabar" : "text-mist",
            )}
          >
            your forwarding alias
          </span>
          {alias ? <Badge tone="cinnabar">active</Badge> : <Badge tone="muted">pending</Badge>}
        </div>
        <h3 className="font-display text-[22px] text-white leading-tight mb-1">
          Forward any newsletter here.
        </h3>
        <p className="text-[13px] text-mist mb-4 max-w-[60ch]">
          Every forwarded email is extracted, chunked, embedded, and added to
          your graph. No setup — just forward.
        </p>
        {alias ? (
          <div className="flex items-center gap-2">
            <code className="flex-1 font-mono text-[13px] text-white bg-night border border-hairline rounded-md px-3 h-9 flex items-center">
              {alias}
            </code>
            <button
              onClick={copy}
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-md bg-white/[0.06] border border-hairline hover:bg-white/[0.1] transition-colors text-[12.5px] text-white font-medium"
            >
              {copied ? (
                <>
                  <Check size={12} weight="bold" className="text-cinnabar" />
                  copied
                </>
              ) : (
                <>
                  <Copy size={12} weight="bold" />
                  copy
                </>
              )}
            </button>
          </div>
        ) : (
          <p className="font-mono text-[11.5px] text-mist">
            Alias will be provisioned on first newsletter-source addition.
          </p>
        )}
      </div>

      <div className="rounded-xl border border-hairline bg-surface p-10 text-center">
        <Rss size={18} className="text-mist mx-auto mb-2" />
        <p className="text-[13.5px] text-white mb-1">No sources connected yet.</p>
        <p className="text-[12px] text-mist font-mono">
          Forward a newsletter to your alias to add the first source.
        </p>
      </div>
    </div>
  );
}

function InsightsTab() {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-10 text-center max-w-[1100px]">
      <Lightbulb size={18} className="text-cinnabar mx-auto mb-2" />
      <p className="text-[13.5px] text-white mb-1">No insights yet.</p>
      <p className="text-[12px] text-mist font-mono leading-[1.6] max-w-[52ch] mx-auto">
        Synthesised signals from the research agent + your connected sources
        surface here once you've published a few videos.
      </p>
    </div>
  );
}
