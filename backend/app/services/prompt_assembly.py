from __future__ import annotations

import json
from typing import Any

from backend.app.core.plugin_engine import BlockDeclaration
from backend.app.core.prompt_builder import PromptBuilder
from backend.app.services.turn_context import TurnContext


def assemble_prompt(
    ctx: TurnContext,
    user_content: str,
    save_user_msg: bool,
) -> list[dict[str, str]]:
    """Build the PromptBuilder from TurnContext and return the messages list."""
    builder = PromptBuilder()

    # System: world doc
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
        # Enforce output language based on world document metadata
        if world_language:
            _LANG_DISPLAY = {
                "zh": "中文", "en": "English", "ja": "日本語",
                "ko": "한국어", "es": "Español", "fr": "Français",
                "de": "Deutsch", "pt": "Português", "ru": "Русский",
            }
            lang_display = _LANG_DISPLAY.get(world_language, world_language)
            builder.inject(
                "system", 1,
                f"**LANGUAGE REQUIREMENT**: All your narrative text, dialogue, and descriptions "
                f"MUST be written in **{lang_display}**. "
                f"This does not apply to ```json:xxx``` structured data blocks — "
                f"field keys and technical identifiers inside blocks may remain in English.",
            )
    else:
        builder.inject(
            "system", 0,
            "You are the Dungeon Master (DM) for a role-playing game. "
            "No world document has been defined yet. Help the player explore.",
        )

    # Character info
    if ctx.characters:
        char_text = "## Characters\n\n"
        for ch in ctx.characters:
            char_text += f"- **{ch.name}** ({ch.role}) [id: {ch.id}]"
            if ch.description:
                char_text += f": {ch.description}"
            if ch.personality:
                char_text += f"\n  Personality: {ch.personality}"
            attrs = json.loads(ch.attributes_json) if ch.attributes_json else {}
            if attrs:
                char_text += f"\n  Attributes: {json.dumps(attrs, ensure_ascii=False)}"
            inv = json.loads(ch.inventory_json) if ch.inventory_json else []
            if inv:
                char_text += f"\n  Inventory: {', '.join(str(i) for i in inv)}"
            char_text += "\n"
        builder.inject("character", 10, char_text)

    # Scene context
    if ctx.current_scene:
        npc_names = []
        for snpc in ctx.scene_npcs:
            role_suffix = f" ({snpc['role_in_scene']})" if snpc.get("role_in_scene") else ""
            npc_names.append(f"{snpc['name']}{role_suffix}")
        scene_text = "## Current Scene\n\n"
        scene_text += f"Scene: {ctx.current_scene.name}\n"
        if ctx.current_scene.description:
            scene_text += f"Description: {ctx.current_scene.description}\n"
        if npc_names:
            scene_text += f"NPCs present: {', '.join(npc_names)}\n"
        builder.inject("character", 5, scene_text)

    # Active events
    if ctx.active_events:
        events_text = "## Active Events\n\n"
        for evt in ctx.active_events:
            vis_tag = "" if evt.visibility == "known" else " [hidden]"
            events_text += f"- [{evt.event_type}] {evt.name} ({evt.status}) [id: {evt.id}]{vis_tag}"
            if evt.description:
                events_text += f" — {evt.description}"
            events_text += "\n"
        builder.inject("world-state", 20, events_text)

    # Session world state
    session_world_state = ctx.world_state.get("session_world_state", {})
    if isinstance(session_world_state, dict) and session_world_state:
        world_state_json = json.dumps(session_world_state, ensure_ascii=False, indent=2)
        if len(world_state_json) > 4000:
            world_state_json = world_state_json[:4000] + "\n... (truncated)"
        builder.inject(
            "world-state", 15,
            "## Session World State\n\n"
            "The following JSON is the current persistent runtime world state "
            "for this session. Treat it as authoritative when narrating.\n\n"
            f"```json\n{world_state_json}\n```",
        )

    # Plugin prompt injections
    _inject_plugins(builder, ctx)

    # Chat history
    if save_user_msg:
        for i, msg in enumerate(ctx.recent_messages[:-1]):
            builder.inject("chat-history", i, f"{msg.role}: {msg.content}")
    else:
        for i, msg in enumerate(ctx.recent_messages):
            builder.inject("chat-history", i, f"{msg.role}: {msg.content}")

    builder.inject("chat-history", len(ctx.recent_messages) + 1, f"user: {user_content}")

    # Pre-response instructions
    builder.inject(
        "pre-response", 0,
        _build_pre_response_instructions(
            ctx.block_declarations,
            capability_declarations=ctx.capability_declarations,
        ),
    )
    if ctx.runtime_settings_prompt:
        builder.inject("pre-response", 5, ctx.runtime_settings_prompt)

    return builder.build()


def _inject_plugins(builder: PromptBuilder, ctx: TurnContext) -> None:
    """Inject plugin prompt content into the builder."""
    if not ctx.enabled_names or not ctx.pe:
        return
    try:
        character_context = [
            {
                "id": c.id, "name": c.name, "role": c.role,
                "description": c.description,
                "attributes": json.loads(c.attributes_json) if c.attributes_json else {},
                "inventory": json.loads(c.inventory_json) if c.inventory_json else [],
            }
            for c in ctx.characters
        ]
        player_context = next((c for c in character_context if c["role"] == "player"), None)
        npc_context = [c for c in character_context if c["role"] != "player"]
        context = {
            "project": {"name": ctx.project.name, "world_doc": ctx.project.world_doc},
            "characters": character_context,
            "current_scene": {
                "name": ctx.current_scene.name,
                "description": ctx.current_scene.description,
            } if ctx.current_scene else None,
            "active_events": [
                {
                    "id": e.id, "event_type": e.event_type, "name": e.name,
                    "description": e.description, "status": e.status, "visibility": e.visibility,
                }
                for e in ctx.active_events
            ],
            "player": player_context,
            "npcs": npc_context,
            "scene_npcs": ctx.scene_npcs,
            "world_state": ctx.world_state,
            "memories": ctx.memories,
            "runtime_settings": ctx.runtime_settings_by_plugin,
            "runtime_settings_flat": ctx.runtime_settings_flat,
            "story_images": ctx.story_images,
            "archive": ctx.archive_context,
        }
        injections = ctx.pe.get_prompt_injections(ctx.enabled_names, context)
        for inj in injections:
            content = str(inj.get("content", "") or "").strip()
            if not content:
                continue
            builder.inject(inj["position"], inj["priority"], content)
    except Exception:
        from loguru import logger
        logger.exception("Failed to inject plugin prompts")


def _build_pre_response_instructions(
    block_declarations: dict[str, BlockDeclaration] | None = None,
    *,
    capability_declarations: list[dict[str, Any]] | None = None,
) -> str:
    """Build the pre-response block format instructions for the LLM."""
    header = (
        "Respond in character as the DM. You may include structured data blocks "
        "in your response using fenced code blocks.\n\n"
        "**IMPORTANT FORMAT RULE**: Every structured data block MUST use triple-backtick "
        "fences with the `json:<type>` tag. The correct format is:\n"
        "```\n"
        "```json:<type>\n"
        '{"key": "value"}\n'
        "```\n"
        "```\n"
        "Do NOT omit the triple backticks. Do NOT use plain `json:<type>` without fences.\n\n"
    )

    if block_declarations:
        sections: list[str] = []
        for i, (block_type, decl) in enumerate(block_declarations.items(), 1):
            if decl.instruction:
                sections.append(f"{i}. **{block_type}**:\n{decl.instruction.strip()}")
        if sections:
            header += "Available block types:\n\n"
            header += "\n\n".join(sections)
            header += (
                "\n\nInclude blocks at the end of your narrative text. "
                "You may include multiple blocks in a single response. "
                "Each block MUST be wrapped in triple-backtick fences as shown above."
            )

    if capability_declarations:
        cap_sections: list[str] = []
        for cap in capability_declarations:
            cap_sections.append(
                f"- **{cap['capability_id']}** (plugin: {cap['plugin']}): "
                f"{cap.get('description', '')}"
            )
        header += (
            "\n\n## Plugin Capabilities (plugin_use protocol)\n\n"
            "You can invoke plugin capabilities by outputting a `json:plugin_use` block. "
            "The backend will execute the capability and return the result.\n\n"
            "Format:\n"
            "```\n"
            "```json:plugin_use\n"
            '{"plugin": "<plugin-name>", "capability": "<capability-id>", "args": {<arguments>}}\n'
            "```\n"
            "```\n\n"
            "Available capabilities:\n"
            + "\n".join(cap_sections)
        )

    if not block_declarations and not capability_declarations:
        header += (
            "You may output structured data as ```json:<type>``` blocks at the end "
            "of your narrative text when game state changes occur."
        )

    return header
