from __future__ import annotations

import re
from pathlib import Path

import frontmatter
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from pydantic import BaseModel

from backend.app.core.config import settings
from backend.app.core.llm_gateway import completion
from backend.app.core.search_replace import apply_edits, is_search_replace, parse_edits

router = APIRouter(prefix="/api/templates", tags=["templates"])
_TEMPLATE_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class WorldTemplateMeta(BaseModel):
    slug: str
    name: str
    description: str
    genre: str
    tags: list[str]
    language: str


class WorldTemplateDetail(WorldTemplateMeta):
    content: str
    raw: str


class GenerateWorldRequest(BaseModel):
    genre: str
    setting: str | None = None
    tone: str | None = None
    language: str | None = "zh"
    extra_notes: str | None = None


class GenerateWorldResponse(BaseModel):
    world_doc: str


class ReviseWorldRequest(BaseModel):
    world_doc: str
    instruction: str
    language: str | None = "zh"


class ReviseWorldResponse(BaseModel):
    world_doc: str


def _templates_dir() -> Path:
    return Path(settings.TEMPLATES_DIR)


def _safe_template_path(slug: str) -> Path:
    cleaned = str(slug or "").strip()
    if not _TEMPLATE_SLUG_RE.fullmatch(cleaned):
        raise HTTPException(status_code=400, detail="Invalid template slug")

    root = _templates_dir().resolve()
    target = (root / f"{cleaned}.md").resolve()
    if root not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid template path")
    return target


def _load_template(path: Path) -> tuple[dict, str]:
    """Load a template file and return (metadata dict, content body)."""
    post = frontmatter.load(str(path))
    return dict(post.metadata), post.content


def _lang_candidates(lang: str | None) -> list[str]:
    if not lang:
        return []
    normalized = str(lang).strip().lower()
    if not normalized:
        return []
    candidates = [normalized]
    base = normalized.replace("_", "-").split("-", 1)[0]
    if base and base not in candidates:
        candidates.append(base)
    return candidates


def _localized_text(metadata: dict, field: str, lang: str | None) -> str:
    i18n = metadata.get("i18n")
    # 1. Try exact requested language in i18n
    if isinstance(i18n, dict):
        for key in _lang_candidates(lang):
            payload = i18n.get(key)
            if isinstance(payload, dict):
                value = payload.get(field)
                if isinstance(value, str) and value.strip():
                    return value
    # 2. Fall back to root-level field (template's native language)
    fallback = metadata.get(field, "")
    if isinstance(fallback, str) and fallback.strip():
        return fallback
    # 3. Last resort: try English in i18n
    if isinstance(i18n, dict):
        en_payload = i18n.get("en")
        if isinstance(en_payload, dict):
            value = en_payload.get(field)
            if isinstance(value, str) and value.strip():
                return value
    return str(fallback) if fallback is not None else ""


def _metadata_tags(metadata: dict) -> list[str]:
    raw_tags = metadata.get("tags", [])
    if not isinstance(raw_tags, list):
        return []
    return [str(tag) for tag in raw_tags]


@router.get("/worlds", response_model=list[WorldTemplateMeta])
async def list_world_templates(lang: str | None = None):
    """List all available world templates."""
    templates_dir = _templates_dir()
    if not templates_dir.is_dir():
        return []

    result = []
    for path in sorted(templates_dir.glob("*.md")):
        try:
            metadata, _ = _load_template(path)
            result.append(
                WorldTemplateMeta(
                    slug=path.stem,
                    name=_localized_text(metadata, "name", lang) or path.stem,
                    description=_localized_text(metadata, "description", lang),
                    genre=metadata.get("genre", ""),
                    tags=_metadata_tags(metadata),
                    language=metadata.get("language", ""),
                )
            )
        except Exception:
            logger.warning(f"Failed to parse template: {path}")
            continue
    return result


@router.get("/worlds/{slug}", response_model=WorldTemplateDetail)
async def get_world_template(slug: str, lang: str | None = None):
    """Get a single world template by slug."""
    path = _safe_template_path(slug)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Template not found")

    metadata, content = _load_template(path)
    raw = path.read_text(encoding="utf-8")
    return WorldTemplateDetail(
        slug=slug,
        name=_localized_text(metadata, "name", lang) or slug,
        description=_localized_text(metadata, "description", lang),
        genre=metadata.get("genre", ""),
        tags=_metadata_tags(metadata),
        language=metadata.get("language", ""),
        content=content,
        raw=raw,
    )


@router.post("/worlds/generate", response_model=GenerateWorldResponse)
async def generate_world(
    body: GenerateWorldRequest,
    x_llm_model: str | None = Header(default=None),
    x_llm_api_key: str | None = Header(default=None),
    x_llm_api_base: str | None = Header(default=None),
):
    """Generate a world document using AI."""
    # Load WORLD-SPEC as system prompt
    spec_path = Path("docs/WORLD-SPEC.md")
    if spec_path.is_file():
        world_spec = spec_path.read_text(encoding="utf-8")
    else:
        world_spec = "Generate a detailed RPG world document in Markdown format."

    system_prompt = (
        "You are a world-building expert for tabletop RPG games. "
        "Generate a complete world document following the specification below.\n\n"
        "IMPORTANT RULES:\n"
        "- Output ONLY the Markdown world document, no explanations or wrapping.\n"
        "- Do NOT include any json:xxx block format details (e.g. json:state_update, json:event). "
        "Block formats are defined by the plugin system, not the world document.\n"
        "- The '玩法触发指引' section is REQUIRED — describe WHEN each game mechanic triggers in the world's narrative language.\n"
        "- The document MUST start with YAML frontmatter containing: name, description, genre, tags (array), language, plugins (array of recommended gameplay plugin names).\n\n"
        f"--- WORLD-SPEC ---\n{world_spec}"
    )

    user_parts = [f"Genre/Type: {body.genre}"]
    if body.setting:
        user_parts.append(f"Setting: {body.setting}")
    if body.tone:
        user_parts.append(f"Tone: {body.tone}")
    if body.language:
        user_parts.append(f"Language: {body.language}")
    if body.extra_notes:
        user_parts.append(f"Additional notes: {body.extra_notes}")

    user_prompt = "\n".join(user_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = await completion(
        messages,
        stream=True,
        model=x_llm_model,
        api_key=x_llm_api_key,
        api_base=x_llm_api_base,
    )

    async def _stream():
        async for chunk in result:
            yield chunk

    return StreamingResponse(_stream(), media_type="text/plain; charset=utf-8")


@router.post("/worlds/revise")
async def revise_world(
    body: ReviseWorldRequest,
    x_llm_model: str | None = Header(default=None),
    x_llm_api_key: str | None = Header(default=None),
    x_llm_api_base: str | None = Header(default=None),
):
    """Revise an existing world document using search/replace blocks."""
    lang = body.language or "zh"

    system_prompt = (
        "You are a world-document editor. "
        "The user provides an existing document and an edit instruction.\n\n"
        "OUTPUT FORMAT — output ONLY search/replace blocks:\n\n"
        "<<<<<<< SEARCH\n"
        "exact text from the original document\n"
        "=======\n"
        "replacement text\n"
        ">>>>>>> REPLACE\n\n"
        "RULES:\n"
        "- SEARCH text must match the original EXACTLY.\n"
        "- Include enough context in SEARCH to be unique.\n"
        "- Use MULTIPLE blocks for changes in different places.\n"
        "- To insert, use a nearby line as SEARCH anchor and include it + new content in REPLACE.\n"
        "- Do NOT output the full document.\n"
        "- Do NOT include any json:xxx blocks.\n"
        "- The document may start with YAML frontmatter (---). You can edit frontmatter fields too.\n"
        f"- Write in {lang}.\n"
    )

    user_prompt = (
        f"## Current Document\n\n{body.world_doc}\n\n"
        f"## Edit Instruction\n\n{body.instruction}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = await completion(
        messages,
        stream=True,
        model=x_llm_model,
        api_key=x_llm_api_key,
        api_base=x_llm_api_base,
    )

    full_output = ""
    async for chunk in result:
        full_output += chunk

    if not is_search_replace(full_output):
        logger.warning("LLM returned full document instead of search/replace blocks")
        return JSONResponse({"mode": "full", "world_doc": full_output, "edits": []})

    edits = parse_edits(full_output)
    revised, applied = apply_edits(body.world_doc, edits)

    if len(applied) < len(edits):
        logger.warning(f"Skipped {len(edits) - len(applied)} unmatched edits")

    return JSONResponse({
        "mode": "search_replace",
        "world_doc": revised,
        "edits": [{"old_text": e.old_text, "new_text": e.new_text} for e in applied],
    })
