import * as Tabs from "@radix-ui/react-tabs";
import {
  Graph,
  Rss,
  FileMd,
  Lightbulb,
} from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { cn } from "../lib/cn";
import GraphTabComponent from "./library/GraphTab";
import KnowTabComponent from "./library/KnowTab";
import SourcesTabComponent from "./library/SourcesTab";
import InsightsTabComponent from "./library/InsightsTab";

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
            <KnowTabComponent />
          </Tabs.Content>
          <Tabs.Content value="graph">
            <GraphTabComponent />
          </Tabs.Content>
          <Tabs.Content value="sources">
            <SourcesTabComponent />
          </Tabs.Content>
          <Tabs.Content value="insights">
            <InsightsTabComponent />
          </Tabs.Content>
        </Tabs.Root>
      </PageContainer>
    </Shell>
  );
}

