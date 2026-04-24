/**
 * Client for the /ws/agents/* WebSocket endpoints.
 *
 * runResearchStream opens a WS, streams events until the server emits a
 * `complete` or `error` event, then closes. Per PRD §2.1 the backend does
 * NOT persist the drafts — it delivers them via `ideas_ready` and the user
 * picks one, at which point the frontend POSTs to /ideas to save it.
 */

import { supabase } from "./supabase";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

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
      token_usage?: { input: number; output: number; cost_usd: number };
    }
  | { type: "complete"; count: number; cost_usd: number }
  | { type: "error"; message: string };

export type ResearchSetup = {
  topic: string;
};

function wsBaseUrl(): string {
  return API_URL.replace(/^http/, "ws");
}

export async function runResearchStream(
  setup: ResearchSetup,
  onEvent: (ev: AgentEvent) => void,
): Promise<{ count: number; cost_usd: number }> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("Not authenticated");

  const params = new URLSearchParams({
    token,
    topic: setup.topic,
  });

  const url = `${wsBaseUrl()}/ws/agents/research?${params.toString()}`;

  return new Promise((resolve, reject) => {
    let settled = false;
    const ws = new WebSocket(url);

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
        resolve({ count: ev.count, cost_usd: ev.cost_usd });
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
