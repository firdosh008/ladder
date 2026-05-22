import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

export type KnowledgeNode = {
  id: string;
  source_type: string | null;
  source_id: string | null;
  content_chunk: string;
  topic_tags: string[] | null;
  created_at: string | null;
  title: string | null;
};

export type AccumulatedEntry = {
  id: string;
  source_type: string;
  source_title: string | null;
  summary: string | null;
  created_at: string | null;
  session_id: string | null;
};

export type TagCount = { tag: string; count: number };

export type TopicTerritory = {
  covered: TagCount[];
  thin: TagCount[];
  open_gaps: string[];
};

export type Insight = {
  id: string;
  title: string;
  body: string | null;
  signal_type: string | null;
  source_ref: string | null;
  read: boolean;
  created_at: string | null;
};

export function useKnowledge(params?: { source_type?: string }) {
  const [nodes, setNodes] = useState<KnowledgeNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchNodes = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = params?.source_type
        ? `?source_type=${encodeURIComponent(params.source_type)}`
        : "";
      const r = await api.get<{ nodes: KnowledgeNode[] }>(
        `/knowledge${qs}`,
      );
      setNodes(r.nodes);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load knowledge");
    } finally {
      setLoading(false);
    }
  }, [params?.source_type]);

  useEffect(() => {
    void fetchNodes();
  }, [fetchNodes]);

  const createKnowledge = useCallback(
    async (payload: {
      title?: string;
      content_chunk: string;
      topic_tags?: string[];
    }): Promise<KnowledgeNode> => {
      const r = await api.post<KnowledgeNode>("/knowledge", payload);
      setNodes((prev) => [r, ...prev]);
      return r;
    },
    [],
  );

  const deleteKnowledge = useCallback(async (id: string): Promise<void> => {
    await api.delete<void>(`/knowledge/${encodeURIComponent(id)}`);
    setNodes((prev) => prev.filter((n) => n.id !== id));
  }, []);

  return {
    nodes,
    loading,
    error,
    refresh: fetchNodes,
    createKnowledge,
    deleteKnowledge,
  };
}

export function useAccumulated() {
  const [entries, setEntries] = useState<AccumulatedEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get<{ entries: AccumulatedEntry[] }>(
        "/knowledge/accumulated",
      );
      setEntries(r.entries);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load feed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetch();
  }, [fetch]);

  /** Remove an entry from local state (the server DELETE is on the knowledge node). */
  const removeEntry = useCallback((id: string) => {
    setEntries((prev) => prev.filter((e) => e.id !== id));
  }, []);

  return { entries, loading, error, refresh: fetch, removeEntry };
}

export function useTopics() {
  const [topics, setTopics] = useState<TopicTerritory>({
    covered: [],
    thin: [],
    open_gaps: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get<TopicTerritory>("/knowledge/topics");
      setTopics(r);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Failed to load topic territory",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetch();
  }, [fetch]);

  return { topics, loading, error, refresh: fetch };
}

export function useInsights() {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get<{ insights: Insight[] }>("/insights");
      setInsights(r.insights);
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Failed to load insights",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetch();
  }, [fetch]);

  const markRead = useCallback(async (id: string) => {
    await api.patch(`/insights/${encodeURIComponent(id)}/read`);
    setInsights((prev) =>
      prev.map((i) => (i.id === id ? { ...i, read: true } : i)),
    );
  }, []);

  const generate = useCallback(async (): Promise<Insight[]> => {
    const r = await api.post<{ insights: Insight[]; generated: number }>(
      "/insights/generate",
    );
    if (r.insights.length > 0) {
      setInsights((prev) => [...r.insights, ...prev]);
    }
    return r.insights;
  }, []);

  return { insights, loading, error, refresh: fetch, markRead, generate };
}
