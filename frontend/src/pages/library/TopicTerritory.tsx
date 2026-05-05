import { Link } from "react-router-dom";
import { ArrowRight, Target } from "@phosphor-icons/react";
import { useTopics, type TagCount } from "../../lib/useKnowledge";

export default function TopicTerritory() {
  const { topics, loading, error, refresh } = useTopics();

  if (loading) {
    return (
      <div className="rounded-xl border border-hairline bg-surface p-5">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-3">
          topic territory
        </div>
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-8 rounded bg-white/[0.04] animate-pulse"
            />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-hairline bg-surface p-5">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-3">
          topic territory
        </div>
        <p className="text-[12.5px] text-sienna mb-2">{error}</p>
        <button
          onClick={refresh}
          className="text-[12px] text-cinnabar hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  const isEmpty =
    topics.covered.length === 0 &&
    topics.thin.length === 0 &&
    topics.open_gaps.length === 0;

  if (isEmpty) {
    return (
      <div className="rounded-xl border border-hairline bg-surface p-5">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-3">
          topic territory
        </div>
        <div className="flex items-center gap-2 text-mist">
          <Target size={15} weight="regular" />
          <p className="text-[13px]">
            No topic data yet. As you generate ideas and process sources, your
            topic territory will appear here.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-hairline bg-surface p-5">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.22em] text-mist mb-4">
        topic territory
      </div>
      <div className="space-y-4">
        {topics.covered.length > 0 && (
          <div>
            <div className="text-[12px] text-white font-medium mb-2 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
              Covered
              <span className="font-mono text-[11px] text-mist">
                (3+ uses)
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {topics.covered.map((t) => (
                <TagChip key={t.tag} t={t} tone="green" />
              ))}
            </div>
          </div>
        )}
        {topics.thin.length > 0 && (
          <div>
            <div className="text-[12px] text-white font-medium mb-2 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              Thin coverage
              <span className="font-mono text-[11px] text-mist">
                (1-2 uses)
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {topics.thin.map((t) => (
                <TagChip key={t.tag} t={t} tone="amber" />
              ))}
            </div>
          </div>
        )}
        {topics.open_gaps.length > 0 && (
          <div>
            <div className="text-[12px] text-white font-medium mb-2 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-cinnabar" />
              Open gaps
              <span className="font-mono text-[11px] text-mist">
                (unused tags)
              </span>
            </div>
            <ul className="space-y-1">
              {topics.open_gaps.map((gap) => (
                <li key={gap} className="flex items-center justify-between">
                  <code className="font-mono text-[12px] text-mist">{gap}</code>
                  <Link
                    to={`/make?topic=${encodeURIComponent(gap)}`}
                    className="inline-flex items-center gap-1 text-[11.5px] text-cinnabar hover:underline"
                  >
                    Make a video about this
                    <ArrowRight size={11} weight="bold" />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="mt-5 pt-4 border-t border-hairline">
        <Link
          to="/settings"
          className="text-[12px] text-mist hover:text-white transition-colors"
        >
          Manage brands in settings →
        </Link>
      </div>
    </div>
  );
}

function TagChip({
  t,
  tone,
}: {
  t: TagCount;
  tone: "green" | "amber";
}) {
  const color =
    tone === "green"
      ? "text-green-400 bg-green-500/10 border-green-500/20"
      : "text-amber-400 bg-amber-500/10 border-amber-500/20";
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-[11px] border rounded px-2 py-0.5 ${color}`}
    >
      {t.tag}
      <span className="opacity-60">{t.count}</span>
    </span>
  );
}
