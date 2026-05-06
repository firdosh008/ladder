-- Settings tab infrastructure: API keys, model prefs, profile extensions, storage buckets.
-- PRD §8.3-8.7.

-- ── USER_PROFILES new columns ────────────────────────────────────────────────
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS avatar_storage_path text;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS theme text DEFAULT 'dark';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS font_scale text DEFAULT 'default';

-- Integration tokens (PRD §8.5)
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS notion_token text;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS gamma_api_key text;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS nano_banana_api_key text;

-- YouTube integration fields
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS youtube_channel_name text;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS youtube_subscriber_count int;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS youtube_last_sync timestamptz;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS youtube_client_id text;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS youtube_client_secret text;

-- ── API_KEYS table ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_keys (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  provider      text NOT NULL CHECK (provider IN ('anthropic','openai','google')),
  encrypted_key text NOT NULL,
  created_at    timestamptz DEFAULT now(),
  updated_at    timestamptz DEFAULT now(),
  UNIQUE(user_id, provider)
);

ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_owns_keys" ON api_keys FOR ALL USING (user_id = auth.uid());

-- ── USER_MODEL_PREFS table ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_model_prefs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  function_name text NOT NULL,
  model         text NOT NULL,
  provider      text NOT NULL,
  updated_at    timestamptz DEFAULT now(),
  UNIQUE(user_id, function_name)
);

ALTER TABLE user_model_prefs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "user_owns_prefs" ON user_model_prefs FOR ALL USING (user_id = auth.uid());

-- ── STORAGE BUCKETS ──────────────────────────────────────────────────────────
-- Avatars — private user avatars
INSERT INTO storage.buckets (id, name, public)
VALUES ('avatars', 'avatars', true)
ON CONFLICT (id) DO UPDATE SET public = EXCLUDED.public;

CREATE POLICY "avatar_owner_write"
  ON storage.objects FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "avatar_owner_update"
  ON storage.objects FOR UPDATE TO authenticated
  USING (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  )
  WITH CHECK (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "avatar_owner_delete"
  ON storage.objects FOR DELETE TO authenticated
  USING (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "avatar_public_read"
  ON storage.objects FOR SELECT TO anon, authenticated
  USING (bucket_id = 'avatars');

-- Skill files — private markdown uploads
INSERT INTO storage.buckets (id, name, public)
VALUES ('skill_files', 'skill_files', false)
ON CONFLICT (id) DO UPDATE SET public = EXCLUDED.public;

CREATE POLICY "skill_owner_write"
  ON storage.objects FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'skill_files'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "skill_owner_select"
  ON storage.objects FOR SELECT TO authenticated
  USING (
    bucket_id = 'skill_files'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "skill_owner_delete"
  ON storage.objects FOR DELETE TO authenticated
  USING (
    bucket_id = 'skill_files'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );
