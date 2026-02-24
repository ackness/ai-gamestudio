from __future__ import annotations

from backend.app.core.prompt_builder import PromptBuilder
from backend.app.services.turn_context import TurnContext


def _inject_world_doc(builder: PromptBuilder, ctx: TurnContext) -> None:
    """Inject world doc into system position (shared by both prompt modes)."""
    if ctx.project.world_doc:
        try:
            import frontmatter as fm
            parsed = fm.loads(ctx.project.world_doc)
            clean_world_doc = parsed.content
            world_language = (parsed.metadata.get("language") or "").strip().lower()
        except Exception:
            clean_world_doc = ctx.project.world_doc
            world_language = ""
        builder.inject(
            "system", 0,
            "You are the Dungeon Master (DM) for a role-playing game.\n\n"
            f"## World Document\n\n{clean_world_doc}",
        )
        if world_language:
            _LANG_DISPLAY = {
                "zh": "中文", "en": "English", "ja": "日本語",
                "ko": "한국어", "es": "Español", "fr": "Français",
                "de": "Deutsch", "pt": "Português", "ru": "Русский",
            }
            lang_display = _LANG_DISPLAY.get(world_language, world_language)
            builder.inject(
                "system", 1,
                f"**LANGUAGE REQUIREMENT**: ALL your output MUST be in **{lang_display}**.",
            )
    else:
        builder.inject(
            "system", 0,
            "You are the Dungeon Master (DM) for a role-playing game. "
            "No world document has been defined yet. Help the player explore.",
        )


NARRATIVE_INSTRUCTION = (
    "Respond in character as the DM. Focus purely on storytelling — "
    "describe scenes, NPC dialogue, actions, and consequences.\n"
    "IMPORTANT RULES:\n"
    "- Do NOT output any structured data blocks (```json:xxx```).\n"
    "- Do NOT output action suggestions, numbered option lists, or \"你现在可以：\" style choices.\n"
    "- Do NOT end your response with a list of possible player actions.\n"
    "- The game's plugin system will independently generate guides and choices for the player.\n"
    "- Just end your narrative naturally and let the game system handle the rest."
)


def assemble_narrative_prompt(
    ctx: TurnContext,
    user_content: str,
    save_user_msg: bool,
) -> list[dict[str, str]]:
    """Build a narrative-only prompt (no block instructions, no plugin injections)."""
    builder = PromptBuilder()

    # World doc
    _inject_world_doc(builder, ctx)

    # Scene + characters (compact summary)
    if ctx.current_scene:
        scene_text = f"## Current Scene: {ctx.current_scene.name}\n"
        if ctx.current_scene.description:
            scene_text += ctx.current_scene.description + "\n"
        builder.inject("character", 5, scene_text)

    if ctx.characters:
        char_lines = ["## Characters\n"]
        for ch in ctx.characters:
            line = f"- **{ch.name}** ({ch.role})"
            if ch.description:
                line += f": {ch.description}"
            char_lines.append(line)
        builder.inject("character", 10, "\n".join(char_lines))

    # Memory / compression summary (if available)
    if ctx.compression_summary:
        builder.inject("memory", 0, f"## Story So Far\n\n{ctx.compression_summary}")

    # Chat history
    if save_user_msg:
        for i, msg in enumerate(ctx.recent_messages[:-1]):
            builder.inject("chat-history", i, f"{msg.role}: {msg.content}")
    else:
        for i, msg in enumerate(ctx.recent_messages):
            builder.inject("chat-history", i, f"{msg.role}: {msg.content}")
    builder.inject("chat-history", len(ctx.recent_messages) + 1, f"user: {user_content}")

    # Narrative-only instruction (no blocks)
    builder.inject("pre-response", 0, NARRATIVE_INSTRUCTION)

    return builder.build()


