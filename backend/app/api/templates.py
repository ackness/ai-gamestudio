from __future__ import annotations

from pathlib import Path

import frontmatter
from fastapi import APIRouter, Header, HTTPException
from loguru import logger
from pydantic import BaseModel

from backend.app.core.config import settings
from backend.app.core.llm_gateway import completion

router = APIRouter(prefix="/api/templates", tags=["templates"])


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


def _templates_dir() -> Path:
    return Path(settings.TEMPLATES_DIR)


def _load_template(path: Path) -> tuple[dict, str]:
    """Load a template file and return (metadata dict, content body)."""
    post = frontmatter.load(str(path))
    return dict(post.metadata), post.content


@router.get("/worlds", response_model=list[WorldTemplateMeta])
async def list_world_templates():
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
                    name=metadata.get("name", path.stem),
                    description=metadata.get("description", ""),
                    genre=metadata.get("genre", ""),
                    tags=metadata.get("tags", []),
                    language=metadata.get("language", ""),
                )
            )
        except Exception:
            logger.warning(f"Failed to parse template: {path}")
            continue
    return result


@router.get("/worlds/{slug}", response_model=WorldTemplateDetail)
async def get_world_template(slug: str):
    """Get a single world template by slug."""
    templates_dir = _templates_dir()
    path = templates_dir / f"{slug}.md"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Template not found")

    metadata, content = _load_template(path)
    raw = path.read_text(encoding="utf-8")
    return WorldTemplateDetail(
        slug=slug,
        name=metadata.get("name", slug),
        description=metadata.get("description", ""),
        genre=metadata.get("genre", ""),
        tags=metadata.get("tags", []),
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
        "- The frontmatter MUST include a 'plugins' field listing recommended gameplay plugins.\n\n"
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
        stream=False,
        model=x_llm_model,
        api_key=x_llm_api_key,
        api_base=x_llm_api_base,
    )
    return GenerateWorldResponse(world_doc=result)
