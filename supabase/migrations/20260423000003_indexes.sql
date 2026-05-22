CREATE INDEX ON ideas            (user_id, opportunity_score DESC);
CREATE INDEX ON ideas            (user_id, status, created_at DESC);
CREATE INDEX ON studio_sessions  (user_id, status, updated_at DESC);
CREATE INDEX ON chat_messages    (session_id, created_at ASC);
CREATE INDEX ON yt_metrics       (user_id, fetched_at DESC);
CREATE INDEX ON usage_log        (user_id, created_at DESC);
CREATE INDEX ON knowledge_nodes  (user_id);
CREATE INDEX ON newsletter_items (user_id, received_at DESC);
CREATE INDEX ON artifacts        (session_id, type, version DESC);
