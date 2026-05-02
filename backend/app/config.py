from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_EXCALIDRAW_VENDOR = _BACKEND_ROOT / "vendor" / "mcp_excalidraw"


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

    #: Claude structured outputs compile JSON Schema to a grammar; large schemas
    #: (e.g. full ``SceneSkeleton``) routinely hit 400 "Schema is too complex"
    #: or 503 grammar-compiler-overloaded errors in practice. Default off so
    #: scene builds skip the retry storm and go straight to the prompted-JSON
    #: + Pydantic path. Flip on via env to try grammar-constrained sampling.
    SCENE_DESIGNER_STRUCTURED_OUTPUTS: bool = False

    #: When True, ``/ws/agents/scene`` renders diagrams via the local MCP canvas
    #: (HTTP API + iterative vision loop) instead of the CrewAI planner +
    #: structured-output designer path.
    ENABLE_MCP_SCENE_DIAGRAM: bool = False

    #: Root directory of ``mcp_excalidraw`` (built ``dist/server.js``).
    EXCALIDRAW_VENDOR_ROOT: str = str(_DEFAULT_EXCALIDRAW_VENDOR)

    #: Canvas HTTP base URL (Express server).
    EXCALIDRAW_HTTP_URL: str = "http://127.0.0.1:3000"

    #: Spawn ``node dist/server.js`` when the canvas is unreachable.
    EXCALIDRAW_CANVAS_AUTOSTART: bool = True

    #: Seconds to wait for ``/health`` after spawning the canvas Node process.
    EXCALIDRAW_CANVAS_HEALTH_WAIT_SECONDS: int = Field(default=240, ge=30, le=1200)

    #: Spawn Playwright ``scripts/headless-canvas.mjs`` so exports work without a human browser.
    EXCALIDRAW_HEADLESS_AUTOSTART: bool = True

    #: Max seconds to wait for the headless tab to open a WebSocket (needed for PNG export).
    EXCALIDRAW_HEADLESS_CONNECT_TIMEOUT_S: float = Field(default=180.0, ge=30.0, le=600.0)

    #: Model used for diagram drafting + vision QA (needs vision capability).
    DIAGRAM_ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

    #: Max full redraw iterations (each clears canvas + new draft). Default 1 avoids triple redraws.
    DIAGRAM_MAX_ITERATIONS: int = Field(default=1, ge=1, le=8)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()  # type: ignore[call-arg]
