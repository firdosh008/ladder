-- Videos page: archived flags, weekly suggestions, and performance indexes.

ALTER TABLE ideas ADD COLUMN IF NOT EXISTS archived boolean DEFAULT false;
ALTER TABLE studio_sessions ADD COLUMN IF NOT EXISTS archived boolean DEFAULT false;

-- Weekly AI suggestion block (refreshes every Monday).
CREATE TABLE IF NOT EXISTS weekly_suggestions (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
    week_start   date NOT NULL,
    ideas        jsonb NOT NULL,
    dismissed    boolean DEFAULT false,
    generated_at timestamptz DEFAULT now(),
    UNIQUE(user_id, week_start)
);

ALTER TABLE weekly_suggestions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "user_owns_weekly_suggestions" ON weekly_suggestions
    FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

-- Indexes for the kanban queries in /videos/kanban.
CREATE INDEX IF NOT EXISTS studio_sessions_user_status_idx
    ON studio_sessions(user_id, status);

CREATE INDEX IF NOT EXISTS yt_metrics_user_id_idx
    ON yt_metrics(user_id);


