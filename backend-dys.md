---
name: ladder-backend-db
description: Design, query, migrate, or debug the Ladder Content OS database layer — a Supabase Postgres + pgvector schema with strict per-user Row-Level Security. Use this skill whenever the user asks to create or modify tables, write migrations, add RLS policies, build or debug pgvector RAG retrieval, design SQL queries, add indexes, set up Supabase Storage buckets, write the Python (FastAPI) data-access layer, wire the cross-user isolation unit test, or touch anything under supabase/ or backend/app/rag/. Trigger this even when the user says "add a column," "write the migration," "query the ideas table," "fix the knowledge graph retrieval," "why is RLS blocking me," "set up pgvector," "add a new table for X," or references any of these tables by name: users, user_profiles, brands, skill_files, projects, ideas, studio_sessions, artifacts, chat_messages, sources, newsletter_items, knowledge_nodes, yt_metrics, usage_log, tags, idea_tags. Also trigger on "BYOK keys," "Supabase Vault," "match_knowledge_nodes," "embedding," or "usage logging." Stack: Supabase Postgres + pgvector + RLS on the data side, Python 3.11+ / FastAPI / supabase-py + pydantic on the backend side.
---

# Ladder Content OS — Backend & Database

Everything about the data layer: the 15-table schema, RLS policies, pgvector setup, the Python/FastAPI service that sits on top, and the non-negotiable rules that keep one user's data out of another user's context.

---

## Cardinal rules (these block merges)

1. **Every row in every table carries a `user_id`.** No exceptions.
2. **Every query is scoped by `auth.uid()` via RLS.** The frontend *never* adds manual `user_id` filters — if you see one, RLS is broken and needs fixing.
3. **Every pgvector retrieval includes `WHERE user_id = :uid` BEFORE the similarity search.** Enforced at the DB level (RLS) *and* the application level (explicit filter in the SQL function). Both must be in place. Belt and braces.
4. **A unit test that attempts cross-user `knowledge_nodes` retrieval must return zero results** — and must pass in CI from day one.
5. **Every Python endpoint writes to `usage_log`** with provider, model, input_tokens, output_tokens, cost_usd, latency_ms. Historical data from the first call.
6. **API keys are stored encrypted in Supabase Vault.** Never plaintext. Decrypted only server-side in Python, in-memory during the request, never logged.
7. **Admin has NO access to content tables** (`ideas`, `chat_messages`, `artifacts`, `user_profiles`, `knowledge_nodes`, `skill_files`). Admin reads `usage_log` and `users` metadata only — numbers, not content.

---

## Tables at a glance (15 total + 1 join)

| Table | Purpose |
|---|---|
| `users` | Mirrors `auth.users`, adds `is_admin`. |
| `user_profiles` | Positioning, audience, voice, creators followed, things to avoid, forwarding alias, onboarding state. |
| `brands` | User-defined content brands (name, colors, context_description). |
| `skill_files` | User-uploaded `.md` files (max 3, combined ≤50KB). |
| `projects` | Optional grouping for ideas. |
| `ideas` | The atomic unit. Title, body, type, score, rationale, source. |
| `studio_sessions` | A single video being made. Outline, excalidraw_url, status. |
| `artifacts` | Versioned outputs: script, scene_outline, excalidraw, gamma, notion, thumbnail. |
| `chat_messages` | AI chat panel messages, scoped to a studio_session. |
| `sources` | Newsletters / YouTube channels / X accounts the user has added. |
| `newsletter_items` | Raw newsletter issues received via Cloudflare Email Routing. |
| `knowledge_nodes` | **pgvector RAG store.** Per-user knowledge with 1536-dim embeddings. |
| `yt_metrics` | YouTube Data API v3 sync per video (views, CTR, watch time, outlier score). |
| `usage_log` | Every Python endpoint call with provider + model + cost. |
| `tags` | User-scoped tags. |
| `idea_tags` | Join table for many-to-many. |

---

## Full schema

Save as `supabase/migrations/0001_init.sql`. Enable the `vector` extension first:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

```sql
-- ── USERS ──────────────────────────────────────────────────────────────────
CREATE TABLE users (
  id         uuid PRIMARY KEY REFERENCES auth.users(id),
  is_admin   boolean DEFAULT false,
  created_at timestamptz DEFAULT now()
);

-- ── USER PROFILES ──────────────────────────────────────────────────────────
CREATE TABLE user_profiles (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              uuid REFERENCES users(id) UNIQUE NOT NULL,
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
  user_id              uuid REFERENCES users(id) NOT NULL,
  name                 text NOT NULL,
  primary_color        text,
  secondary_color      text,
  context_description  text,
  created_at           timestamptz DEFAULT now()
);

-- ── SKILL FILES ────────────────────────────────────────────────────────────
CREATE TABLE skill_files (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid REFERENCES users(id) NOT NULL,
  filename      text NOT NULL,
  storage_path  text NOT NULL,
  file_summary  text,
  file_size_kb  int,
  created_at    timestamptz DEFAULT now()
);

-- ── PROJECTS ───────────────────────────────────────────────────────────────
CREATE TABLE projects (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid REFERENCES users(id) NOT NULL,
  name       text NOT NULL,
  color      text,
  created_at timestamptz DEFAULT now()
);

-- ── IDEAS ──────────────────────────────────────────────────────────────────
CREATE TABLE ideas (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            uuid REFERENCES users(id) NOT NULL,
  project_id         uuid REFERENCES projects(id),
  title              text NOT NULL,
  body               text,
  idea_type          text,       -- systems|framework|pitch|case_study
  status             text DEFAULT 'new',  -- new|in_progress|completed|archived
  opportunity_score  int,
  outlier_score      numeric(5,2),
  rationale          text,
  source_type        text DEFAULT 'manual',
  source_id          uuid,
  source_content     text,       -- original pasted content (Option 3)
  source_content_url text,       -- if source was a URL
  created_at         timestamptz DEFAULT now(),
  updated_at         timestamptz DEFAULT now()
);

-- ── STUDIO SESSIONS ────────────────────────────────────────────────────────
CREATE TABLE studio_sessions (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  uuid REFERENCES users(id) NOT NULL,
  idea_id                  uuid REFERENCES ideas(id),
  topic_text               text,
  output_type              text DEFAULT 'excalidraw',
  brand_id                 uuid REFERENCES brands(id),
  target_duration_min      int DEFAULT 20,
  duration_locked          boolean DEFAULT false,
  scene_outline            text,
  outline_approved         boolean DEFAULT false,
  excalidraw_url           text,
  excalidraw_storage_path  text,
  notion_url               text,
  gamma_url                text,
  thumbnail_selected_id    uuid,
  status                   text DEFAULT 'active',  -- active|completed|archived
  created_at               timestamptz DEFAULT now(),
  updated_at               timestamptz DEFAULT now()
);

-- ── ARTIFACTS ──────────────────────────────────────────────────────────────
CREATE TABLE artifacts (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid REFERENCES users(id) NOT NULL,
  session_id    uuid REFERENCES studio_sessions(id),
  type          text NOT NULL,
  -- type ∈ script | scene_outline | excalidraw | gamma | notion | thumbnail
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
  user_id             uuid REFERENCES users(id) NOT NULL,
  session_id          uuid REFERENCES studio_sessions(id) NOT NULL,
  role                text NOT NULL,     -- user | assistant
  content             text NOT NULL,
  has_image           boolean DEFAULT false,
  image_storage_path  text,
  applied             boolean DEFAULT false,
  created_at          timestamptz DEFAULT now()
);

-- ── SOURCES ────────────────────────────────────────────────────────────────
CREATE TABLE sources (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           uuid REFERENCES users(id) NOT NULL,
  name              text NOT NULL,
  source_type       text,   -- newsletter | youtube_channel | x_account
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
  user_id       uuid REFERENCES users(id) NOT NULL,
  source_id     uuid REFERENCES sources(id) NOT NULL,
  received_at   timestamptz DEFAULT now(),
  subject       text,
  raw_text      text,
  summary       text,
  processed_at  timestamptz
);

-- ── KNOWLEDGE NODES (pgvector) ─────────────────────────────────────────────
-- CRITICAL: EVERY retrieval query must include WHERE user_id = :uid
-- BEFORE the similarity search. No exceptions.
CREATE TABLE knowledge_nodes (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid REFERENCES users(id) NOT NULL,
  source_type    text,
  -- source_type ∈ idea | chat | script | manual | yt_transcript | skill_file
  source_id      uuid,
  content_chunk  text,
  embedding      vector(1536),
  topic_tags     text[],
  created_at     timestamptz DEFAULT now()
);

-- ── YOUTUBE METRICS ────────────────────────────────────────────────────────
CREATE TABLE yt_metrics (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id             uuid REFERENCES users(id) NOT NULL,
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
  user_id        uuid REFERENCES users(id) NOT NULL,
  function_name  text,
  model          text,
  provider       text,   -- anthropic | openai | google
  input_tokens   int,
  output_tokens  int,
  cost_usd       numeric(10,6),
  latency_ms     int,
  created_at     timestamptz DEFAULT now()
);

-- ── TAGS ───────────────────────────────────────────────────────────────────
CREATE TABLE tags (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id  uuid REFERENCES users(id) NOT NULL,
  name     text NOT NULL,
  UNIQUE (user_id, name)
);

CREATE TABLE idea_tags (
  idea_id  uuid REFERENCES ideas(id),
  tag_id   uuid REFERENCES tags(id),
  PRIMARY KEY (idea_id, tag_id)
);
```

---

## Row-Level Security

Save as `supabase/migrations/0002_rls_policies.sql`.

```sql
-- Enable RLS on every content table
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

-- Standard owner policy — repeat for every user_id-scoped table
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

-- users table: user reads their own row only
CREATE POLICY "user_reads_self" ON users
  FOR SELECT USING (id = auth.uid());

-- idea_tags: ownership via idea
CREATE POLICY "user_owns_idea_tag" ON idea_tags
  FOR ALL USING (
    idea_id IN (SELECT id FROM ideas WHERE user_id = auth.uid())
  );

-- usage_log: user reads their own; admin reads all (see below)
CREATE POLICY "user_reads_own_usage" ON usage_log
  FOR SELECT USING (user_id = auth.uid());

-- Service role (backend) writes usage_log directly using service key — bypasses RLS by design.

-- Admin read-only access to usage_log and users metadata
CREATE POLICY "admin_reads_usage" ON usage_log
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM users WHERE id = auth.uid() AND is_admin = true)
  );

CREATE POLICY "admin_reads_users" ON users
  FOR SELECT USING (
    EXISTS (SELECT 1 FROM users u WHERE u.id = auth.uid() AND u.is_admin = true)
  );

-- Admin has NO access to ideas, chat_messages, artifacts, user_profiles,
-- knowledge_nodes, or skill_files. Do NOT add admin policies on those tables.
```

---

## Indexes

Save as `supabase/migrations/0003_indexes.sql`.

```sql
CREATE INDEX ON ideas            (user_id, opportunity_score DESC);
CREATE INDEX ON ideas            (user_id, status, created_at DESC);
CREATE INDEX ON studio_sessions  (user_id, status, updated_at DESC);
CREATE INDEX ON chat_messages    (session_id, created_at ASC);
CREATE INDEX ON yt_metrics       (user_id, fetched_at DESC);
CREATE INDEX ON usage_log        (user_id, created_at DESC);
CREATE INDEX ON knowledge_nodes  (user_id);
CREATE INDEX ON newsletter_items (user_id, received_at DESC);
CREATE INDEX ON artifacts        (session_id, type, version DESC);

-- Vector index — ivfflat is lighter; switch to hnsw if recall matters more than build cost.
-- Rule of thumb for ivfflat: lists = sqrt(rows). Start with 100 for small datasets.
CREATE INDEX ON knowledge_nodes
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);
```

---

## pgvector — the match RPC

The **single most important SQL object** in the whole system. Save as `supabase/migrations/0004_match_function.sql`.

```sql
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
  WHERE user_id = query_user_id      -- user filter FIRST — non-negotiable
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;
```

**Why the user filter comes first in the WHERE clause, not via RLS alone:**
- RLS on `knowledge_nodes` is the *second* layer of defense.
- But when the backend calls this RPC using the service role key (to populate agent context), RLS is bypassed by design.
- The explicit `WHERE user_id = query_user_id` is the *only* thing standing between user A's context and user B's knowledge graph in that path.
- Both layers must be in place. Remove either and you have a leak.

---

## Storage buckets

Create via Supabase Dashboard or programmatically:

| Bucket | Access | Contents |
|---|---|---|
| `excalidraw_scenes` | Private (signed URLs) | `.excalidraw` JSON files |
| `thumbnails` | Private (signed URLs) | Thumbnail PNGs |
| `skill_files` | Private | User-uploaded `.md` files — max 3 per user, ≤50KB combined |
| `avatars` | Public-read, private-write | Profile avatars |

Upload helper in Python:

```python
# app/services/storage.py
from supabase import AsyncClient

async def upload_excalidraw(supabase: AsyncClient, user_id: str,
                            session_id: str, json_bytes: bytes) -> str:
    path = f"{user_id}/{session_id}/{uuid4()}.excalidraw"
    await supabase.storage.from_("excalidraw_scenes").upload(
        path, json_bytes,
        file_options={"content-type": "application/json"},
    )
    return path
```

Always namespace object paths with `user_id` as the first segment. Makes manual cleanup and debugging far easier.

---

## Python / FastAPI layout

```
backend/
├── app/
│   ├── main.py
│   ├── config.py                   # env vars via pydantic-settings
│   ├── deps.py                     # auth dependency, supabase clients
│   ├── middleware/
│   │   ├── auth.py                 # Verify Supabase JWT → user_id
│   │   └── usage_logger.py         # Writes to usage_log after every call
│   ├── models/
│   │   ├── db.py                   # Pydantic models mirroring tables
│   │   └── responses.py            # API response shapes
│   ├── rag/
│   │   ├── embed.py                # Chunk + embed content into knowledge_nodes
│   │   └── retrieve.py             # ALWAYS filters by user_id BEFORE similarity
│   ├── services/
│   │   ├── usage.py                # Cost calc, token accounting
│   │   ├── storage.py              # Supabase Storage helpers
│   │   ├── byok.py                 # Decrypt per-user API keys from Vault
│   │   └── excalidraw.py           # JSON validation, overlap detection
│   ├── routes/
│   │   ├── agents.py               # POST /agents/*
│   │   ├── webhooks.py             # POST /webhooks/newsletter (from n8n)
│   │   └── health.py
│   └── agents/                     # Agent logic (see other skills / PRD)
├── tests/
│   ├── test_cross_user_isolation.py   # BLOCKS MERGES
│   ├── test_rag_user_filter.py
│   └── fixtures/
└── pyproject.toml
```

---

## The two Supabase clients

You will have **two** Supabase clients in the backend, and using the wrong one is a subtle but real security bug.

```python
# app/deps.py
from supabase import create_async_client, AsyncClient
from app.config import settings

# 1. Service-role client — BYPASSES RLS.
#    Used only for: writing usage_log, administrative reads, match_knowledge_nodes RPC.
_service_client: AsyncClient | None = None

async def service_client() -> AsyncClient:
    global _service_client
    if _service_client is None:
        _service_client = await create_async_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _service_client


# 2. User-scoped client — HONORS RLS using the user's JWT.
#    Used for: every read/write on behalf of a user.
async def user_client(jwt: str) -> AsyncClient:
    client = await create_async_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
    )
    await client.postgrest.auth(jwt)
    return client
```

**Rule of thumb:**
- Reading/writing user content → **user client** (RLS protects you even if you forget a filter).
- `usage_log` writes, the `match_knowledge_nodes` RPC, admin operations → **service client** (you must filter manually).

---

## The JWT auth dependency

```python
# app/middleware/auth.py
from fastapi import Header, HTTPException
from jose import jwt, JWTError
from uuid import UUID
from app.config import settings

async def current_user(authorization: str = Header(...)) -> tuple[UUID, str]:
    """Returns (user_id, raw_jwt). The raw JWT is needed to construct a user-scoped client."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = jwt.decode(
            token, settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"], audience="authenticated",
        )
    except JWTError as e:
        raise HTTPException(401, f"Invalid token: {e}")
    return UUID(payload["sub"]), token
```

Every route that touches user data:

```python
from fastapi import APIRouter, Depends

router = APIRouter()

@router.get("/ideas")
async def list_ideas(ctx=Depends(current_user)):
    user_id, jwt = ctx
    client = await user_client(jwt)
    result = await client.from_("ideas").select("*").execute()
    return result.data
```

Notice: no `.eq("user_id", user_id)`. RLS does it.

---

## pgvector retrieval — the one code path that matters most

```python
# app/rag/retrieve.py
from uuid import UUID
from app.deps import service_client
from app.providers.openai import embed_text

async def top_k_for_user(
    user_id: UUID,
    query_text: str,
    k: int = 8,
) -> list[dict]:
    """
    Fetch top-K knowledge chunks for a specific user.

    Uses the service client because we call match_knowledge_nodes as an RPC,
    which bypasses RLS — that is why the SQL function itself enforces
    `WHERE user_id = query_user_id`. Both layers are required.
    """
    embedding = await embed_text(query_text)  # OpenAI text-embedding-3-small

    sb = await service_client()
    result = await sb.rpc("match_knowledge_nodes", {
        "query_user_id": str(user_id),     # explicit, required, non-negotiable
        "query_embedding": embedding,
        "match_count": k,
    }).execute()

    return result.data
```

**If you ever write a version of this function that does not pass `query_user_id` — stop.** You have introduced the highest-severity bug the system can have.

---

## The cross-user isolation test (blocks merges)

```python
# tests/test_cross_user_isolation.py
import pytest
from uuid import uuid4
from app.rag.retrieve import top_k_for_user
from app.rag.embed import embed_and_store

pytestmark = pytest.mark.asyncio

async def test_user_cannot_retrieve_another_users_knowledge(test_db):
    user_a = uuid4()
    user_b = uuid4()

    # User A writes a distinctive knowledge node
    secret = "cinnabar-flamingo-reactor-core-42"
    await embed_and_store(
        user_id=user_a,
        content_chunk=secret,
        source_type="manual",
        source_id=None,
    )

    # User B queries for the exact secret string
    results = await top_k_for_user(user_id=user_b, query_text=secret, k=10)

    # Must return zero matches. If this test fails, the build fails.
    assert results == [], (
        f"CROSS-USER LEAK: user B retrieved user A's knowledge node. "
        f"Results: {results}"
    )


async def test_rls_blocks_direct_select_across_users(test_db, user_client_factory):
    user_a = uuid4()
    user_b = uuid4()

    # User A inserts an idea
    client_a = await user_client_factory(user_a)
    await client_a.from_("ideas").insert({
        "user_id": str(user_a),
        "title": "User A's private idea",
    }).execute()

    # User B tries to SELECT it directly
    client_b = await user_client_factory(user_b)
    result = await client_b.from_("ideas").select("*").execute()

    # RLS filters — user B sees nothing belonging to A
    assert all(r["user_id"] == str(user_b) for r in result.data)
```

Add to CI:

```yaml
# .github/workflows/backend.yml
- name: Cross-user isolation test
  run: pytest tests/test_cross_user_isolation.py -v --exitfirst
```

If this test ever fails, the merge is blocked. Period.

---

## Embedding pipeline

```python
# app/rag/embed.py
from uuid import UUID
from app.deps import service_client
from app.providers.openai import embed_text

CHUNK_SIZE = 1000   # characters
CHUNK_OVERLAP = 150

def chunk_text(text: str) -> list[str]:
    """Simple sliding-window chunker. Replace with semantic chunking later if needed."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])
        start = end - CHUNK_OVERLAP
        if end == len(text):
            break
    return chunks


async def embed_and_store(
    user_id: UUID,
    content_chunk: str,
    source_type: str,             # idea | chat | script | manual | yt_transcript | skill_file
    source_id: UUID | None,
    topic_tags: list[str] | None = None,
) -> list[UUID]:
    """Chunk, embed, and store content in knowledge_nodes. Returns inserted IDs."""
    sb = await service_client()
    inserted_ids: list[UUID] = []

    for chunk in chunk_text(content_chunk):
        embedding = await embed_text(chunk)
        result = await sb.from_("knowledge_nodes").insert({
            "user_id": str(user_id),
            "source_type": source_type,
            "source_id": str(source_id) if source_id else None,
            "content_chunk": chunk,
            "embedding": embedding,
            "topic_tags": topic_tags or [],
        }).execute()
        inserted_ids.append(UUID(result.data[0]["id"]))

    return inserted_ids
```

**When to embed:**
- After a script is finalized → chunk and embed with `source_type='script'`.
- When a user accepts/approves an idea → embed with `source_type='idea'`.
- When a user manually adds knowledge via Library → `source_type='manual'`.
- When a YouTube transcript is synced (post-MVP) → `source_type='yt_transcript'`.
- When a skill.md file is uploaded → `source_type='skill_file'`.

---

## Usage logging (required on every endpoint)

```python
# app/middleware/usage_logger.py
from dataclasses import dataclass, asdict
from time import perf_counter
from uuid import UUID
from contextlib import asynccontextmanager
from app.deps import service_client

@dataclass
class UsageEntry:
    user_id: str
    function_name: str
    model: str
    provider: str   # anthropic | openai | google
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


@asynccontextmanager
async def log_usage(user_id: UUID, function_name: str, model: str, provider: str):
    """Use as `async with log_usage(...) as entry: ...; entry.input_tokens = ...`"""
    started = perf_counter()
    entry = UsageEntry(
        user_id=str(user_id),
        function_name=function_name,
        model=model,
        provider=provider,
    )
    try:
        yield entry
    finally:
        entry.latency_ms = int((perf_counter() - started) * 1000)
        sb = await service_client()
        await sb.from_("usage_log").insert(asdict(entry)).execute()
```

Used like:

```python
async with log_usage(user_id, "stream_script", "claude-sonnet-4", "anthropic") as entry:
    response = await anthropic_client.messages.create(...)
    entry.input_tokens = response.usage.input_tokens
    entry.output_tokens = response.usage.output_tokens
    entry.cost_usd = compute_cost(
        "claude-sonnet-4",
        entry.input_tokens, entry.output_tokens,
    )
```

A unit test verifies that every endpoint under `app/routes/agents.py` uses this context manager — grep-based is fine.

---

## BYOK — per-user API keys via Supabase Vault

```python
# app/services/byok.py
from uuid import UUID
from app.deps import service_client

async def get_api_key(user_id: UUID, provider: str) -> str | None:
    """
    Fetch a decrypted API key for a user.
    Returns None if the user has not configured this provider — caller must
    fall back to the server-default key (v1 team usage) or fail explicitly.
    """
    sb = await service_client()
    result = await sb.rpc("vault_read_user_key", {
        "user_id": str(user_id),
        "provider": provider,
    }).execute()
    return result.data or None
```

The matching SQL function (reads from `vault.secrets`, scoped by user_id):

```sql
-- Provider keys stored in vault.secrets with name pattern: "{user_id}:{provider}"
CREATE OR REPLACE FUNCTION vault_read_user_key(user_id uuid, provider text)
RETURNS text
LANGUAGE sql SECURITY DEFINER
AS $$
  SELECT decrypted_secret
  FROM vault.decrypted_secrets
  WHERE name = user_id::text || ':' || provider;
$$;

-- Only the service role can call this. Revoke public execute.
REVOKE ALL ON FUNCTION vault_read_user_key(uuid, text) FROM public;
GRANT EXECUTE ON FUNCTION vault_read_user_key(uuid, text) TO service_role;
```

**Never log a decrypted key.** Never return it in an API response. It lives in memory for the duration of one request and then goes away.

---

## Pydantic models (the Python-side mirror)

```python
# app/models/db.py
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

class Idea(BaseModel):
    id: UUID
    user_id: UUID
    project_id: UUID | None = None
    title: str
    body: str | None = None
    idea_type: Literal["systems", "framework", "pitch", "case_study"] | None = None
    status: Literal["new", "in_progress", "completed", "archived"] = "new"
    opportunity_score: int | None = None
    outlier_score: float | None = None
    rationale: str | None = None
    source_type: str = "manual"
    source_id: UUID | None = None
    source_content: str | None = None
    source_content_url: str | None = None
    created_at: datetime
    updated_at: datetime


class StudioSession(BaseModel):
    id: UUID
    user_id: UUID
    idea_id: UUID | None = None
    output_type: Literal["excalidraw", "gamma", "notion"] = "excalidraw"
    brand_id: UUID | None = None
    target_duration_min: int = 20
    duration_locked: bool = False
    scene_outline: str | None = None
    outline_approved: bool = False
    excalidraw_url: str | None = None
    notion_url: str | None = None
    gamma_url: str | None = None
    thumbnail_selected_id: UUID | None = None
    status: Literal["active", "completed", "archived"] = "active"
    created_at: datetime
    updated_at: datetime


class Artifact(BaseModel):
    id: UUID
    user_id: UUID
    session_id: UUID | None = None
    type: Literal["script", "scene_outline", "excalidraw", "gamma", "notion", "thumbnail"]
    version: int = 1
    content_text: str | None = None
    content_json: dict | None = None
    file_url: str | None = None
    storage_path: str | None = None
    created_at: datetime


class UserProfile(BaseModel):
    user_id: UUID
    display_name: str | None = None
    forwarding_alias: str | None = None
    positioning: str | None = None
    audience: str | None = None
    voice: str | None = None
    creators_followed: list[str] = Field(default_factory=list)
    things_to_avoid: str | None = None
    youtube_connected: bool = False
    last_used_brand_id: UUID | None = None
    last_used_duration: int = 20
    onboarded_at: datetime | None = None


class KnowledgeNode(BaseModel):
    id: UUID
    user_id: UUID
    source_type: Literal["idea", "chat", "script", "manual", "yt_transcript", "skill_file"]
    source_id: UUID | None = None
    content_chunk: str
    topic_tags: list[str] = Field(default_factory=list)
    created_at: datetime
    # `embedding` omitted — never serialize embedding vectors to API responses
```

---

## Environment variables

```
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWT_SECRET=...

# Provider defaults (v1 — flip to full BYOK in v2)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AIza...
GAMMA_API_KEY=...
TUBELAB_API_KEY=...
NANOBANANA_API_KEY=...

# YouTube Data API v3
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...

# Webhook shared secret for n8n
N8N_WEBHOOK_SECRET=...
```

Load via `pydantic-settings`:

```python
# app/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_JWT_SECRET: str

    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    GOOGLE_API_KEY: str | None = None

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## Common query patterns

**Get current user's top ideas for the Make-a-Video picker:**
```python
client = await user_client(jwt)
result = await (
    client.from_("ideas")
    .select("id, title, rationale, opportunity_score, idea_type, source_type")
    .in_("status", ["new", "in_progress"])
    .order("opportunity_score", desc=True)
    .limit(20)
    .execute()
)
```

**Restore a studio session (all state in one round trip):**
```python
result = await (
    client.from_("studio_sessions")
    .select("""
        *,
        idea:ideas(*),
        brand:brands(*),
        artifacts(*),
        chat_messages(*)
    """)
    .eq("id", str(session_id))
    .single()
    .execute()
)
```

**Latest script version for a session:**
```python
result = await (
    client.from_("artifacts")
    .select("*")
    .eq("session_id", str(session_id))
    .eq("type", "script")
    .order("version", desc=True)
    .limit(1)
    .single()
    .execute()
)
```

**Channel summary numbers for My Videos top strip:**
```python
# Uses a Postgres view or inline aggregate — choose per preference.
result = await (
    client.from_("yt_metrics")
    .select("views.sum(), ctr.avg(), outlier_score.avg()")
    .gte("fetched_at", first_of_month())
    .execute()
)
```

---

## Supabase Realtime subscriptions

From the Next.js frontend, subscribe to:
- `studio_sessions` — so kanban cards update in real time when the Python backend changes their status.
- `ideas` — so the Ideas column and the weekly suggestion block update when `research_agent` deposits new ideas.

```ts
// frontend/lib/realtime.ts
supabase
  .channel("studio-sessions")
  .on("postgres_changes", {
    event: "UPDATE",
    schema: "public",
    table: "studio_sessions",
  }, (payload) => {
    // update kanban UI
  })
  .subscribe();
```

RLS applies to realtime too — the user only receives events for their own rows.

---

## Migration order

Run in this order:

1. `0001_init.sql` — tables (above).
2. `0002_rls_policies.sql` — enable RLS + policies.
3. `0003_indexes.sql` — B-tree indexes.
4. `0004_match_function.sql` — `match_knowledge_nodes` RPC.
5. `0005_vault_functions.sql` — `vault_read_user_key` RPC + permissions.
6. `0006_vector_index.sql` — the ivfflat index on `knowledge_nodes.embedding`. Run this **after** some data is loaded — ivfflat quality depends on training on existing vectors.

---

## Things people get wrong (checklist before PR)

- [ ] Every new table has `user_id uuid REFERENCES users(id) NOT NULL` (or ownership via a parent row for join tables).
- [ ] Every new table has `ALTER TABLE … ENABLE ROW LEVEL SECURITY` + a `user_owns_row` policy.
- [ ] No manual `user_id` filter in frontend queries (smells like broken RLS).
- [ ] Every new agent endpoint is wrapped in `log_usage(...)`.
- [ ] Every new RAG retrieval path calls a function whose SQL includes `WHERE user_id = :uid` explicitly.
- [ ] No API key, secret, or JWT appears in `usage_log.function_name`, error messages, or logs.
- [ ] New Pydantic models never include the `embedding` field in API response shapes.
- [ ] Cross-user isolation test still passes locally (`pytest tests/test_cross_user_isolation.py`).