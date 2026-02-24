"""API route for independent plugin invocation."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from backend.app.core.game_db import GameDB
from backend.app.core.llm_config import resolve_llm_config
from backend.app.core.plugin_engine import PluginEngine
from backend.app.db.engine import get_session
from backend.app.services.plugin_agent import invoke_single_plugin

router = APIRouter()


class PluginInvokeRequest(BaseModel):
    context: dict = {}
    llm_overrides: dict | None = None


@router.post("/chat/{session_id}/plugin/{plugin_name}")
async def invoke_plugin(
    session_id: str,
    plugin_name: str,
    body: PluginInvokeRequest,
    db: SQLModelAsyncSession = Depends(get_session),
):
    pe = PluginEngine()
    game_db = GameDB(db, session_id)
    config = resolve_llm_config(overrides=body.llm_overrides)
    blocks = await invoke_single_plugin(
        plugin_name=plugin_name,
        context=body.context,
        session_id=session_id,
        game_db=game_db,
        pe=pe,
        config=config,
    )
    return {"blocks": blocks}
