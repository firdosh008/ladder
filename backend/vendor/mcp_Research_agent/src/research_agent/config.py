"""Configuration — loads from env, provides defaults, exposes typed settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """All config loaded from .env / environment variables."""

    # --- LLM Providers ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    # --- Search / Scraping ---
    tavily_api_key: str = ""
    exa_api_key: str = ""
    scrape_creators_api_key: str = ""
    dataforseo_login: str = ""
    dataforseo_password: str = ""
    supadata_api_key: str = ""
    supadata_transcript_mode: str = "native"
    apify_api_key: str = ""
    apify_youtube_comments_actor: str = "apify/youtube-comments-scraper"
    youtube_comments_provider: str = "apify"
    youtube_api_key: str = ""

    # --- Storage (Supabase HTTPS client; no direct Postgres sockets) ---
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    # database_url is removed (Supabase HTTPS is used)
    redis_url: str = ""
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""

    # --- Observability ---
    langsmith_api_key: str = ""
    langsmith_project: str = "ladder-research-agent"

    # --- Cost / Alerting ---
    slack_webhook_url: str = ""
    max_cost_per_run: float = 3.0
    max_daily_spend: float = 50.0

    # --- Rollout / Migration ---
    unified_agent_enabled_ladderflow: bool = True
    unified_agent_enabled_ladderbrief: bool = True
    shadow_mode_enabled: bool = False
    legacy_research_endpoint: str = ""

    # --- Model routing ---
    synthesis_model: str = "claude-sonnet-4-20250514"
    summarization_model: str = "claude-haiku-4-5-20251001"
    classification_model: str = "gemini-2.5-flash-preview-04-17"
    embedding_model: str = "text-embedding-3-small"

    # --- Agent defaults ---
    max_sources_per_agent: int = 15
    comment_fetch_limit: int = 50
    comment_cluster_k: int = 8
    paa_cache_ttl_hours: int = 72
    search_cache_ttl_hours: int = 24

    # --- Quality gates ---
    reddit_min_score: int = 10
    reddit_max_age_days: int = 28
    reddit_allowed_subreddits: str = ""
    youtube_min_views: int = 5000
    youtube_max_age_days: int = 90
    hn_min_points: int = 5
    hn_max_age_days: int = 28
    min_platforms_for_corroboration: int = 2

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Singleton
settings = Settings()
