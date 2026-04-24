import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

export type Idea = {
  id: string;
  user_id: string;
  project_id: string | null;
  title: string;
  body: string | null;
  idea_type: string | null;
  status: string;
  opportunity_score: number | null;
  outlier_score: number | null;
  rationale: string | null;
  source_type: string;
  source_id: string | null;
  source_content: string | null;
  source_content_url: string | null;
  position: number | null;
  created_at: string;
  updated_at: string;
};

export type IdeaCreate = {
  title: string;
  body?: string;
  idea_type?: string;
  status?: string;
  opportunity_score?: number;
  rationale?: string;
  source_type?: string;
  source_content?: string;
  source_content_url?: string;
  project_id?: string;
  position?: number;
};

export type IdeaUpdate = Partial<
  Pick<
    Idea,
    | "title"
    | "body"
    | "idea_type"
    | "status"
    | "opportunity_score"
    | "rationale"
    | "project_id"
    | "position"
  >
>;

export function useIdeas(params: { status?: string } = {}) {
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchIdeas = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = params.status ? `?status=${encodeURIComponent(params.status)}` : "";
      const r = await api.get<{ ideas: Idea[] }>(`/ideas${qs}`);
      setIdeas(r.ideas);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load ideas");
    } finally {
      setLoading(false);
    }
  }, [params.status]);

  useEffect(() => {
    void fetchIdeas();
  }, [fetchIdeas]);

  const createIdea = useCallback(async (payload: IdeaCreate): Promise<Idea> => {
    const r = await api.post<{ idea: Idea }>("/ideas", payload);
    setIdeas((prev) => [r.idea, ...prev]);
    return r.idea;
  }, []);

  const updateIdea = useCallback(async (id: string, patch: IdeaUpdate): Promise<Idea> => {
    const r = await api.patch<{ idea: Idea }>(`/ideas/${id}`, patch);
    setIdeas((prev) => prev.map((i) => (i.id === id ? r.idea : i)));
    return r.idea;
  }, []);

  /** Apply a patch to local state immediately without calling the server.
   *  Use before `updateIdea` to make UI feel instant; on error, `refresh()`. */
  const patchLocal = useCallback((id: string, patch: IdeaUpdate) => {
    setIdeas((prev) => prev.map((i) => (i.id === id ? { ...i, ...patch } : i)));
  }, []);

  const deleteIdea = useCallback(async (id: string): Promise<void> => {
    await api.delete<void>(`/ideas/${id}`);
    setIdeas((prev) => prev.filter((i) => i.id !== id));
  }, []);

  return {
    ideas,
    loading,
    error,
    refresh: fetchIdeas,
    createIdea,
    updateIdea,
    deleteIdea,
    patchLocal,
  };
}
