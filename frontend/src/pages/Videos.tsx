import { useNavigate } from "react-router-dom";
import { Plus, DotsThreeVertical } from "@phosphor-icons/react";
import { Shell, PageHeader, PageContainer } from "../components/app/Shell";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { cn } from "../lib/cn";

type Status = "ideas" | "scripting" | "scene" | "ready" | "published";

const COLUMNS: { id: Status; title: string; hint: string }[] = [
  { id: "ideas", title: "Ideas", hint: "7" },
  { id: "scripting", title: "Scripting", hint: "2" },
  { id: "scene", title: "Scene", hint: "1" },
  { id: "ready", title: "Ready to record", hint: "3" },
  { id: "published", title: "Published", hint: "11" },
];

type Card = {
  id: string;
  title: string;
  status: Status;
  score?: number;
  duration?: string;
  age: string;
};

const CARDS: Card[] = [
  { id: "1", title: "Why AI agents will replace SaaS", status: "ideas", score: 91, age: "2h" },
  { id: "2", title: "The new creator stack in 2026", status: "ideas", score: 87, age: "1d" },
  { id: "3", title: "How I scripted 30 videos in a day", status: "ideas", score: 83, age: "3d" },
  { id: "4", title: "The knowledge graph monologue", status: "ideas", score: 76, age: "5d" },
  { id: "5", title: "Why founders dread voiceover", status: "ideas", score: 71, age: "1w" },
  { id: "6", title: "Shipping through the generate-button era", status: "scripting", duration: "18m", age: "32m" },
  { id: "7", title: "RAG for solo operators", status: "scripting", duration: "22m", age: "1h" },
  { id: "8", title: "Thumbnail as the first scene", status: "scene", duration: "14m", age: "4h" },
  { id: "9", title: "Scenes you don't render twice", status: "ready", duration: "20m", age: "1d" },
  { id: "10", title: "The pgvector per-user trick", status: "ready", duration: "16m", age: "2d" },
  { id: "11", title: "How we killed the generate button", status: "ready", duration: "24m", age: "3d" },
  { id: "12", title: "Why we moved off Zapier", status: "published", age: "last wk" },
  { id: "13", title: "TubeLab for founder research", status: "published", age: "2wk" },
];

export default function VideosPage() {
  const navigate = useNavigate();

  return (
    <Shell>
      <PageContainer>
        <PageHeader
          eyebrow="§ /videos · pipeline"
          title="My videos"
          description="Everything in flight — from idea to published. Drag across columns to advance a card."
          right={
            <Button onClick={() => navigate("/make")}>
              <Plus size={13} weight="bold" />
              New video
            </Button>
          }
        />

        {/* Kanban */}
        <div className="flex gap-4 overflow-x-auto pb-4 -mx-2 px-2">
          {COLUMNS.map((col) => {
            const cards = CARDS.filter((c) => c.status === col.id);
            return (
              <div
                key={col.id}
                className="min-w-[280px] w-[280px] shrink-0 flex flex-col"
              >
                <div className="flex items-center justify-between px-2 py-2 mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-[13px] font-semibold text-white">
                      {col.title}
                    </span>
                    <span className="font-mono text-[10.5px] text-mist tabular-nums">
                      {col.hint}
                    </span>
                  </div>
                  <button className="text-mist hover:text-white transition-colors">
                    <DotsThreeVertical size={14} weight="bold" />
                  </button>
                </div>

                <div className="flex-1 space-y-2 rounded-lg border border-hairline/50 bg-surface/30 p-2 min-h-[200px]">
                  {cards.length === 0 ? (
                    <EmptyColumn status={col.id} />
                  ) : (
                    cards.map((card) => (
                      <KanbanCard key={card.id} card={card} />
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </PageContainer>
    </Shell>
  );
}

function KanbanCard({ card }: { card: Card }) {
  return (
    <button
      type="button"
      className={cn(
        "group w-full text-left rounded-md border border-hairline bg-surface p-3",
        "hover:border-l-[3px] hover:border-l-cinnabar hover:pl-[calc(0.75rem-2px)]",
        "transition-all duration-150",
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="text-[13px] text-white leading-snug line-clamp-2">
          {card.title}
        </span>
        {card.score ? (
          <Badge tone={card.score >= 90 ? "cinnabar" : "neutral"}>
            {card.score}
          </Badge>
        ) : null}
      </div>
      <div className="flex items-center justify-between font-mono text-[10.5px] text-mist">
        <span>{card.duration ?? "—"}</span>
        <span>{card.age}</span>
      </div>
    </button>
  );
}

function EmptyColumn({ status }: { status: Status }) {
  const copy: Record<Status, string> = {
    ideas: "Generate ideas to fill your pipeline.",
    scripting: "Approve an idea to start scripting.",
    scene: "Scripts move here once the outline lands.",
    ready: "Scenes move here once approved.",
    published: "Connect YouTube to sync published videos.",
  };
  return (
    <div className="flex items-center justify-center h-full py-8 px-3">
      <p className="text-[12px] text-mist text-center leading-[1.5]">
        {copy[status]}
      </p>
    </div>
  );
}
