from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import agents, auth, health, ideas, studio_sessions, visual
from app.services import excalidraw_canvas

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
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
    except Exception as e:
        log.warning("Excalidraw canvas did not start automatically: %s", e)
    yield
    await excalidraw_canvas.stop_canvas_process()


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
app.include_router(visual.router)
