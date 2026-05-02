from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str

    CORS_ORIGINS: str = "http://localhost:5173"

    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    #: Image model for scene hero thumbnails (``images.generate``).
    #: Examples: ``dall-e-3``, ``gpt-image-1``, ``gpt-image-1.5``, ``gpt-image-2``.
    OPENAI_IMAGE_MODEL: str = "dall-e-3"
    #: ``hd`` / ``standard`` for ``dall-e-3``; ``high`` / ``medium`` / ``low`` /
    #: ``auto`` for GPT image models. Aliases: ``hd`` → ``high`` on GPT models.
    OPENAI_IMAGE_QUALITY: str = "hd"
    #: Optional override, e.g. ``1024x1024``, ``1792x1024`` (dall-e-3), or a
    #: GPT image size. Empty string uses built-in defaults per model.
    OPENAI_IMAGE_SIZE: str = ""
    #: Append up to this many AI/remote thumbnails (see ``SCENE_IMAGE_PLACEMENT``).
    SCENE_AI_IMAGE_COUNT: int = Field(default=5, ge=1, le=12)
    #: When False, skip OpenAI image calls but remote URLs may still apply.
    SCENE_IMAGE_GEN_ENABLED: bool = True
    #: Comma-separated ``https://`` image URLs (PNG/JPEG/WebP/GIF, ≤2 MiB each).
    #: Fetched server-side after AI slots — handy for stock art you trust.
    SCENE_REMOTE_IMAGE_URLS: str = ""
    #: ``frame_anchor``: place each hero image inside the matching layout frame
    #: (outline order). ``canvas_bottom_strip``: legacy strip below all content.
    SCENE_IMAGE_PLACEMENT: Literal["frame_anchor", "canvas_bottom_strip"] = (
        "frame_anchor"
    )
    #: Columns in the notional slide grid used to size frame-anchored images
    #: (e.g. 4 ⇒ image width ≈ one-quarter of the frame content width).
    SCENE_IMAGE_FRAME_GRID_COLUMNS: int = Field(default=4, ge=3, le=8)
    #: Prefer landscape output when ``OPENAI_IMAGE_SIZE`` is unset (diagram /
    #: deck-friendly). DALL·E 3 → ``1792x1024``; GPT Image → ``1536x1024``.
    SCENE_IMAGE_LANDSCAPE_FOR_DIAGRAMS: bool = True
    #: Max UTF-8 JSON size for ``POST .../scene/share`` (embedded ``files`` /
    #: base64). Raised from 2 MiB — hero thumbnails inflate the envelope quickly.
    SCENE_PUBLISH_MAX_ENVELOPE_BYTES: int = Field(
        default=15 * 1024 * 1024,
        ge=512 * 1024,
        le=64 * 1024 * 1024,
    )

    GOOGLE_API_KEY: str | None = None
    EXA_API_KEY: str | None = None
    SCRAPECREATORS_API_KEY: str | None = None

    ANTHROPIC_MODEL: str = "claude-haiku-4-5"
    #: Model for the studio visual agent (Build + Sharpen flows). Sonnet 4.6
    #: gives reliable multi-turn MCP tool use + vision on screenshots.
    VISUAL_AGENT_ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    #: Max CrewAI agent iterations per visual run. The agent does
    #: batch_create + screenshot + fix loops; this caps total turns so a
    #: stuck loop can't burn an unbounded number of API calls.
    VISUAL_AGENT_MAX_ITER: int = Field(default=24, ge=4, le=80)
    #: Max critic↔drawer refine cycles per visual build before we ship
    #: whatever's on the canvas. Each cycle = one critic kickoff + (if
    #: VERDICT: FIX) one drawer kickoff with the critic's notes.
    VISUAL_REFINE_MAX_ITERS: int = Field(default=3, ge=1, le=8)

    #: Base URL where ``mcp_excalidraw`` Express canvas listens (MCP mirrors these routes).
    EXCALIDRAW_HTTP_URL: str = "http://127.0.0.1:3000"
    #: Optional override for the checkout path; blank → ``backend/vendor/mcp_excalidraw``.
    EXCALIDRAW_VENDOR_ROOT: str = ""
    #: Spawn ``node dist/server.js`` automatically on FastAPI startup when /health fails.
    EXCALIDRAW_CANVAS_AUTOSTART: bool = True
    #: Seconds to wait for ``GET /health`` after spawning Node (first ``npm run build`` on drvfs/WSL can be slow).
    EXCALIDRAW_CANVAS_HEALTH_WAIT_SECONDS: int = Field(default=240, ge=30, le=1200)
    #: Path (relative to vendor root) to the MCP stdio entry. Upstream
    #: ``yctimlin/mcp_excalidraw`` ships this at ``dist/index.js`` after
    #: ``npm run build``. Override only if upstream renames the file.
    MCP_EXCALIDRAW_ENTRY: str = "dist/index.js"

    #: Claude structured outputs compile JSON Schema to a grammar; large schemas
    #: (e.g. full ``SceneSkeleton``) routinely hit 400 "Schema is too complex"
    #: or 503 grammar-compiler-overloaded errors in practice. Default off so
    #: scene builds skip the retry storm and go straight to the prompted-JSON
    #: + Pydantic path. Flip on via env to try grammar-constrained sampling.
    SCENE_DESIGNER_STRUCTURED_OUTPUTS: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()  # type: ignore[call-arg]
