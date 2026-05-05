-- Upgrade vector index from planned ivfflat to maintenance-free HNSW,
-- and add full-text search (fts) tsvector column for hybrid retrieval.
-- Replaces the deferred 0006_vector_index.sql plan noted in supabase/README.md.

-- ── HNSW index ───────────────────────────────────────────────────────────────
-- HNSW delivers high-recall, maintenance-free vector search without the
-- training step or index degradation that ivfflat requires.
CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_embedding_hnsw
  ON knowledge_nodes
  USING hnsw (embedding vector_cosine_ops);

-- ── Full-text search vector ──────────────────────────────────────────────────
-- Stores a weighted tsvector derived from title (A-weight) and content_chunk
-- (B-weight) so keyword matches on titles rank higher than body matches.
ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS fts tsvector;

-- ── Auto-populate trigger ────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_knowledge_fts()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.fts :=
    setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(NEW.content_chunk, '')), 'B');
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_knowledge_fts ON knowledge_nodes;
CREATE TRIGGER trg_knowledge_fts
  BEFORE INSERT OR UPDATE OF title, content_chunk ON knowledge_nodes
  FOR EACH ROW EXECUTE FUNCTION update_knowledge_fts();

-- ── Backfill existing rows ───────────────────────────────────────────────────
-- Existing rows won't have fts populated until they're updated. Run a one-time
-- backfill to bring the whole table up to date.
UPDATE knowledge_nodes
   SET fts = setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
             setweight(to_tsvector('english', COALESCE(content_chunk, '')), 'B')
 WHERE fts IS NULL;

-- ── FTS index ────────────────────────────────────────────────────────────────
-- GIN index on the tsvector column for fast @@ lookups.
CREATE INDEX IF NOT EXISTS idx_knowledge_nodes_fts
  ON knowledge_nodes
  USING gin (fts);
