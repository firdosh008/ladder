import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import agents, auth, health, ideas, knowledge, studio_sessions
from app.routes.diagram import router as diagram_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services import excalidraw_canvas

    vendor: Path | None = None
    raw = settings.EXCALIDRAW_VENDOR_ROOT.strip()
    if raw:
        vendor = Path(raw)

    try:
        await excalidraw_canvas.ensure_canvas_running(
            vendor=vendor,
            http_base=settings.EXCALIDRAW_HTTP_URL,
            autostart=settings.EXCALIDRAW_CANVAS_AUTOSTART,
        )
        log.info(
            "Excalidraw MCP canvas is up at %s (managed subprocess when not already running).",
            settings.EXCALIDRAW_HTTP_URL.rstrip("/"),
        )
    except Exception as e:
        log.warning(
            "Excalidraw MCP canvas did not start at API boot: %s. "
            "Start it manually or fix Node/vendor build; diagram routes will retry on demand.",
            excalidraw_canvas.boot_error_message(e),
        )

    yield

    await excalidraw_canvas.shutdown_managed_children()


app = FastAPI(title="Ladder Content OS", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(ideas.router)
app.include_router(studio_sessions.router)
app.include_router(agents.router)
app.include_router(diagram_router)
app.include_router(knowledge.router)
