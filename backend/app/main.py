import os
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
import app.models  # noqa: F401 — register all models with Base metadata


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Create all database tables on startup
    Base.metadata.create_all(bind=engine)

    # Ensure upload directory exists (only needed for local storage)
    if not settings.R2_ACCOUNT_ID:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    yield


app = FastAPI(
    title="Auto-Interview API",
    description="Backend API for the auto-interview platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware — allow all origins for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and register routers
from app.routers import auth, projects, links, interview, export, audio, research_assistant, analysis

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(links.router)
app.include_router(interview.router)
app.include_router(export.router)
app.include_router(audio.router)
app.include_router(research_assistant.router)
app.include_router(analysis.router)


@app.get("/", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "auto-interview-api"}
