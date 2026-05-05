import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

export type Source = {
  id: string;
  name: string;
  source_type: string | null;
  sender_email: string | null;
  auto_extract: boolean;
  status: string;
  last_received_at: string | null;
  created_at: string | null;
  ideas_extracted_this_month: number;
};

export type NewsletterItem = {
  id: string;
  received_at: string | null;
  subject: string | null;
  summary: string | null;
  processed_at: string | null;
};

export function useSources() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSources = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get<{ sources: Source[] }>("/sources");
      setSources(r.sources);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load sources");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchSources();
  }, [fetchSources]);

  const createSource = useCallback(
    async (payload: {
      name: string;
      source_type?: string;
      sender_email?: string;
      auto_extract?: boolean;
    }): Promise<Source> => {
      const r = await api.post<Source>("/sources", payload);
      setSources((prev) => [r, ...prev]);
      return r;
    },
    [],
  );

  const toggleSource = useCallback(
    async (id: string, status: "active" | "paused"): Promise<void> => {
      const r = await api.patch<Source>(`/sources/${encodeURIComponent(id)}`, {
        status,
      });
      setSources((prev) =>
        prev.map((s) => (s.id === id ? { ...s, status: r.status } : s)),
      );
    },
    [],
  );

  const deleteSource = useCallback(async (id: string): Promise<void> => {
    await api.delete<void>(`/sources/${encodeURIComponent(id)}`);
    setSources((prev) => prev.filter((s) => s.id !== id));
  }, []);

  return {
    sources,
    loading,
    error,
    refresh: fetchSources,
    createSource,
    toggleSource,
    deleteSource,
  };
}

export function useSourceItems(sourceId: string | null) {
  const [items, setItems] = useState<NewsletterItem[]>([]);
  const [ideasCount, setIdeasCount] = useState(0);
  const [loading, setLoading] = useState(false);

  const fetch = useCallback(async () => {
    if (!sourceId) return;
    setLoading(true);
    try {
      const r = await api.get<{
        items: NewsletterItem[];
        ideas_extracted_this_month: number;
      }>(`/sources/${encodeURIComponent(sourceId)}/items`);
      setItems(r.items);
      setIdeasCount(r.ideas_extracted_this_month);
    } catch {
      // Silently fail — expanded row data is non-critical
      setItems([]);
      setIdeasCount(0);
    } finally {
      setLoading(false);
    }
  }, [sourceId]);

  useEffect(() => {
    void fetch();
  }, [fetch]);

  return { items, ideasCount, loading };
}
