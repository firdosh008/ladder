-- Hybrid search RPC: vector similarity + full-text keyword search fused via
-- Reciprocal Rank Fusion (RRF, k=60).  Falls back to pure vector cosine
-- similarity when no query_text is supplied — fully backward-compatible with
-- the original v1 signature (3-arg calls).
--
-- Replaces the v1 match_knowledge_nodes defined in 20260423000004.

CREATE OR REPLACE FUNCTION match_knowledge_nodes (
  query_user_id    uuid,
  query_embedding  vector(1536),
  query_text       text DEFAULT NULL,
  match_count      int DEFAULT 8
)
RETURNS TABLE (
  id             uuid,
  content_chunk  text,
  source_type    text,
  source_id      uuid,
  similarity     float
)
LANGUAGE plpgsql STABLE
AS $$
DECLARE
  v_tsquery tsquery;
BEGIN
  -- ── Resolve the text query into a tsquery (NULL if empty / stopwords-only) ──
  IF query_text IS NOT NULL AND query_text != '' THEN
    v_tsquery := plainto_tsquery('english', query_text);
  END IF;

  -- ── Branch 1: pure vector search (no usable text query) ────────────────────
  IF v_tsquery IS NULL THEN
    RETURN QUERY
      SELECT
        kn.id,
        kn.content_chunk,
        kn.source_type,
        kn.source_id,
        1 - (kn.embedding <=> query_embedding) AS similarity
      FROM knowledge_nodes kn
      WHERE kn.user_id = query_user_id
        AND kn.deleted_at IS NULL
      ORDER BY kn.embedding <=> query_embedding
      LIMIT match_count;
    RETURN;
  END IF;

  -- ── Branch 2: hybrid search (vector + FTS fused via RRF) ───────────────────
  RETURN QUERY
    WITH vector_results AS (
      SELECT
        kn.id,
        kn.content_chunk,
        kn.source_type,
        kn.source_id,
        ROW_NUMBER() OVER (ORDER BY kn.embedding <=> query_embedding) AS rank_v
      FROM knowledge_nodes kn
      WHERE kn.user_id = query_user_id
        AND kn.deleted_at IS NULL
      ORDER BY kn.embedding <=> query_embedding
      LIMIT match_count * 3
    ),
    fts_results AS (
      SELECT
        kn.id,
        kn.content_chunk,
        kn.source_type,
        kn.source_id,
        ROW_NUMBER() OVER (
          ORDER BY ts_rank(kn.fts, v_tsquery) DESC
        ) AS rank_f
      FROM knowledge_nodes kn
      WHERE kn.user_id = query_user_id
        AND kn.deleted_at IS NULL
        AND kn.fts @@ v_tsquery
      ORDER BY ts_rank(kn.fts, v_tsquery) DESC
      LIMIT match_count * 3
    ),
    merged AS (
      SELECT
        COALESCE(v.id, f.id)                           AS id,
        COALESCE(v.content_chunk, f.content_chunk)     AS content_chunk,
        COALESCE(v.source_type, f.source_type)         AS source_type,
        COALESCE(v.source_id, f.source_id)             AS source_id,
        COALESCE(1.0 / (60.0 + v.rank_v), 0.0)
          + COALESCE(1.0 / (60.0 + f.rank_f), 0.0)     AS similarity
      FROM vector_results v
      FULL OUTER JOIN fts_results f ON v.id = f.id
    )
    SELECT m.id, m.content_chunk, m.source_type, m.source_id, m.similarity
    FROM merged m
    ORDER BY m.similarity DESC
    LIMIT match_count;
END;
$$;
