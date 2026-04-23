import * as Tabs from "@radix-ui/react-tabs";
import { useState } from "react";
import {
  Graph,
  Rss,
  FileMd,
  Lightbulb,
  Copy,
  Check,
} from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Badge } from "../components/ui/Badge";
import { cn } from "../lib/cn";

const TABS = [
  { id: "know", label: "What I know", icon: Lightbulb },
  { id: "graph", label: "Knowledge graph", icon: Graph },
  { id: "sources", label: "Sources", icon: Rss },
  { id: "insights", label: "Insights", icon: FileMd },
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

function KnowTab() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <StatCard label="nodes" value="1,284" delta="+62 this wk" />
      <StatCard label="sources" value="11" delta="2 ingesting" />
      <StatCard label="skills.md" value="4" delta="2.1 kb avg" />
      <div className="lg:col-span-3 rounded-xl border border-hairline bg-surface p-5 mt-2">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-sans font-semibold text-[14px] text-white">
            Recent additions
          </h3>
          <span className="font-mono text-[10.5px] uppercase tracking-[0.2em] text-mist">
            last 14 days
          </span>
        </div>
        <ul className="divide-y divide-hairline">
          {[
            { t: "Why AI agents replace SaaS", s: "published", d: "2h ago", n: 8 },
            { t: "hormozi-hook.skill.md", s: "upload", d: "1d ago", n: 14 },
            { t: "Newsletter — Lenny's, Apr 18", s: "newsletter", d: "3d ago", n: 6 },
            { t: "The knowledge graph monologue", s: "published", d: "1w ago", n: 11 },
          ].map((row) => (
            <li
              key={row.t}
              className="flex items-center gap-4 py-3 text-[13px]"
            >
              <span className="text-white/85 flex-1 truncate">{row.t}</span>
              <Badge tone="muted">{row.s}</Badge>
              <span className="font-mono text-[11px] text-mist w-14 text-right tabular-nums">
                {row.n} nodes
              </span>
              <span className="font-mono text-[11px] text-mist w-16 text-right">
                {row.d}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function GraphTab() {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-10 text-center">
      <Graph size={20} className="text-cinnabar mx-auto mb-3" />
      <p className="text-[14px] text-white mb-1">
        Graph view renders once embeddings are indexed.
      </p>
      <p className="text-[12.5px] text-mist font-mono">
        pgvector · ivfflat · building
      </p>
    </div>
  );
}

function SourcesTab() {
  const [copied, setCopied] = useState(false);
  const alias = "alex+ladder@ingest.ladder.so";

  function copy() {
    navigator.clipboard.writeText(alias);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className="space-y-4">
      {/* Forwarding alias is the primary element — design-sys empty-state rule */}
      <div className="rounded-xl border border-cinnabar/30 bg-cinnabar/[0.04] p-5">
        <div className="flex items-center justify-between mb-1">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-cinnabar">
            your forwarding alias
          </span>
          <Badge tone="cinnabar">active</Badge>
        </div>
        <h3 className="font-display text-[22px] text-white leading-tight mb-1">
          Forward any newsletter here.
        </h3>
        <p className="text-[13px] text-mist mb-4 max-w-[60ch]">
          Every forwarded email is extracted, chunked, embedded, and added to
          your graph. No setup — just forward.
        </p>
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
      </div>

      <div className="rounded-xl border border-hairline bg-surface">
        <div className="flex items-center justify-between px-5 py-3 border-b border-hairline">
          <span className="text-[13px] text-white font-medium">
            Connected sources
          </span>
          <span className="font-mono text-[10.5px] text-mist">11 active</span>
        </div>
        <ul className="divide-y divide-hairline">
          {[
            { t: "Lenny's Newsletter", k: "email · weekly", last: "3d" },
            { t: "Stratechery", k: "email · 2x/wk", last: "1d" },
            { t: "Ben's Bites", k: "email · daily", last: "2h" },
            { t: "YouTube — @laddercreator", k: "yt api", last: "15m" },
          ].map((s) => (
            <li
              key={s.t}
              className="flex items-center gap-4 px-5 py-3 text-[13px]"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-cinnabar" />
              <span className="text-white flex-1 truncate">{s.t}</span>
              <span className="font-mono text-[11px] text-mist">{s.k}</span>
              <span className="font-mono text-[11px] text-mist w-14 text-right">
                {s.last}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function InsightsTab() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {[
        {
          t: "AI agents vs. SaaS is trending 4.2× in your niche.",
          d: "Covered once in March — refresh angle?",
        },
        {
          t: "You haven't published in 11 days.",
          d: "Your cadence average is 6.4 days. Consider the top idea.",
        },
        {
          t: "Scripts >22 min underperform for you.",
          d: "Average retention drops to 34%. 14–18m is your sweet spot.",
        },
        {
          t: "Hormozi-hook skill boosted CTR 18%.",
          d: "Applied to 3 scripts · still holding.",
        },
      ].map((i) => (
        <div
          key={i.t}
          className="rounded-xl border border-hairline bg-surface p-5 hover:border-l-[3px] hover:border-l-cinnabar hover:pl-[calc(1.25rem-2px)] transition-all duration-150"
        >
          <div className="flex items-start gap-2.5">
            <Lightbulb
              size={14}
              weight="fill"
              className="text-cinnabar mt-0.5 shrink-0"
            />
            <div>
              <p className="text-[13.5px] text-white leading-snug mb-1.5">
                {i.t}
              </p>
              <p className="text-[12.5px] text-mist leading-[1.5]">{i.d}</p>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function StatCard({
  label,
  value,
  delta,
}: {
  label: string;
  value: string;
  delta: string;
}) {
  return (
    <div className="rounded-xl border border-hairline bg-surface p-5">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-2">
        {label}
      </div>
      <div className="font-display text-[32px] text-white leading-none tabular-nums">
        {value}
      </div>
      <div className="mt-2 font-mono text-[11px] text-cinnabar/80">{delta}</div>
    </div>
  );
}
