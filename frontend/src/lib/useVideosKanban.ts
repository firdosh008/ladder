import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";
import type { KanbanData } from "../types/videos";

export function useVideosKanban() {
  const [data, setData] = useState<KanbanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get<KanbanData>("/videos/kanban");
      setData(r);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load kanban");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetch();
  }, [fetch]);

  return { data, loading, error, refresh: fetch };
}
