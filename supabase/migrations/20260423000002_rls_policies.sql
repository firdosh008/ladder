-- Row-Level Security — every user sees only their own rows.
-- The backend never adds manual user_id filters; RLS is the guarantee.

ALTER TABLE users              ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles      ENABLE ROW LEVEL SECURITY;
ALTER TABLE brands             ENABLE ROW LEVEL SECURITY;
ALTER TABLE skill_files        ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects           ENABLE ROW LEVEL SECURITY;
ALTER TABLE ideas              ENABLE ROW LEVEL SECURITY;
ALTER TABLE studio_sessions    ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifacts          ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages      ENABLE ROW LEVEL SECURITY;
ALTER TABLE sources            ENABLE ROW LEVEL SECURITY;
ALTER TABLE newsletter_items   ENABLE ROW LEVEL SECURITY;
ALTER TABLE knowledge_nodes    ENABLE ROW LEVEL SECURITY;
ALTER TABLE yt_metrics         ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_log          ENABLE ROW LEVEL SECURITY;
ALTER TABLE tags               ENABLE ROW LEVEL SECURITY;
ALTER TABLE idea_tags          ENABLE ROW LEVEL SECURITY;

-- Standard owner policy — every user_id-scoped content table gets this shape.
CREATE POLICY "user_owns_row" ON user_profiles
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON brands
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON skill_files
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON projects
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON ideas
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON studio_sessions
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON artifacts
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON chat_messages
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON sources
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON newsletter_items
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON knowledge_nodes
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON yt_metrics
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE POLICY "user_owns_row" ON tags
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

-- users table: user reads their own row only.
CREATE POLICY "user_reads_self" ON users
  FOR SELECT USING (id = auth.uid());

-- idea_tags: ownership derived via the parent idea.
CREATE POLICY "user_owns_idea_tag" ON idea_tags
  FOR ALL USING (
    idea_id IN (SELECT id FROM ideas WHERE user_id = auth.uid())
  );

-- usage_log: user reads own. Service role writes (bypasses RLS by design).
CREATE POLICY "user_reads_own_usage" ON usage_log
  FOR SELECT USING (user_id = auth.uid());

-- Admin read-only on usage_log + users metadata. No admin policies on content tables.
CREATE POLICY "admin_reads_usage" ON usage_log
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND is_admin = true)
  );

CREATE POLICY "admin_reads_users" ON users
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM users u WHERE u.id = auth.uid() AND u.is_admin = true)
  );
