from __future__ import annotations

import json
import os
import pathlib
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.core.config import settings
from backend.app.core.llm_config import get_effective_config_for_project
from backend.app.core.logging import setup_logging
from backend.app.db.engine import init_db


def _print_startup_banner(port: int) -> None:
    from loguru import logger

    in_docker = pathlib.Path("/.dockerenv").exists()
    hostname = socket.gethostname()

    lines = ["", "  AI GameStudio  "]
    if in_docker:
        # Standard Docker / docker compose port mapping
        lines.append(f"  Local   →  http://localhost:{port}")
        # OrbStack: containers are reachable at <hostname>.orb.local
        lines.append(f"  OrbStack→  http://{hostname}.orb.local")
    else:
        lines.append(f"  Dev     →  http://localhost:{port}")

    lines.append("")
    banner = "\n".join(lines)
    logger.info(banner)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Logging first so every subsequent log goes through loguru
    pathlib.Path(settings.LOG_DIR).mkdir(parents=True, exist_ok=True)
    setup_logging()

    # Ensure data/ directory exists and init DB tables
    pathlib.Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)
    await init_db()

    port = int(os.getenv("PORT", "8000"))
    _print_startup_banner(port)

    yield


app = FastAPI(title="AI GameStudio", version="0.1.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
from backend.app.api.characters import router as characters_router  # noqa: E402
from backend.app.api.archive import router as archive_router  # noqa: E402
from backend.app.api.chat import router as chat_router  # noqa: E402
from backend.app.api.events import router as events_router  # noqa: E402
from backend.app.api.llm_profiles import router as llm_profiles_router  # noqa: E402
from backend.app.api.plugins import router as plugins_router  # noqa: E402
from backend.app.api.projects import router as projects_router  # noqa: E402
from backend.app.api.runtime_settings import router as runtime_settings_router  # noqa: E402
from backend.app.api.scenes import router as scenes_router  # noqa: E402
from backend.app.api.sessions import router as sessions_router  # noqa: E402
from backend.app.api.templates import router as templates_router  # noqa: E402

app.include_router(projects_router)
app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(archive_router)
app.include_router(plugins_router)
app.include_router(characters_router)
app.include_router(scenes_router)
app.include_router(events_router)
app.include_router(llm_profiles_router)
app.include_router(templates_router)
app.include_router(runtime_settings_router)


@app.get("/api/health")
async def health_check():
    import os
    running_on_vercel = bool(os.getenv("VERCEL"))
    # SQLite in /tmp is ephemeral (Vercel serverless); any external DB URL is persistent
    db_url = settings.DATABASE_URL or ""
    storage_persistent = not (running_on_vercel and "sqlite" in db_url)
    return {"status": "ok", "storage_persistent": storage_persistent}


@app.get("/api/llm/info")
async def llm_info(project_id: str | None = None):
    """Return the effective LLM model configuration with source information.

    Args:
        project_id: Optional project ID to get project-specific configuration
    """
    from backend.app.db.engine import engine
    from sqlmodel.ext.asyncio.session import AsyncSession

    project = None
    if project_id:
        async with AsyncSession(engine) as session:
            from backend.app.models.project import Project

            project = await session.get(Project, project_id)

    config = get_effective_config_for_project(project)
    model = config.model
    # LiteLLM convention: "provider/model" or just "model" (defaults to openai)
    if "/" in model:
        provider, model_name = model.split("/", 1)
    else:
        provider, model_name = "openai", model
    return {
        "model": config.model,
        "model_name": model_name,
        "provider": provider,
        "api_base": config.api_base,
        "has_key": not config.is_empty_key(),
        "source": config.source,
    }


# Load preset models from JSON file
_PRESETS_PATH = pathlib.Path(__file__).parent / "data" / "llm_presets.json"


def _load_presets() -> list[dict]:
    """Load preset models from JSON file."""
    if _PRESETS_PATH.exists():
        return json.loads(_PRESETS_PATH.read_text()).get("presets", [])
    return []


_PRESET_MODELS = _load_presets()


@app.get("/api/llm/preset-models")
async def get_preset_models():
    """Return preset LLM models for quick selection."""
    return _PRESET_MODELS


# Mount frontend static files (production build) if available
_frontend_dist = pathlib.Path("frontend/dist")
if _frontend_dist.is_dir():
    app.mount(
        "/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend"
    )
