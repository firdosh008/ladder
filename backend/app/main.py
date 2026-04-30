from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routes import agents, auth, diagrams, health, ideas, studio_sessions

app = FastAPI(title="Ladder Content OS", version="0.1.0")

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
app.include_router(diagrams.router)
