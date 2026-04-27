/**
 * Per-idea research snapshot.
 *
 * When the user picks a draft from the /make research panel, we capture
 * the topic + scraped sources + queries and persist it in TWO places:
 *
 *   1. `ideas.research_snapshot` (JSONB) on the server — survives across
 *      tabs / devices / reloads. Source of truth.
 *   2. sessionStorage — same-session cache for instant UI render before
 *      the freshly-created idea is fetched back from the server. Optional.
 *
 * The Studio panel reads (1) first and falls back to (2) so older ideas
 * created before this column existed (or ideas where the snapshot somehow
 * didn't make the round-trip) still render correctly while the user is
 * still in the same tab.
 *
 * The wire shape uses snake_case (`cost_usd`, `captured_at`) so the JSON
 * is friendly to backend tooling; frontend code converts at the edge.
 */

import type { Source } from "./agents";

const PREFIX = "ladder:research:idea:";
export const SNAPSHOT_VERSION = 1;

/** Wire shape — what gets sent to the server and stored in JSONB. */
export type IdeaResearchSnapshotPayload = {
  v: number;
  topic: string;
  sources: Source[];
  queries: string[];
  cost_usd: number | null;
  captured_at: string;
};

/** Local + Studio-render shape. Adds `ideaId` for sessionStorage keying. */
export type IdeaResearchSnapshot = IdeaResearchSnapshotPayload & {
  ideaId: string;
};

function keyFor(ideaId: string): string {
  return `${PREFIX}${ideaId}`;
}

/** Build the canonical payload sent to the server (and mirrored locally). */
export function buildSnapshotPayload(input: {
  topic: string;
  sources: Source[];
  queries: string[];
  costUsd: number | null;
}): IdeaResearchSnapshotPayload {
  return {
    v: SNAPSHOT_VERSION,
    topic: input.topic,
    sources: input.sources,
    queries: input.queries,
    cost_usd: input.costUsd,
    captured_at: new Date().toISOString(),
  };
}

/** Validate + normalise a payload coming back from the server (or storage). */
export function normaliseSnapshot(
  raw: unknown,
  ideaId: string,
): IdeaResearchSnapshot | null {
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Partial<IdeaResearchSnapshotPayload>;
  if (obj.v !== SNAPSHOT_VERSION) return null;
  if (!Array.isArray(obj.sources)) return null;
  return {
    v: obj.v,
    ideaId,
    topic: typeof obj.topic === "string" ? obj.topic : "",
    sources: obj.sources as Source[],
    queries: Array.isArray(obj.queries) ? (obj.queries as string[]) : [],
    cost_usd: typeof obj.cost_usd === "number" ? obj.cost_usd : null,
    captured_at: typeof obj.captured_at === "string" ? obj.captured_at : "",
  };
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
      ...buildSnapshotPayload(snapshot),
      ideaId: snapshot.ideaId,
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
    return normaliseSnapshot(JSON.parse(raw), ideaId);
  } catch {
    return null;
  }
}

export function clearIdeaResearchSnapshot(ideaId: string): void {
  if (typeof window === "undefined") return;
  if (!ideaId) return;
  window.sessionStorage.removeItem(keyFor(ideaId));
}
