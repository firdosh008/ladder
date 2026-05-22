import { useNavigate } from "react-router-dom";
import { YoutubeLogo, Plug } from "@phosphor-icons/react";
import { Button } from "../ui/Button";
import { cn } from "../../lib/cn";
import type { PublishedEntry } from "../../types/videos";
import { PublishedCard } from "./PublishedCard";

type Props = {
  entries: PublishedEntry[];
  youtubeConnected: boolean;
  onCardClick: (entry: PublishedEntry) => void;
};

export function PublishedColumn({
  entries,
  youtubeConnected,
  onCardClick,
}: Props) {
  const navigate = useNavigate();

  const sorted = [...entries].sort(
    (a, b) => {
      const da = a.published_at ? new Date(a.published_at).getTime() : 0;
      const db = b.published_at ? new Date(b.published_at).getTime() : 0;
      return db - da;
    },
  );

  return (
    <div className="min-w-[300px] w-[300px] shrink-0 flex flex-col">
      <div className="flex items-center justify-between px-1 pb-2.5">
        <div className="inline-flex items-center gap-2 rounded-md px-2 py-1 bg-white/[0.04] border border-hairline">
          <span className="h-1.5 w-1.5 rounded-full shrink-0 bg-mist" />
          <span className="text-[12.5px] font-semibold text-white/90 leading-none">
            Published
          </span>
          <span className="font-mono text-[10.5px] text-mist tabular-nums leading-none">
            {entries.length}
          </span>
        </div>
      </div>

      <div
        className={cn(
          "flex-1 flex flex-col gap-2 rounded-xl border p-2",
          "border-transparent bg-white/[0.015]",
        )}
      >
        {!youtubeConnected ? (
          <div className="flex flex-col items-center justify-center py-10 px-3 gap-3">
            <YoutubeLogo size={24} weight="bold" className="text-mist/40" />
            <p className="text-[12px] text-mist/70 text-center leading-[1.5]">
              Connect YouTube to track published video performance.
            </p>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => navigate("/settings")}
            >
              <Plug size={11} weight="bold" />
              Connect YouTube
            </Button>
          </div>
        ) : sorted.length === 0 ? (
          <div className="flex items-center justify-center py-10 px-3">
            <p className="text-[12px] text-mist/70 text-center leading-[1.5]">
              Waiting for first sync…
            </p>
          </div>
        ) : (
          sorted.map((entry) => (
            <PublishedCard
              key={entry.id}
              entry={entry}
              onClick={onCardClick}
            />
          ))
        )}
      </div>
    </div>
  );
}
