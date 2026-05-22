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

export type SourcePlatform = "web" | "reddit" | "youtube" | "x" | "instagram" | "paa" | "hackernews" | "supadata";

/**
 * Platform-specific extras carried in `Source.meta`. Every field is optional
 * — older backend payloads will simply omit them and the renderer falls back
 * to bare URL/title chips.
 */
export type SourceMeta = {
  // common
  domain?: string | null;
  // Exa
  score?: number | null;
  // Reddit
  subreddit?: string | null;
  num_comments?: number | null;
  author?: string | null;
  // YouTube
  channel?: string | null;
  view_count_text?: string | null;
  duration?: string | null;
  video_id?: string | null;
  // X / Twitter
  handle?: string | null;
  like_count?: number | null;
  view_count?: number | null;
  reply_count?: number | null;
  retweet_count?: number | null;
  full_text?: string | null;
  // Instagram
  owner_handle?: string | null;
  owner_full_name?: string | null;
  play_count?: number | null;
  comment_count?: number | null;
  duration_sec?: number | null;
};

export type Source = {
  title: string;
  url: string;
  published_date?: string | null;
  snippet?: string | null;
  platform?: SourcePlatform;
  thumbnail?: string | null;
  meta?: SourceMeta;
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

// ─── Scene (Excalidraw) types ──────────────────────────────────────────────
// Field names are camelCase to mirror @excalidraw/excalidraw's
// `ExcalidrawElementSkeleton` shape exactly — the SceneView component hands
// `scene.elements` straight to `convertToExcalidrawElements()` with no
// translation step.

export type SceneElementType =
  | "rectangle"
  | "ellipse"
  | "diamond"
  | "text"
  | "arrow"
  | "line"
  | "image";

export type SceneElementBinding = { id: string };

export type SceneBinaryFile = {
  mimeType: string;
  id: string;
  dataURL: string;
  created?: number;
};

export type SceneSkeletonElement = {
  id: string;
  type: SceneElementType;
  x: number;
  y: number;
  width: number;
  height: number;
  text?: string | null;
  /** Bound caption on shapes — may carry its own fontFamily for Excalidraw. */
  label?: { text: string; fontFamily?: number | null } | null;
  strokeColor?: string | null;
  backgroundColor?: string | null;
  fillStyle?: "solid" | "hachure" | "cross-hatch" | null;
  strokeWidth?: number | null;
  roughness?: 0 | 1 | 2 | null;
  fontSize?: number | null;
  fontFamily?: number | null;
  fileId?: string | null;
  groupIds?: string[] | null;
  start?: SceneElementBinding | null;
  end?: SceneElementBinding | null;
};

export type Scene = {
  canvas_width: number;
  canvas_height: number;
  background_color: string;
  elements: SceneSkeletonElement[];
  notes?: string | null;
  files?: Record<string, SceneBinaryFile> | null;
};

export type TokenUsage = {
  input: number;
  output: number;
  cost_usd: number;
};

export type ThumbnailVariant = {
  artifact_id: string;
  file_url: string;
  storage_path: string;
  width: number;
  height: number;
};

export type VerdictDetail = {
  claim: {
    claim_text: string;
    claim_type: string;
    source_context: string;
    importance?: "core" | "contextual";
  };
  verdict: "verified" | "contradicted" | "unverifiable";
  confidence: number;
  source_url: string | null;
  supporting_text: string | null;
  explanation: string;
};

export type VerificationReport = {
  claims: VerdictDetail[];
  summary: {
    total: number;
    verified: number;
    contradicted: number;
    unverifiable: number;
  };
};


export type AgentEvent =
  | { type: "agent_start"; agent: string }
  | {
      type: "tool_call";
      agent?: string | null;
      name?: string;
      tool?: string;
      arguments?: any;
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
  | { type: "scene_ready"; scene: Scene }
  | {
      type: "thumbnail_ready";
      variants: ThumbnailVariant[];
    }
  | {
      type: "diagram_draft";
      phase: string;
      iteration?: number;
      element_count?: number;
    }
  | {
      type: "diagram_iteration";
      phase: string;
      iteration?: number;
      layout_hint?: string;
    }
  | { type: "diagram_complete"; iterations: number }
  | { type: "usage"; token_usage: TokenUsage }
  | {
      type: "persisted";
      idea_id?: string;
      session_id: string;
      script_artifact_id?: string;
      outline_artifact_id?: string;
      scene_artifact_id?: string;
      thumbnail_artifact_ids?: string[];
    }
  | { type: "knowledge_context"; count: number }
  | { type: "complete"; count?: number; cost_usd: number }
  | { type: "error"; message: string }
  // ── Verification events ──────────────────────────────────────────────
  | { type: "verifier_start"; agent: string; stage?: string }
  | { type: "verifier_claim_check"; stage?: string; count: number; checked: number }
  | { type: "verifier_search"; queries: string[] }
  | {
      type: "ideas_verification_ready";
      report: VerificationReport;
    }
  | {
      type: "script_verification_ready";
      report: VerificationReport;
    };

export type ResearchSetup = {
  topic: string;
  /**
   * Founder-chosen target runtime in minutes (3-60). Threaded into the
   * idea_formulator's prompt so each draft's scope matches the runtime —
   * a 5-min hot take vs a 30-min deep-dive carry very different shapes
   * even on the same trigger signal. Optional; backend defaults to 10.
   */
  duration_min?: number;
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
      } catch (err) {
        console.error("Agent event handler error:", err, ev);
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
  if (
    setup.duration_min &&
    setup.duration_min >= 3 &&
    setup.duration_min <= 60
  ) {
    params.set("duration", String(setup.duration_min));
  }
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

// ─── runSceneStream ───────────────────────────────────────────────────────

export type SceneRunResult = {
  cost_usd: number;
};

// Excalidraw built-in fontFamily integers. Anything else is dropped server-side.
const VALID_FONT_FAMILIES = new Set<number>([1, 2, 3, 5, 6, 7, 8, 9]);

export async function runSceneStream(
  sessionId: string,
  onEvent: (ev: AgentEvent) => void,
  /** Hex from Studio picker; optional # — sent so scene matches header when DB differs. */
  brandAccentHex?: string | null,
  /** Optional Excalidraw built-in fontFamily integer to apply to every text/label. */
  fontFamily?: number | null,
): Promise<SceneRunResult> {
  const token = await authToken();
  const params = new URLSearchParams({ token, session_id: sessionId });
  const raw = typeof brandAccentHex === "string" ? brandAccentHex.trim() : "";
  if (raw !== "") {
    const withoutHash = raw.startsWith("#") ? raw.slice(1) : raw;
    if (/^[0-9a-fA-F]{6}$/.test(withoutHash)) {
      params.set("brand_accent", withoutHash);
    }
  }
  if (typeof fontFamily === "number" && VALID_FONT_FAMILIES.has(fontFamily)) {
    params.set("font_family", String(fontFamily));
  }
  const url = `${wsBaseUrl()}/ws/agents/scene?${params.toString()}`;

  return consumeStream(url, onEvent, (ev) => ({ cost_usd: ev.cost_usd }));
}

// ─── publishScene ─────────────────────────────────────────────────────────

export type ScenePublishResult = {
  public_url: string;       // raw Storage URL (the .excalidraw file)
  storage_path: string;
  excalidraw_url: string;   // ready-to-share https://excalidraw.com/#url=<...>
};

/**
 * Upload a fully-inflated `.excalidraw` envelope to Storage and return both
 * the raw Storage URL (`public_url`) and the ready-to-share Excalidraw deep
 * link (`excalidraw_url`).
 */
export async function publishScene(
  sessionId: string,
  envelope: Record<string, unknown>,
): Promise<ScenePublishResult> {
  const token = await authToken();
  const res = await fetch(
    `${API_URL}/studio-sessions/${encodeURIComponent(sessionId)}/scene/share`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ envelope }),
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to publish scene (${res.status})`);
  }
  return (await res.json()) as ScenePublishResult;
}

// ─── saveOutline ──────────────────────────────────────────────────────────

export type SaveOutlineResult = {
  artifact_id: string;
  version: number;
};

/**
 * Persist a founder-edited outline as a new versioned `outline` artifact.
 * The backend mirrors the rendered text on the session row so the kanban
 * preview stays in sync.
 */
export async function saveOutline(
  sessionId: string,
  outline: Outline,
): Promise<SaveOutlineResult> {
  const token = await authToken();
  const res = await fetch(
    `${API_URL}/studio-sessions/${encodeURIComponent(sessionId)}/outline`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ outline }),
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to save outline (${res.status})`);
  }
  return (await res.json()) as SaveOutlineResult;
}

// ─── saveSceneSkeleton ────────────────────────────────────────────────────

export type SaveSceneSkeletonResult = {
  artifact_id: string;
  version: number;
};

/**
 * Persist an updated scene skeleton as a new versioned `excalidraw` artifact
 * (same storage path as the scene crew). Keeps layout; used for font swaps.
 */
export async function saveSceneSkeleton(
  sessionId: string,
  scene: Scene,
): Promise<SaveSceneSkeletonResult> {
  const token = await authToken();
  const res = await fetch(
    `${API_URL}/studio-sessions/${encodeURIComponent(sessionId)}/scene`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ scene }),
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to save scene (${res.status})`);
  }
  return (await res.json()) as SaveSceneSkeletonResult;
}

// ─── saveScript ────────────────────────────────────────────────────────────

export type SaveScriptResult = {
  artifact_id: string;
  version: number;
};

/**
 * Persist an AI-patched script as a new versioned ``script`` artifact.
 */
export async function saveScript(
  sessionId: string,
  script: Script,
): Promise<SaveScriptResult> {
  const token = await authToken();
  const res = await fetch(
    `${API_URL}/studio-sessions/${encodeURIComponent(sessionId)}/script`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ script }),
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to save script (${res.status})`);
  }
  return (await res.json()) as SaveScriptResult;
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

// ─── Scene & Script patching utilities ──────────────────────────────────────

export type ScenePatch = {
  upsert_elements: SceneSkeletonElement[];
  remove_element_ids: string[];
};

/**
 * Apply an AI-generated patch to a Scene, returning a new Scene object.
 * - Elements whose IDs appear in `remove_element_ids` are dropped.
 * - Elements in `upsert_elements` replace any existing element with the same id,
 *   or are appended if no existing element matches.
 */
export function applyScenePatch(scene: Scene, patch: ScenePatch): Scene {
  const removeIds = new Set(patch.remove_element_ids ?? []);
  const upserts = patch.upsert_elements ?? [];

  const upsertIdMap = new Map<string, SceneSkeletonElement>();
  for (const el of upserts) {
    if (el?.id) upsertIdMap.set(el.id, el);
  }

  const elements = scene.elements
    .filter((el) => !removeIds.has(el.id) && !upsertIdMap.has(el.id))
    .concat(upserts);

  return { ...scene, elements };
}

export type ScriptPatch = {
  section_index: number;
  new_section: ScriptSection;
};

/**
 * Replace a single script section at the given index.
 */
export function applyScriptPatch(script: Script, patch: ScriptPatch): Script {
  const sections = [...script.sections];
  if (patch.section_index >= 0 && patch.section_index < sections.length) {
    sections[patch.section_index] = patch.new_section;
  }
  return { ...script, sections };
}

/**
 * Insert a new script section at the given index, shifting later sections down.
 */
export function insertScriptSection(script: Script, index: number, section: ScriptSection): Script {
  const sections = [...script.sections];
  sections.splice(index, 0, section);
  return { ...script, sections };
}

/**
 * Remove a script section at the given index.
 */
export function removeScriptSection(script: Script, index: number): Script {
  const sections = [...script.sections];
  sections.splice(index, 1);
  return { ...script, sections };
}

export type OutlinePatch = {
  item_index: number;
  new_item: OutlineItem;
};

/**
 * Replace a single outline item at the given index.
 */
export function applyOutlinePatch(outline: Outline, patch: OutlinePatch): Outline {
  const items = [...outline.items];
  if (patch.item_index >= 0 && patch.item_index < items.length) {
    items[patch.item_index] = patch.new_item;
  }
  return { ...outline, items };
}

/**
 * Insert a new outline item at the given index, shifting later items down.
 */
export function insertOutlineItem(outline: Outline, index: number, item: OutlineItem): Outline {
  const items = [...outline.items];
  items.splice(index, 0, item);
  return { ...outline, items };
}

/**
 * Remove an outline item at the given index.
 */
export function removeOutlineItem(outline: Outline, index: number): Outline {
  const items = [...outline.items];
  items.splice(index, 1);
  return { ...outline, items };
}

// ─── PATCH /studio-sessions/{session_id} ─────────────────────────────────

export type StudioSessionPatch = {
  brand_color?: string | null;
  brand_id?: string | null;
};

export type StudioSessionPatchResult = {
  id: string;
  brand_color: string | null;
  brand_id: string | null;
};

/**
 * Patch session-level fields (`brand_color`, `brand_id`). Each key is
 * optional; omit a key to leave that column unchanged. Used by the studio
 * header brand picker and accent color for the scene designer.
 */
export async function patchStudioSession(
  sessionId: string,
  patch: StudioSessionPatch,
): Promise<StudioSessionPatchResult> {
  const token = await authToken();
  const res = await fetch(
    `${API_URL}/studio-sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(patch),
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to update studio session (${res.status})`);
  }
  return (await res.json()) as StudioSessionPatchResult;
}

// ─── Hydration: GET /studio-sessions/by-idea/{idea_id} ───────────────────

export type HydratedThumbnail = {
  id: string;
  file_url: string | null;
  storage_path: string | null;
  content_json: Record<string, unknown> | null;
  version: number;
};

export type StudioHydration = {
  session: Record<string, unknown> | null;
  script: { id: string; content_json: Script; version: number } | null;
  outline: { id: string; content_json: Outline; version: number } | null;
  scene: { id: string; content_json: Scene; version: number } | null;
  thumbnails: HydratedThumbnail[] | null;
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

// ─── Chat ─────────────────────────────────────────────────────────────────

export type ChatHistory = {
  messages: Array<{
    id: string;
    role: "user" | "assistant";
    content: string;
    has_image: boolean;
    image_storage_path?: string | null;
    applied: boolean;
    created_at: string;
  }>;
};

export async function fetchChatHistory(sessionId: string): Promise<ChatHistory> {
  const token = await authToken();
  const res = await fetch(
    `${API_URL}/studio-sessions/${encodeURIComponent(sessionId)}/chat`,
    {
      headers: { Authorization: `Bearer ${token}` },
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to load chat history (${res.status})`);
  }
  return (await res.json()) as ChatHistory;
}

export type ChatRunResult = {
  cost_usd: number;
};

export async function runChatStream(
  sessionId: string,
  payload: {
    message: string;
    mode: string;
    image_base64?: string | null;
    skill?: string | null;
  },
  onEvent: (ev: AgentEvent) => void,
): Promise<ChatRunResult> {
  const token = await authToken();
  const params = new URLSearchParams({ token, session_id: sessionId });
  const url = `${wsBaseUrl()}/ws/agents/chat?${params.toString()}`;

  return consumeStream(
    url,
    onEvent,
    (ev) => ({ cost_usd: ev.cost_usd }),
    payload,
  );
}

// ─── runThumbnailStream ─────────────────────────────────────────────────────

export type ThumbnailRunResult = {
  cost_usd: number;
  variants: ThumbnailVariant[];
};

export async function runThumbnailStream(
  sessionId: string,
  referenceUrl: string | null | undefined,
  onEvent: (ev: AgentEvent) => void,
): Promise<ThumbnailRunResult> {
  const token = await authToken();
  const params = new URLSearchParams({ token, session_id: sessionId });
  if (referenceUrl?.trim()) {
    params.set("reference_url", referenceUrl.trim());
  }
  const url = `${wsBaseUrl()}/ws/agents/thumbnail?${params.toString()}`;

  let variants: ThumbnailVariant[] = [];

  return consumeStream(
    url,
    (ev) => {
      if (ev.type === "thumbnail_ready") {
        variants = ev.variants;
      }
      onEvent(ev);
    },
    (ev) => ({ cost_usd: ev.cost_usd, variants }),
  );
}

// ─── selectThumbnail ────────────────────────────────────────────────────────

export type SelectThumbnailResult = {
  thumbnail_selected_id: string | null;
};

export async function selectThumbnail(
  sessionId: string,
  artifactId: string,
): Promise<SelectThumbnailResult> {
  const token = await authToken();
  const res = await fetch(
    `${API_URL}/studio-sessions/${encodeURIComponent(sessionId)}/thumbnail/select`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ artifact_id: artifactId }),
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to select thumbnail (${res.status})`);
  }
  return (await res.json()) as SelectThumbnailResult;
}

// ─── refineThumbnail ────────────────────────────────────────────────────────

export type RefineThumbnailResult = {
  artifact_id: string;
  file_url: string;
  storage_path: string;
  width: number;
  height: number;
};

export async function refineThumbnail(
  sessionId: string,
  artifactId: string,
  instruction: string,
): Promise<RefineThumbnailResult> {
  const token = await authToken();
  const res = await fetch(
    `${API_URL}/studio-sessions/${encodeURIComponent(sessionId)}/thumbnail/refine`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ artifact_id: artifactId, instruction }),
    },
  );
  if (!res.ok) {
    throw new Error(`Failed to refine thumbnail (${res.status})`);
  }
  return (await res.json()) as RefineThumbnailResult;
}
