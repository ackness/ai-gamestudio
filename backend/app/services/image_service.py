from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from loguru import logger

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.config import settings
from backend.app.core.secret_store import get_secret_store
from backend.app.models.project import Project
from backend.app.services.plugin_service import storage_get, storage_set
from backend.app.services.runtime_settings_service import (
    render_settings_template,
    resolve_runtime_settings,
)

STORY_IMAGE_PLUGIN = "story-image"
_MAX_STORED_IMAGES = 60
_DEFAULT_IMAGE_ENDPOINT = "https://api.whatai.cc/v1/chat/completions"
_MAX_IMAGE_REFERENCE_INPUTS = 6
_MAX_DATA_URL_CHARS = 4_500_000
_URL_RE = re.compile(r"(https?://[^\s\"'<>]+)")
_DATA_URL_RE = re.compile(r"(data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\n\r]+)")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=\n\r]+)\)")
_BASE64_RUN_RE = re.compile(r"([A-Za-z0-9+/=\n\r]{64,})")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_empty(value: str | None) -> bool:
    return value is None or value.strip() == ""


def _resolve_project_image_api_key(project: Project) -> str | None:
    store = get_secret_store()
    from_ref = store.get_secret(project.image_api_key_ref)
    if not _is_empty(from_ref):
        return from_ref
    return project.image_api_key


def _normalize_image_api_base(raw_base: str | None) -> str:
    base = (raw_base or "").strip() or _DEFAULT_IMAGE_ENDPOINT
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    if base.endswith("/v1/"):
        return f"{base}chat/completions"
    if base.endswith("/"):
        return f"{base}chat/completions"
    return f"{base}/chat/completions"


@dataclass(frozen=True)
class ResolvedImageConfig:
    model: str
    api_key: str | None
    api_base: str
    source: str  # "project" | "env" | "default"

    def has_api_key(self) -> bool:
        return not _is_empty(self.api_key)


def resolve_image_config(project: Project | None = None) -> ResolvedImageConfig:
    if project and not _is_empty(project.image_model):
        project_api_key = _resolve_project_image_api_key(project)
        return ResolvedImageConfig(
            model=project.image_model or settings.IMAGE_GEN_MODEL,
            api_key=project_api_key
            if not _is_empty(project_api_key)
            else settings.IMAGE_GEN_API_KEY,
            api_base=_normalize_image_api_base(
                project.image_api_base or settings.IMAGE_GEN_API_BASE
            ),
            source="project",
        )

    if not _is_empty(settings.IMAGE_GEN_MODEL):
        return ResolvedImageConfig(
            model=settings.IMAGE_GEN_MODEL,
            api_key=settings.IMAGE_GEN_API_KEY,
            api_base=_normalize_image_api_base(settings.IMAGE_GEN_API_BASE),
            source="env",
        )

    return ResolvedImageConfig(
        model="gemini-2.5-flash-image-preview",
        api_key=None,
        api_base=_DEFAULT_IMAGE_ENDPOINT,
        source="default",
    )


def _storage_key_for_session(session_id: str) -> str:
    return f"session:{session_id}:images"


def _truncate(text: str, limit: int = 220) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[:limit].rstrip()}..."


def _extract_world_lore_text(world_doc: str | None) -> str:
    raw = (world_doc or "").strip()
    if not raw:
        return ""

    try:
        import frontmatter as fm

        parsed = fm.loads(raw)
        cleaned = str(parsed.content or "").strip()
        return cleaned or raw
    except Exception:
        return raw


def _detect_multi_scene_mode(
    *,
    story_background: str,
    prompt: str,
    scene_frames: list[str],
    layout_preference: str | None,
) -> tuple[bool, str]:
    pref = str(layout_preference or "auto").strip().lower()
    if pref in {"comic", "comic_strip", "multi_panel"}:
        return True, "layout_preference"
    if pref in {"single", "single_frame"}:
        return False, "layout_preference"
    if len(scene_frames) >= 2:
        return True, "scene_frames"

    joined = f"{story_background}\n{prompt}"
    keywords = [
        "多场景",
        "多格",
        "分镜",
        "切换",
        "转场",
        "与此同时",
        "另一方面",
        "parallel",
        "multiple scenes",
        "scene transition",
    ]
    if any(kw in joined for kw in keywords):
        return True, "keyword"

    # Heuristic: explicit sequential cues often imply multiple beats/scenes.
    sequencing_cues = ["先", "然后", "接着", "随后", "最后", "first", "then", "after that"]
    hits = sum(1 for cue in sequencing_cues if cue in joined)
    if hits >= 2:
        return True, "sequence"

    return False, "default"


async def _build_text_world_state(
    db: AsyncSession,
    *,
    session_id: str,
) -> str:
    from backend.app.models.character import Character
    from backend.app.models.game_event import GameEvent
    from backend.app.models.message import Message
    from backend.app.models.scene import Scene
    from backend.app.models.scene_npc import SceneNPC

    parts: list[str] = []

    current_scene = (
        await db.exec(
            select(Scene).where(
                Scene.session_id == session_id,
                Scene.is_current == True,  # noqa: E712
            )
        )
    ).first()
    if current_scene:
        parts.append(
            f"Current scene: {current_scene.name}\n"
            f"Scene description: {(current_scene.description or '').strip()}"
        )
        npc_rows = list(
            (
                await db.exec(
                    select(SceneNPC).where(SceneNPC.scene_id == current_scene.id)
                )
            ).all()
        )
        if npc_rows:
            char_rows = list(
                (
                    await db.exec(
                        select(Character).where(Character.session_id == session_id)
                    )
                ).all()
            )
            name_map = {c.id: c.name for c in char_rows}
            npc_desc = []
            for npc in npc_rows:
                npc_name = name_map.get(npc.character_id, npc.character_id)
                role = f" ({npc.role_in_scene})" if npc.role_in_scene else ""
                npc_desc.append(f"{npc_name}{role}")
            parts.append("NPCs in current scene: " + ", ".join(npc_desc))

    active_events = list(
        (
            await db.exec(
                select(GameEvent)
                .where(
                    GameEvent.session_id == session_id,
                    GameEvent.status == "active",
                )
                .order_by(GameEvent.created_at.asc())  # type: ignore[arg-type]
                .limit(8)
            )
        ).all()
    )
    if active_events:
        lines = []
        for evt in active_events:
            lines.append(f"- [{evt.event_type}] {evt.name}: {evt.description}")
        parts.append("Active events:\n" + "\n".join(lines))

    latest_assistant = (
        await db.exec(
            select(Message)
            .where(Message.session_id == session_id, Message.role == "assistant")
            .order_by(Message.created_at.desc())  # type: ignore[arg-type]
            .limit(1)
        )
    ).first()
    if latest_assistant and latest_assistant.content.strip():
        parts.append("Latest narration: " + _truncate(latest_assistant.content, 700))

    if not parts:
        return "No explicit text world state available yet."
    return "\n\n".join(parts)


def _build_generation_prompt(
    *,
    world_lore: str,
    text_world_state: str,
    story_background: str,
    prompt: str,
    continuity_notes: str | None,
    references: list[dict[str, Any]],
    previous_images: list[dict[str, Any]] | None = None,
    scene_frames: list[str] | None = None,
    layout_preference: str | None = None,
    runtime_settings: dict[str, Any] | None = None,
) -> str:
    runtime_settings = runtime_settings or {}
    style_preset = str(runtime_settings.get("style_preset") or "cinematic").strip()
    negative_prompt = str(runtime_settings.get("negative_prompt") or "").strip()
    strict_continuity = bool(runtime_settings.get("strict_continuity", True))
    scene_frames = [str(item).strip() for item in (scene_frames or []) if str(item).strip()]
    multi_scene_policy = str(runtime_settings.get("multi_scene_policy") or "comic").strip().lower()
    is_multi_scene, multi_scene_reason = _detect_multi_scene_mode(
        story_background=story_background,
        prompt=prompt,
        scene_frames=scene_frames,
        layout_preference=layout_preference,
    )

    ref_lines: list[str] = []
    for ref in references:
        rid = str(ref.get("image_id") or "")
        rtitle = str(ref.get("title") or "reference frame")
        rprompt = str(ref.get("prompt") or "")
        ref_lines.append(
            f"- id={rid}, title={rtitle}, prompt={_truncate(rprompt, 160)}"
        )
    reference_summary = "\n".join(ref_lines) if ref_lines else "(none)"

    recent_source = previous_images if isinstance(previous_images, list) else references
    recent_lines: list[str] = []
    for ref in recent_source[-6:]:
        rid = str(ref.get("image_id") or "")
        rtitle = str(ref.get("title") or "frame")
        rwhen = str(ref.get("created_at") or "")
        rprompt = str(ref.get("prompt") or "")
        recent_lines.append(
            f"- {rtitle} (id={rid}, at={rwhen}): {_truncate(rprompt, 120)}"
        )
    recent_images_text = "\n".join(recent_lines) if recent_lines else "(none)"

    user_template = str(runtime_settings.get("prompt_template") or "").strip()
    if user_template and "{{story_background}}" in user_template and "{{frame_prompt}}" in user_template:
        rendered = render_settings_template(
            user_template,
            {
                "story_background": story_background.strip(),
                "frame_prompt": prompt.strip(),
                "continuity_notes": continuity_notes or "",
                "reference_summary": reference_summary,
                "style_preset": style_preset,
                "negative_prompt": negative_prompt,
            },
        ).strip()
        if rendered:
            sections = [
                "You are an RPG visual director generating one story-consistent image.",
                "[World Lore]\n" + (_truncate(world_lore, 2000) or "(empty)"),
                "[Current Text World State]\n" + (_truncate(text_world_state, 2000) or "(empty)"),
                "[Recent Generated Images]\n" + recent_images_text,
                "[User Prompt Template Rendered]\n" + rendered,
            ]
            if strict_continuity:
                sections.append(
                    "[Continuity Policy]\n"
                    "Strictly keep character appearance, costume, and key props consistent with references."
                )
            if scene_frames:
                sections.append("[Scene Frames]\n" + "\n".join(f"- {item}" for item in scene_frames))
            if is_multi_scene and multi_scene_policy != "single":
                sections.append(
                    "[Layout Requirement]\n"
                    "Output one multi-panel comic composition (2-6 panels) with clear panel borders.\n"
                    "Each panel should represent one scene beat with coherent reading order."
                )
            else:
                sections.append("[Layout Requirement]\nOutput a single cinematic frame.")
            sections.append(f"[Layout Decision Reason]\n{multi_scene_reason}")
            if negative_prompt:
                sections.append("[Negative Prompt]\n" + negative_prompt)
            return "\n\n".join(sections)

    sections = [
        "You are an RPG visual director generating one story-consistent image.",
        "[Style Preset]\n" + style_preset,
        "[World Lore]\n" + (_truncate(world_lore, 2000) or "(empty)"),
        "[Current Text World State]\n" + (_truncate(text_world_state, 2000) or "(empty)"),
        "[Recent Generated Images]\n" + recent_images_text,
        "[Story Background]\n" + story_background.strip(),
        "[Current Frame]\n" + prompt.strip(),
    ]
    if continuity_notes and continuity_notes.strip():
        sections.append("[Continuity Notes]\n" + continuity_notes.strip())
    if ref_lines:
        sections.append("[Reference Frames]\n" + "\n".join(ref_lines))
    if scene_frames:
        sections.append("[Scene Frames]\n" + "\n".join(f"- {item}" for item in scene_frames))
    if is_multi_scene and multi_scene_policy != "single":
        sections.append(
            "[Layout Requirement]\n"
            "Render as a multi-panel comic page/strip (2-6 panels) with clear panel borders.\n"
            "Preserve continuity of characters and props across panels."
        )
    else:
        sections.append("[Layout Requirement]\nRender as a single cinematic frame.")
    sections.append(f"[Layout Decision Reason]\n{multi_scene_reason}")
    if negative_prompt:
        sections.append("[Negative Prompt]\n" + negative_prompt)
    sections.append(
        "[Output Constraints]\n"
        "- Keep character appearance and major props consistent with references.\n"
        "- Preserve scene continuity and story tone.\n"
        "- Focus only on the requested current frame."
    )
    if strict_continuity:
        sections.append(
            "[Strict Continuity]\n"
            "- Do not change character face/body proportions across frames.\n"
            "- Keep same outfit palette and unique accessories unless explicitly requested."
        )
    return "\n\n".join(sections)


def _extract_possible_json_string(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        parsed = json.loads(stripped)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _guess_mime_from_bytes(payload: bytes) -> str | None:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith(b"GIF87a") or payload.startswith(b"GIF89a"):
        return "image/gif"
    if payload.startswith(b"RIFF") and len(payload) >= 12 and payload[8:12] == b"WEBP":
        return "image/webp"
    return None


def _to_data_url_from_base64(candidate: str) -> tuple[str | None, str | None]:
    cleaned = "".join(ch for ch in candidate if ch not in "\n\r\t ")
    if len(cleaned) < 64:
        return None, None

    # If the string already includes a data URL prefix.
    if cleaned.startswith("data:image/"):
        return cleaned, None

    # Strip optional "base64," prefix.
    if cleaned.lower().startswith("base64,"):
        cleaned = cleaned.split(",", 1)[1]

    if not re.fullmatch(r"[A-Za-z0-9+/=]+", cleaned):
        return None, None

    try:
        decoded = base64.b64decode(cleaned, validate=True)
    except (binascii.Error, ValueError):
        return None, None

    mime = _guess_mime_from_bytes(decoded)
    if not mime:
        return None, None

    return f"data:{mime};base64,{cleaned}", mime


def _extract_image_from_text(text: str) -> tuple[str | None, str | None]:
    markdown_match = _MARKDOWN_IMAGE_RE.search(text)
    if markdown_match:
        return markdown_match.group(1), None

    data_match = _DATA_URL_RE.search(text)
    if data_match:
        return data_match.group(1), None

    url_match = _URL_RE.search(text)
    if url_match:
        return url_match.group(1), None

    # Try pure base64 payloads embedded in text.
    for run in _BASE64_RUN_RE.findall(text):
        data_url, _mime = _to_data_url_from_base64(run)
        if data_url:
            return data_url, None

    return None, text.strip() or None


def _extract_from_content_item(item: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    image_url = item.get("image_url")
    if isinstance(image_url, str):
        out["image_url"] = image_url
    elif isinstance(image_url, dict):
        nested_url = image_url.get("url")
        if isinstance(nested_url, str):
            out["image_url"] = nested_url
        nested_b64 = image_url.get("b64_json")
        if isinstance(nested_b64, str):
            out["image_b64"] = nested_b64
            out["mime_type"] = str(image_url.get("mime_type") or "image/png")

    if isinstance(item.get("url"), str):
        out["image_url"] = item["url"]
    if isinstance(item.get("b64_json"), str):
        out["image_b64"] = item["b64_json"]
        out["mime_type"] = str(item.get("mime_type") or "image/png")
    if isinstance(item.get("image_base64"), str):
        out["image_b64"] = item["image_base64"]
        out["mime_type"] = str(item.get("mime_type") or "image/png")

    text = item.get("text")
    if isinstance(text, str) and text.strip():
        out["text"] = text.strip()
        data_url, mime = _extract_image_from_text(text)
        if data_url:
            out["image_url"] = data_url
            if data_url.startswith("data:") and mime:
                out["mime_type"] = mime
                out["image_b64"] = data_url.split(",", 1)[1]

    return out


def _extract_image_payload(raw: dict[str, Any]) -> dict[str, Any]:
    image_url: str | None = None
    image_b64: str | None = None
    mime_type: str | None = None
    text_notes: list[str] = []

    choices = raw.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message")
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    parsed = _extract_from_content_item(item)
                    if not image_url and isinstance(parsed.get("image_url"), str):
                        image_url = parsed["image_url"]
                    if not image_b64 and isinstance(parsed.get("image_b64"), str):
                        image_b64 = parsed["image_b64"]
                        mime_type = str(parsed.get("mime_type") or "image/png")
                    text = parsed.get("text")
                    if isinstance(text, str) and text:
                        text_notes.append(text)
            elif isinstance(content, str):
                parsed_json = _extract_possible_json_string(content)
                if parsed_json:
                    parsed = _extract_from_content_item(parsed_json)
                    if not image_url and isinstance(parsed.get("image_url"), str):
                        image_url = parsed["image_url"]
                    if not image_b64 and isinstance(parsed.get("image_b64"), str):
                        image_b64 = parsed["image_b64"]
                        mime_type = str(parsed.get("mime_type") or "image/png")
                    text = parsed.get("text")
                    if isinstance(text, str) and text:
                        text_notes.append(text)
                else:
                    found_url, text_note = _extract_image_from_text(content)
                    if not image_url and found_url:
                        image_url = found_url
                    if text_note:
                        text_notes.append(text_note)

    data_items = raw.get("data")
    if isinstance(data_items, list):
        for item in data_items:
            if not isinstance(item, dict):
                continue
            parsed = _extract_from_content_item(item)
            if not image_url and isinstance(parsed.get("image_url"), str):
                image_url = parsed["image_url"]
            if not image_b64 and isinstance(parsed.get("image_b64"), str):
                image_b64 = parsed["image_b64"]
                mime_type = str(parsed.get("mime_type") or "image/png")
            text = parsed.get("text")
            if isinstance(text, str) and text:
                text_notes.append(text)

    if isinstance(raw.get("image_url"), str) and not image_url:
        image_url = raw["image_url"]
    if isinstance(raw.get("b64_json"), str) and not image_b64:
        image_b64 = raw["b64_json"]
        mime_type = str(raw.get("mime_type") or "image/png")

    # If image_url is a data URL, extract base64 from it
    if image_url and image_url.startswith("data:image/") and not image_b64:
        data_match = _DATA_URL_RE.search(image_url)
        if data_match:
            full_data_url = data_match.group(1)
            # Parse mime type and base64 from data URL
            # Format: data:image/png;base64,iVBORw0KGgo...
            if ";base64," in full_data_url:
                prefix, b64_data = full_data_url.rsplit(";base64,", 1)
                mime_type = prefix.replace("data:", "")
                image_b64 = b64_data

    if image_b64 and not image_url:
        image_url = f"data:{mime_type or 'image/png'};base64,{image_b64}"

    if not image_url:
        note = _truncate("\n".join(text_notes), 300) if text_notes else ""
        raise ValueError(f"No image found in API response. note={note!r}")

    return {
        "image_url": image_url,
        "image_b64": image_b64,
        "mime_type": mime_type or "image/png",
        "note": _truncate("\n".join(text_notes), 400) if text_notes else "",
    }


def _post_json_sync(
    *,
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(endpoint, data=data, headers=headers, method="POST")

    try:
        with urlopen(req, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {err_body[:800]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Connection failed: {exc.reason}") from exc
    except Exception as exc:
        raise RuntimeError(f"Image API request failed: {exc}") from exc

    try:
        parsed = json.loads(body)
    except Exception as exc:
        raise RuntimeError(f"Image API returned non-JSON body: {body[:800]}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("Image API returned unexpected payload type")
    return parsed


async def _call_image_api(
    *,
    prompt: str,
    config: ResolvedImageConfig,
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = {
        "model": config.model,
        "stream": False,
        "messages": messages or [{"role": "user", "content": prompt}],
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if config.has_api_key():
        headers["Authorization"] = f"Bearer {str(config.api_key).strip()}"

    return await asyncio.to_thread(
        _post_json_sync,
        endpoint=config.api_base,
        payload=payload,
        headers=headers,
    )


async def get_session_story_images(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
) -> list[dict[str, Any]]:
    stored = await storage_get(
        db,
        project_id,
        STORY_IMAGE_PLUGIN,
        _storage_key_for_session(session_id),
    )
    if not isinstance(stored, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in stored:
        if isinstance(item, dict):
            rows.append(item)
    return rows


async def _append_story_image(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
    record: dict[str, Any],
    autocommit: bool,
) -> None:
    rows = await get_session_story_images(
        db, project_id=project_id, session_id=session_id
    )
    rows.append(record)
    rows = rows[-_MAX_STORED_IMAGES:]
    await storage_set(
        db,
        project_id,
        STORY_IMAGE_PLUGIN,
        _storage_key_for_session(session_id),
        rows,
        autocommit=autocommit,
    )


def build_story_image_prompt_context(
    rows: list[dict[str, Any]],
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    condensed: list[dict[str, Any]] = []
    for item in rows[-limit:]:
        condensed.append(
            {
                "image_id": item.get("image_id"),
                "title": item.get("title"),
                "story_background": _truncate(
                    str(item.get("story_background") or ""), 160
                ),
                "prompt": _truncate(str(item.get("prompt") or ""), 160),
                "continuity_notes": _truncate(
                    str(item.get("continuity_notes") or ""), 140
                ),
                "created_at": item.get("created_at"),
                "regenerated_from": item.get("regenerated_from"),
            }
        )
    return condensed


def _resolve_reference_frames(
    *,
    rows: list[dict[str, Any]],
    requested_ids: list[str],
) -> list[dict[str, Any]]:
    by_id = {
        str(item.get("image_id")): item
        for item in rows
        if isinstance(item, dict) and isinstance(item.get("image_id"), str)
    }
    resolved: list[dict[str, Any]] = []
    for rid in requested_ids:
        hit = by_id.get(rid)
        if hit is not None:
            resolved.append(hit)
    if not resolved and rows:
        resolved.append(rows[-1])
    return resolved


def _collect_reference_ids(frames: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for frame in frames:
        rid = frame.get("image_id")
        if isinstance(rid, str) and rid:
            ids.append(rid)
    return ids


def _resolve_reference_image_url(frame: dict[str, Any]) -> str | None:
    raw_url = frame.get("image_url")
    if isinstance(raw_url, str) and raw_url.strip():
        candidate = raw_url.strip()
        if candidate.startswith("data:image/") and len(candidate) > _MAX_DATA_URL_CHARS:
            logger.warning("Skip oversized data-url reference image: {} chars", len(candidate))
            return None
        return candidate

    raw_b64 = frame.get("image_b64")
    if isinstance(raw_b64, str) and raw_b64.strip():
        mime_type = str(frame.get("mime_type") or "image/png").strip() or "image/png"
        candidate = f"data:{mime_type};base64,{raw_b64.strip()}"
        if len(candidate) > _MAX_DATA_URL_CHARS:
            logger.warning("Skip oversized base64 reference image: {} chars", len(candidate))
            return None
        return candidate
    return None


def _build_image_generation_messages(
    *,
    prompt: str,
    references: list[dict[str, Any]],
    history_rows: list[dict[str, Any]],
    reference_limit: int,
) -> tuple[list[dict[str, Any]], int]:
    bounded_limit = min(max(0, reference_limit), _MAX_IMAGE_REFERENCE_INPUTS)
    if bounded_limit <= 0:
        return [{"role": "user", "content": prompt}], 0

    source_rows: list[dict[str, Any]]
    if references:
        source_rows = references[-bounded_limit:]
    else:
        source_rows = history_rows[-bounded_limit:]

    content_items: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    used = 0
    for item in source_rows:
        url = _resolve_reference_image_url(item)
        if not url:
            continue
        content_items.append({"type": "image_url", "image_url": {"url": url}})
        used += 1

    if used == 0:
        return [{"role": "user", "content": prompt}], 0
    return [{"role": "user", "content": content_items}], used


def _image_error_payload(
    *,
    title: str,
    story_background: str,
    prompt: str,
    continuity_notes: str,
    reference_image_ids: list[str],
    error: str,
) -> dict[str, Any]:
    return {
        "status": "error",
        "title": title or "Story Image",
        "story_background": story_background,
        "prompt": prompt,
        "continuity_notes": continuity_notes,
        "reference_image_ids": reference_image_ids,
        "error": error,
        "can_regenerate": True,
    }


async def generate_story_image(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
    title: str,
    story_background: str,
    prompt: str,
    continuity_notes: str | None = None,
    reference_image_ids: list[str] | None = None,
    scene_frames: list[str] | None = None,
    layout_preference: str | None = None,
    turn_id: str | None = None,
    regenerated_from: str | None = None,
    max_retries: int = 1,
    autocommit: bool = False,
) -> dict[str, Any]:
    story_background = (story_background or "").strip()
    prompt = (prompt or "").strip()
    continuity_notes = (continuity_notes or "").strip()
    requested_refs = [
        str(item).strip() for item in (reference_image_ids or []) if str(item).strip()
    ]
    scene_frames = [str(item).strip() for item in (scene_frames or []) if str(item).strip()]
    layout_preference = str(layout_preference or "auto").strip().lower()

    if not story_background:
        return _image_error_payload(
            title=title,
            story_background=story_background,
            prompt=prompt,
            continuity_notes=continuity_notes,
            reference_image_ids=requested_refs,
            error="story_background is required for story_image.",
        )
    if not prompt:
        return _image_error_payload(
            title=title,
            story_background=story_background,
            prompt=prompt,
            continuity_notes=continuity_notes,
            reference_image_ids=requested_refs,
            error="prompt is required for story_image.",
        )

    project = await db.get(Project, project_id)
    if not project:
        return _image_error_payload(
            title=title,
            story_background=story_background,
            prompt=prompt,
            continuity_notes=continuity_notes,
            reference_image_ids=requested_refs,
            error=f"Project not found: {project_id}",
        )

    config = resolve_image_config(project)
    if not config.has_api_key():
        return _image_error_payload(
            title=title,
            story_background=story_background,
            prompt=prompt,
            continuity_notes=continuity_notes,
            reference_image_ids=requested_refs,
            error=(
                "Image API key is not configured. "
                "Please set IMAGE_GEN_API_KEY in .env or project image settings."
            ),
        )

    history_rows = await get_session_story_images(
        db,
        project_id=project_id,
        session_id=session_id,
    )
    runtime_settings: dict[str, Any] = {}
    try:
        resolved_settings = await resolve_runtime_settings(
            db,
            project_id=project_id,
            session_id=session_id,
            enabled_plugins=[STORY_IMAGE_PLUGIN],
        )
        by_plugin = resolved_settings.get("by_plugin")
        if isinstance(by_plugin, dict):
            story_settings = by_plugin.get(STORY_IMAGE_PLUGIN)
            if isinstance(story_settings, dict):
                runtime_settings = dict(story_settings)
    except Exception:
        logger.exception("Failed to resolve runtime settings for story-image")

    references = _resolve_reference_frames(
        rows=history_rows, requested_ids=requested_refs
    )
    reference_limit_raw = runtime_settings.get("reference_count")
    reference_limit_for_input = 2
    if isinstance(reference_limit_raw, int):
        reference_limit = max(0, reference_limit_raw)
        reference_limit_for_input = reference_limit
        if reference_limit == 0:
            references = []
        elif len(references) > reference_limit:
            references = references[-reference_limit:]
    elif references:
        reference_limit_for_input = min(len(references), _MAX_IMAGE_REFERENCE_INPUTS)
    resolved_ref_ids = _collect_reference_ids(references)
    world_lore = _extract_world_lore_text(project.world_doc)
    text_world_state = await _build_text_world_state(db, session_id=session_id)
    final_prompt = _build_generation_prompt(
        world_lore=world_lore,
        text_world_state=text_world_state,
        story_background=story_background,
        prompt=prompt,
        continuity_notes=continuity_notes,
        references=references,
        previous_images=history_rows,
        scene_frames=scene_frames,
        layout_preference=layout_preference,
        runtime_settings=runtime_settings,
    )
    api_messages, reference_input_count = _build_image_generation_messages(
        prompt=final_prompt,
        references=references,
        history_rows=history_rows,
        reference_limit=reference_limit_for_input,
    )

    last_error = ""
    attempts = max(1, int(max_retries) + 1)
    raw_response: dict[str, Any] | None = None
    extracted: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        try:
            raw_response = await _call_image_api(
                prompt=final_prompt,
                config=config,
                messages=api_messages,
            )
            extracted = _extract_image_payload(raw_response)
            break
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "story_image generation failed (attempt {}/{}): {}",
                attempt,
                attempts,
                last_error,
            )

    if not extracted:
        return _image_error_payload(
            title=title,
            story_background=story_background,
            prompt=prompt,
            continuity_notes=continuity_notes,
            reference_image_ids=resolved_ref_ids,
            error=f"Image generation failed: {last_error or 'unknown error'}",
        )

    image_id = str(uuid.uuid4())
    created_at = _utcnow_iso()

    record = {
        "image_id": image_id,
        "session_id": session_id,
        "turn_id": turn_id,
        "title": title or "Story Image",
        "story_background": story_background,
        "prompt": prompt,
        "continuity_notes": continuity_notes,
        "reference_image_ids": resolved_ref_ids,
        "scene_frames": scene_frames,
        "layout_preference": layout_preference,
        "regenerated_from": regenerated_from,
        "model": config.model,
        "api_base": config.api_base,
        "provider_response_id": raw_response.get("id")
        if isinstance(raw_response, dict)
        else None,
        "image_url": extracted.get("image_url"),
        "image_b64": extracted.get("image_b64"),
        "mime_type": extracted.get("mime_type"),
        "provider_note": extracted.get("note"),
        "runtime_settings": runtime_settings,
        "generation_prompt": final_prompt,
        "reference_input_count": reference_input_count,
        "world_lore_excerpt": _truncate(world_lore, 2400),
        "text_world_state": _truncate(text_world_state, 2400),
        "created_at": created_at,
    }
    await _append_story_image(
        db,
        project_id=project_id,
        session_id=session_id,
        record=record,
        autocommit=autocommit,
    )

    reference_items = [
        {
            "image_id": item.get("image_id"),
            "title": item.get("title"),
        }
        for item in references
    ]

    return {
        "status": "ok",
        "image_id": image_id,
        "title": record["title"],
        "story_background": story_background,
        "prompt": prompt,
        "continuity_notes": continuity_notes,
        "reference_image_ids": resolved_ref_ids,
        "reference_images": reference_items,
        "scene_frames": scene_frames,
        "layout_preference": layout_preference,
        "regenerated_from": regenerated_from,
        "image_url": record["image_url"],
        "mime_type": record["mime_type"],
        "provider_model": config.model,
        "provider_note": record["provider_note"],
        "settings_applied": runtime_settings,
        "debug": {
            "generated_prompt": final_prompt,
            "world_lore_excerpt": record["world_lore_excerpt"],
            "text_world_state": record["text_world_state"],
            "reference_images": reference_items,
            "reference_input_count": reference_input_count,
            "runtime_settings": runtime_settings,
        },
        "created_at": created_at,
        "can_regenerate": True,
    }


async def regenerate_story_image(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
    image_id: str,
    reason: str | None = None,
    turn_id: str | None = None,
    autocommit: bool = False,
) -> dict[str, Any]:
    history_rows = await get_session_story_images(
        db,
        project_id=project_id,
        session_id=session_id,
    )
    source = next(
        (
            row
            for row in history_rows
            if isinstance(row, dict) and str(row.get("image_id")) == image_id
        ),
        None,
    )
    if not source:
        return {
            "status": "error",
            "error": f"image_id not found: {image_id}",
            "can_regenerate": True,
        }

    continuity_notes = str(source.get("continuity_notes") or "").strip()
    reason = (reason or "").strip()
    if reason:
        if continuity_notes:
            continuity_notes = f"{continuity_notes}. Regeneration note: {reason}"
        else:
            continuity_notes = f"Regeneration note: {reason}"

    refs = source.get("reference_image_ids")
    if not isinstance(refs, list):
        refs = []
    reference_ids = [str(item).strip() for item in refs if str(item).strip()]
    if not reference_ids:
        reference_ids = [image_id]

    new_title = str(source.get("title") or "Story Image")
    if "(regen)" not in new_title:
        new_title = f"{new_title} (regen)"

    return await generate_story_image(
        db,
        project_id=project_id,
        session_id=session_id,
        title=new_title,
        story_background=str(source.get("story_background") or ""),
        prompt=str(source.get("prompt") or ""),
        continuity_notes=continuity_notes,
        reference_image_ids=reference_ids,
        scene_frames=(
            [str(item).strip() for item in source.get("scene_frames", []) if str(item).strip()]
            if isinstance(source.get("scene_frames"), list)
            else []
        ),
        layout_preference=str(source.get("layout_preference") or "auto"),
        turn_id=turn_id,
        regenerated_from=image_id,
        autocommit=autocommit,
    )
