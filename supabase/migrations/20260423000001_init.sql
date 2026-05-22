-- Ladder Content OS — initial schema
-- Every row in every content table carries a user_id. No exceptions.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── USERS ──────────────────────────────────────────────────────────────────
CREATE TABLE users (
  id         uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  is_admin   boolean DEFAULT false,
  created_at timestamptz DEFAULT now()
);

-- ── USER PROFILES ──────────────────────────────────────────────────────────
CREATE TABLE user_profiles (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              uuid REFERENCES users(id) ON DELETE CASCADE UNIQUE NOT NULL,
  display_name         text,
  forwarding_alias     text,
  positioning          text,
  audience             text,
  voice                text,
  creators_followed    text[],
  things_to_avoid      text,
  youtube_connected    boolean DEFAULT false,
  last_used_brand_id   uuid,
  last_used_duration   int DEFAULT 20,
  onboarded_at         timestamptz,
  updated_at           timestamptz DEFAULT now()
);

-- ── BRANDS ─────────────────────────────────────────────────────────────────
CREATE TABLE brands (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  name                 text NOT NULL,
  primary_color        text,
  secondary_color      text,
  context_description  text,
  created_at           timestamptz DEFAULT now()
);

-- ── SKILL FILES ────────────────────────────────────────────────────────────
CREATE TABLE skill_files (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  filename      text NOT NULL,
  storage_path  text NOT NULL,
  file_summary  text,
  file_size_kb  int,
  created_at    timestamptz DEFAULT now()
);

-- ── PROJECTS ───────────────────────────────────────────────────────────────
CREATE TABLE projects (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  name       text NOT NULL,
  color      text,
  created_at timestamptz DEFAULT now()
);

-- ── IDEAS ──────────────────────────────────────────────────────────────────
CREATE TABLE ideas (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  project_id         uuid REFERENCES projects(id) ON DELETE SET NULL,
  title              text NOT NULL,
  body               text,
  idea_type          text,
  status             text DEFAULT 'new',
  opportunity_score  int,
  outlier_score      numeric(5,2),
  rationale          text,
  source_type        text DEFAULT 'manual',
  source_id          uuid,
  source_content     text,
  source_content_url text,
  created_at         timestamptz DEFAULT now(),
  updated_at         timestamptz DEFAULT now()
);

-- ── STUDIO SESSIONS ────────────────────────────────────────────────────────
CREATE TABLE studio_sessions (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  idea_id                  uuid REFERENCES ideas(id) ON DELETE SET NULL,
  topic_text               text,
  output_type              text DEFAULT 'excalidraw',
  brand_id                 uuid REFERENCES brands(id) ON DELETE SET NULL,
  target_duration_min      int DEFAULT 20,
  duration_locked          boolean DEFAULT false,
  scene_outline            text,
  outline_approved         boolean DEFAULT false,
  excalidraw_url           text,
  excalidraw_storage_path  text,
  notion_url               text,
  gamma_url                text,
  thumbnail_selected_id    uuid,
  status                   text DEFAULT 'active',
  created_at               timestamptz DEFAULT now(),
  updated_at               timestamptz DEFAULT now()
);

-- ── ARTIFACTS ──────────────────────────────────────────────────────────────
CREATE TABLE artifacts (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  session_id    uuid REFERENCES studio_sessions(id) ON DELETE CASCADE,
  type          text NOT NULL,
  version       int DEFAULT 1,
  content_text  text,
  content_json  jsonb,
  file_url      text,
  storage_path  text,
  created_at    timestamptz DEFAULT now()
);

-- ── CHAT MESSAGES ──────────────────────────────────────────────────────────
CREATE TABLE chat_messages (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  session_id          uuid REFERENCES studio_sessions(id) ON DELETE CASCADE NOT NULL,
  role                text NOT NULL,
  content             text NOT NULL,
  has_image           boolean DEFAULT false,
  image_storage_path  text,
  applied             boolean DEFAULT false,
  created_at          timestamptz DEFAULT now()
);

-- ── SOURCES ────────────────────────────────────────────────────────────────
CREATE TABLE sources (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  name              text NOT NULL,
  source_type       text,
  sender_email      text,
  external_id       text,
  auto_extract      boolean DEFAULT true,
  status            text DEFAULT 'active',
  created_at        timestamptz DEFAULT now(),
  last_received_at  timestamptz
);

-- ── NEWSLETTER ITEMS ───────────────────────────────────────────────────────
CREATE TABLE newsletter_items (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  source_id     uuid REFERENCES sources(id) ON DELETE CASCADE NOT NULL,
  received_at   timestamptz DEFAULT now(),
  subject       text,
  raw_text      text,
  summary       text,
  processed_at  timestamptz
);

-- ── KNOWLEDGE NODES (pgvector) ─────────────────────────────────────────────
CREATE TABLE knowledge_nodes (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  source_type    text,
  source_id      uuid,
  content_chunk  text,
  embedding      vector(1536),
  topic_tags     text[],
  created_at     timestamptz DEFAULT now()
);

-- ── YOUTUBE METRICS ────────────────────────────────────────────────────────
CREATE TABLE yt_metrics (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  video_id            text NOT NULL,
  title               text,
  thumbnail_url       text,
  views               int,
  ctr                 numeric(5,4),
  watch_time_hrs      numeric,
  avg_duration_s      int,
  total_duration_s    int,
  subscribers_gained  int,
  outlier_score       numeric(5,2),
  what_worked         text,
  published_at        timestamptz,
  fetched_at          timestamptz DEFAULT now()
);

-- ── USAGE LOG ──────────────────────────────────────────────────────────────
CREATE TABLE usage_log (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  function_name  text,
  model          text,
  provider       text,
  input_tokens   int,
  output_tokens  int,
  cost_usd       numeric(10,6),
  latency_ms     int,
  created_at     timestamptz DEFAULT now()
);

-- ── TAGS ───────────────────────────────────────────────────────────────────
CREATE TABLE tags (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id  uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  name     text NOT NULL,
  UNIQUE (user_id, name)
);

CREATE TABLE idea_tags (
  idea_id  uuid REFERENCES ideas(id) ON DELETE CASCADE,
  tag_id   uuid REFERENCES tags(id) ON DELETE CASCADE,
  PRIMARY KEY (idea_id, tag_id)
);

-- ── AUTH BOOTSTRAP ────────────────────────────────────────────────────────
-- Every new auth.users row gets a matching public.users row automatically.
-- Without this, the first API call after signup 500s trying to satisfy FKs.
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.users (id) VALUES (NEW.id);
  INSERT INTO public.user_profiles (user_id) VALUES (NEW.id);
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();
