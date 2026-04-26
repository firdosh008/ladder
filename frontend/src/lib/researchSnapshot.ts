/**
 * Per-idea research snapshot stored in sessionStorage.
 *
 * When the user picks a draft from the /make research panel, we snapshot
 * the topic + scraped sources + queries keyed by the new idea's UUID. The
 * Studio page (/studio/:id) reads this back so the founder can verify what
 * was actually scraped (Reddit posts, YouTube vids, X tweets) rather than
 * staring at an LLM rationale alone.
 *
 * Sources are NOT yet persisted server-side — that would require a JSONB
 * column on `studio_sessions` or a new `research_sources` table. For now
 * sessionStorage is enough for the same-session flow (make → studio in one
 * tab). If the user opens studio in a fresh tab the source rail just shows
 * an empty state, which is honest.
 */

import type { Source } from "./agents";

const PREFIX = "ladder:research:idea:";
const VERSION = 1;

export type IdeaResearchSnapshot = {
  v: number;
  ideaId: string;
  topic: string;
  sources: Source[];
  queries: string[];
  costUsd: number | null;
  capturedAt: number;
};

function keyFor(ideaId: string): string {
  return `${PREFIX}${ideaId}`;
}

export function writeIdeaResearchSnapshot(snapshot: {
  ideaId: string;
  topic: string;
  sources: Source[];
  queries: string[];
  costUsd: number | null;
}): void {
  if (typeof window === "undefined") return;
  if (!snapshot.ideaId) return;
  try {
    const payload: IdeaResearchSnapshot = {
      v: VERSION,
      ideaId: snapshot.ideaId,
      topic: snapshot.topic,
      sources: snapshot.sources,
      queries: snapshot.queries,
      costUsd: snapshot.costUsd,
      capturedAt: Date.now(),
    };
    window.sessionStorage.setItem(keyFor(snapshot.ideaId), JSON.stringify(payload));
  } catch {
    /* sessionStorage may be full or disabled — best-effort only */
  }
}

export function readIdeaResearchSnapshot(
  ideaId: string,
): IdeaResearchSnapshot | null {
  if (typeof window === "undefined") return null;
  if (!ideaId) return null;
  try {
    const raw = window.sessionStorage.getItem(keyFor(ideaId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as IdeaResearchSnapshot;
    if (parsed.v !== VERSION) return null;
    if (!Array.isArray(parsed.sources)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function clearIdeaResearchSnapshot(ideaId: string): void {
  if (typeof window === "undefined") return;
  if (!ideaId) return;
  window.sessionStorage.removeItem(keyFor(ideaId));
}
