from __future__ import annotations
# ruff: noqa: E402

import json
import os
import pathlib
import socket
from contextlib import asynccontextmanager

# Ensure localhost connections bypass any system HTTP proxy (e.g. Clash, V2Ray).
# Must be set before any library (litellm, httpx, etc.) reads proxy env vars.
_no_proxy = set(filter(None, os.environ.get("NO_PROXY", os.environ.get("no_proxy", "")).split(",")))
_no_proxy.update(["localhost", "127.0.0.1", "::1"])
os.environ["NO_PROXY"] = ",".join(sorted(_no_proxy))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from backend.app.core.config import settings
from backend.app.core.access_key import access_key_required, is_request_authorized
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
    setup_logging(log_dir=settings.LOG_DIR)

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

# Access key protection (optional — only active when ACCESS_KEY env var is set)
_EXEMPT_PATHS = {"/api/health"}

class AccessKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not access_key_required():
            return await call_next(request)
        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)
        # For HTTP requests, only accept header-based access key to avoid
        # leaking secrets in URLs/logs. Query-param auth remains for WebSocket.
        if not is_request_authorized(request.headers, None):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

app.add_middleware(AccessKeyMiddleware)

# Routers
from backend.app.api.characters import router as characters_router  # noqa: E402
from backend.app.api.archive import router as archive_router  # noqa: E402
from backend.app.api.chat import router as chat_router  # noqa: E402
from backend.app.api.debug_log import router as debug_log_router  # noqa: E402
from backend.app.api.events import router as events_router  # noqa: E402
from backend.app.api.llm_profiles import router as llm_profiles_router  # noqa: E402
from backend.app.api.plugins import router as plugins_router  # noqa: E402
from backend.app.api.projects import router as projects_router  # noqa: E402
from backend.app.api.runtime_settings import router as runtime_settings_router  # noqa: E402
from backend.app.api.scenes import router as scenes_router  # noqa: E402
from backend.app.api.sessions import router as sessions_router  # noqa: E402
from backend.app.api.novel import router as novel_router  # noqa: E402
from backend.app.api.templates import router as templates_router  # noqa: E402
from backend.app.api.model_info import router as model_info_router  # noqa: E402
from backend.app.api.plugin_invoke import router as plugin_invoke_router  # noqa: E402

app.include_router(projects_router)
app.include_router(sessions_router)
app.include_router(chat_router)
app.include_router(debug_log_router)
app.include_router(archive_router)
app.include_router(plugins_router)
app.include_router(characters_router)
app.include_router(scenes_router)
app.include_router(events_router)
app.include_router(llm_profiles_router)
app.include_router(templates_router)
app.include_router(novel_router)
app.include_router(runtime_settings_router)
app.include_router(model_info_router)
app.include_router(plugin_invoke_router)


@app.get("/api/health")
async def health_check():
    import os
    running_on_vercel = bool(os.getenv("VERCEL"))
    db_url = settings.DATABASE_URL or ""
    storage_persistent = not (running_on_vercel and "sqlite" in db_url)
    return {
        "status": "ok",
        "storage_persistent": storage_persistent,
        "auth_required": bool(settings.ACCESS_KEY),
    }


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


@app.post("/api/llm/test")
async def test_llm(
    x_llm_model: str | None = __import__("fastapi").Header(default=None),
    x_llm_api_key: str | None = __import__("fastapi").Header(default=None),
    x_llm_api_base: str | None = __import__("fastapi").Header(default=None),
):
    """Send a short test message to verify LLM connectivity."""
    import time
    from backend.app.core.llm_gateway import completion

    messages = [{"role": "user", "content": "Hi, I am testing. Please reply with just 'ok'."}]
    start = time.monotonic()
    try:
        reply = await completion(
            messages, stream=False,
            model=x_llm_model, api_key=x_llm_api_key, api_base=x_llm_api_base,
        )
        latency_ms = round((time.monotonic() - start) * 1000)
        return {"ok": True, "reply": reply, "latency_ms": latency_ms}
    except Exception as e:
        latency_ms = round((time.monotonic() - start) * 1000)
        return JSONResponse(
            status_code=502,
            content={"ok": False, "error": str(e), "latency_ms": latency_ms},
        )


# Mount frontend static files (production build) if available
_frontend_dist = pathlib.Path("frontend/dist")
if _frontend_dist.is_dir():
    app.mount(
        "/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend"
    )
