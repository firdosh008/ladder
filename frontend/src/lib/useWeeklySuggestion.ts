import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { WeeklySuggestion } from "../types/videos";

export function useWeeklySuggestion() {
  const [suggestion, setSuggestion] = useState<WeeklySuggestion | null>(null);
  const [loading, setLoading] = useState(true);

  const fetch = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<WeeklySuggestion | null>("/videos/weekly-suggestions");
      setSuggestion(r);
    } catch {
      setSuggestion(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const save = useCallback(async (ideas: WeeklySuggestion["ideas"]) => {
    const r = await api.post<WeeklySuggestion>("/videos/weekly-suggestions", { ideas });
    setSuggestion(r);
    return r;
  }, []);

  const dismiss = useCallback(async () => {
    await api.post("/videos/weekly-suggestions/dismiss");
    setSuggestion((prev) => (prev ? { ...prev, dismissed: true } : null));
  }, []);

  useEffect(() => {
    void fetch();
  }, [fetch]);

  return { suggestion, loading, save, dismiss, refresh: fetch };
}
