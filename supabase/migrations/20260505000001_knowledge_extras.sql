-- Add title + soft-delete to knowledge_nodes (for manual entries + safe removal).
ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS title text;
ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

-- Curated research signals (Library > Insights tab). Populated by the
-- research agent when it identifies a signal relevant to the user's positioning.
CREATE TABLE IF NOT EXISTS insights (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  title       text NOT NULL,
  body        text,
  signal_type text,   -- trend_shift | positioning_gap | audience_signal
  source_ref  text,   -- optional URL or newsletter reference
  read        boolean DEFAULT false,
  created_at  timestamptz DEFAULT now()
);

ALTER TABLE insights ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_owns_row" ON insights
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE INDEX IF NOT EXISTS idx_insights_user_created
  ON insights (user_id, created_at DESC);

-- Filter out soft-deleted nodes from common queries (used by the backend route).
-- pgvector index still planned as migration 0006 once data exists.
