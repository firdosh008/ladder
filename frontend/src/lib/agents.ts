/**
 * Client for the /ws/agents/* WebSocket endpoints.
 *
 * Three streams today:
 *   runResearchStream  — /ws/agents/research?token&topic
 *   runStudioStream    — /ws/agents/studio?token&idea_id&duration
 *   runExtractStream   — /ws/agents/extract (source posted as 1st WS msg)
 *
 * All three speak the same AgentEvent protocol. Research drafts are NOT
 * auto-persisted; Studio + Extract DO persist (artifacts + idea row) and
 * emit a `persisted` event with the new ids.
 */

import { supabase } from "./supabase";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// ─── Shared types ─────────────────────────────────────────────────────────

export type IdeaDraft = {
  title: string;
  rationale?: string | null;
  idea_type?: "systems" | "framework" | "pitch" | "case_study" | null;
  opportunity_score?: number | null;
  outlier_score?: number | null;
  why_now?: string | null;
  suggested_tags?: string[];
};

export type Source = {
  title: string;
  url: string;
  published_date?: string | null;
  snippet?: string | null;
};

export type ScriptSection = {
  heading: string;
  duration_min: number;
  talking_points: string[];
  transition?: string | null;
};

export type Script = {
  sections: ScriptSection[];
};

export type OutlineItem = {
  number: number;
  label: string;
  beat: string;
};

export type Outline = {
  items: OutlineItem[];
};

export type ExtractedVideo = {
  title: string;
  rationale: string;
  idea_type: "systems" | "framework" | "pitch" | "case_study";
  derived_duration_min: number;
  script: Script;
  outline: Outline;
};

export type TokenUsage = {
  input: number;
  output: number;
  cost_usd: number;
};

export type AgentEvent =
  | { type: "agent_start"; agent: string }
  | {
      type: "tool_call";
      agent?: string | null;
      tool: string;
      arguments?: string;
    }
  | { type: "sources"; query: string; items: Source[] }
  | { type: "text_delta"; agent: string; content: string }
  | { type: "task_complete"; agent?: string | null; preview?: string }
  | {
      type: "ideas_ready";
      ideas: IdeaDraft[];
      token_usage?: TokenUsage;
    }
  | { type: "script_ready"; script: Script }
  | { type: "outline_ready"; outline: Outline }
  | { type: "extract_ready"; extracted: ExtractedVideo }
  | { type: "usage"; token_usage: TokenUsage }
  | {
      type: "persisted";
      idea_id?: string;
      session_id: string;
      script_artifact_id: string;
      outline_artifact_id: string;
    }
  | { type: "complete"; count?: number; cost_usd: number }
  | { type: "error"; message: string };

export type ResearchSetup = {
  topic: string;
};

// ─── WS helpers ───────────────────────────────────────────────────────────

function wsBaseUrl(): string {
  return API_URL.replace(/^http/, "ws");
}

async function authToken(): Promise<string> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("Not authenticated");
  return token;
}

type StreamResult<T> = T;

function consumeStream<T>(
  url: string,
  onEvent: (ev: AgentEvent) => void,
  finalise: (ev: AgentEvent & { type: "complete" }) => StreamResult<T>,
  initialPayload?: unknown,
): Promise<T> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const ws = new WebSocket(url);

    ws.onopen = () => {
      if (initialPayload !== undefined) {
        ws.send(JSON.stringify(initialPayload));
      }
    };

    ws.onmessage = (e) => {
      let ev: AgentEvent;
      try {
        ev = JSON.parse(e.data) as AgentEvent;
      } catch {
        return;
      }
      try {
        onEvent(ev);
      } catch {
        /* UI callback errors should not kill the stream */
      }
      if (ev.type === "complete") {
        settled = true;
        resolve(finalise(ev));
        ws.close();
      } else if (ev.type === "error") {
        settled = true;
        reject(new Error(ev.message));
        ws.close();
      }
    };

    ws.onerror = () => {
      if (!settled) {
        settled = true;
        reject(new Error("WebSocket error"));
      }
    };

    ws.onclose = (e) => {
      if (!settled) {
        settled = true;
        reject(
          new Error(
            `Stream closed unexpectedly${e.reason ? `: ${e.reason}` : ""}`,
          ),
        );
      }
    };
  });
}

// ─── runResearchStream ────────────────────────────────────────────────────

export async function runResearchStream(
  setup: ResearchSetup,
  onEvent: (ev: AgentEvent) => void,
): Promise<{ count: number; cost_usd: number }> {
  const token = await authToken();
  const params = new URLSearchParams({ token, topic: setup.topic });
  const url = `${wsBaseUrl()}/ws/agents/research?${params.toString()}`;

  return consumeStream(url, onEvent, (ev) => ({
    count: ev.count ?? 0,
    cost_usd: ev.cost_usd,
  }));
}

// ─── runStudioStream ──────────────────────────────────────────────────────

export type StudioRunResult = {
  cost_usd: number;
};

export async function runStudioStream(
  ideaId: string,
  duration: number | undefined,
  onEvent: (ev: AgentEvent) => void,
): Promise<StudioRunResult> {
  const token = await authToken();
  const params = new URLSearchParams({ token, idea_id: ideaId });
  if (duration && duration >= 3 && duration <= 60) {
    params.set("duration", String(duration));
  }
  const url = `${wsBaseUrl()}/ws/agents/studio?${params.toString()}`;

  return consumeStream(url, onEvent, (ev) => ({ cost_usd: ev.cost_usd }));
}

// ─── runExtractStream ─────────────────────────────────────────────────────

export type ExtractRunResult = {
  cost_usd: number;
};

export async function runExtractStream(
  source: { source_content: string; source_url?: string | null },
  onEvent: (ev: AgentEvent) => void,
): Promise<ExtractRunResult> {
  const token = await authToken();
  const params = new URLSearchParams({ token });
  const url = `${wsBaseUrl()}/ws/agents/extract?${params.toString()}`;

  return consumeStream(
    url,
    onEvent,
    (ev) => ({ cost_usd: ev.cost_usd }),
    {
      source_content: source.source_content,
      source_url: source.source_url ?? null,
    },
  );
}

// ─── Hydration: GET /studio-sessions/by-idea/{idea_id} ───────────────────

export type StudioHydration = {
  session: Record<string, unknown> | null;
  script: { id: string; content_json: Script; version: number } | null;
  outline: { id: string; content_json: Outline; version: number } | null;
};

export async function fetchStudioByIdea(
  ideaId: string,
): Promise<StudioHydration> {
  const token = await authToken();
  const res = await fetch(
    `${API_URL}/studio-sessions/by-idea/${encodeURIComponent(ideaId)}`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to load studio session (${res.status})`);
  }
  return (await res.json()) as StudioHydration;
}
