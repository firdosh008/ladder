-- pgvector retrieval. EVERY call must pass query_user_id — no exceptions.
-- RLS is the second layer; this explicit filter is the first and only
-- barrier when the backend uses the service role key to call this RPC.

CREATE OR REPLACE FUNCTION match_knowledge_nodes (
  query_user_id    uuid,
  query_embedding  vector(1536),
  match_count      int DEFAULT 8
)
RETURNS TABLE (
  id             uuid,
  content_chunk  text,
  source_type    text,
  source_id      uuid,
  similarity     float
)
LANGUAGE sql STABLE
AS $$
  SELECT
    id,
    content_chunk,
    source_type,
    source_id,
    1 - (embedding <=> query_embedding) AS similarity
  FROM knowledge_nodes
  WHERE user_id = query_user_id
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;
