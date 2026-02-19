from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from backend.app.core.block_handlers import BlockContext, dispatch_block as _default_dispatch
from backend.app.core.block_parser import extract_blocks
from backend.app.core.block_validation import validate_block_data
from backend.app.core.event_bus import PluginEventBus
from backend.app.core.audit_logger import AuditLogger
from backend.app.core.capability_executor import CapabilityExecutor
from backend.app.core.config import settings

if TYPE_CHECKING:
    from backend.app.core.plugin_engine import BlockDeclaration, PluginEngine


def _register_event_listeners(
    event_bus: PluginEventBus,
    pe: PluginEngine,
    enabled_names: list[str],
) -> None:
    """Register event listeners declared in plugin PLUGIN.md ``events.listen``."""
    from backend.app.core.block_handlers import DeclarativeBlockHandler

    for name in enabled_names:
        data = pe.load(name)
        if not data:
            continue
        events_cfg = data["metadata"].get("events")
        if not events_cfg or not isinstance(events_cfg, dict):
            continue
        listen_cfg = events_cfg.get("listen")
        if not listen_cfg or not isinstance(listen_cfg, list):
            continue
        for entry in listen_cfg:
            if isinstance(entry, dict):
                for event_name, handler_cfg in entry.items():
                    actions = (
                        handler_cfg.get("actions", [])
                        if isinstance(handler_cfg, dict)
                        else []
                    )
                    if actions:
                        dh = DeclarativeBlockHandler(actions, name)

                        async def _listener(
                            event_data: dict,
                            ctx: "BlockContext",
                            _handler: DeclarativeBlockHandler = dh,
                        ) -> None:
                            await _handler.process(event_data, ctx)

                        event_bus.register(event_name, _listener)


async def process_blocks(
    full_response: str,
    block_context: BlockContext,
    block_declarations: dict[str, BlockDeclaration],
    capability_declarations: list[dict[str, Any]],
    pe: PluginEngine,
    enabled_names: list[str],
    dispatch_fn=None,
) -> tuple[list[dict[str, Any]], PluginEventBus]:
    """Extract, validate, and dispatch all json:xxx blocks. Returns (processed_blocks, event_bus)."""
    if dispatch_fn is None:
        dispatch_fn = _default_dispatch
    blocks = extract_blocks(full_response)
    if blocks:
        logger.info("Extracted {} block(s): {}", len(blocks), [b["type"] for b in blocks])
        for block in blocks:
            logger.debug("Block type={}, data={}", block["type"], block["data"])

    event_bus = PluginEventBus()
    _register_event_listeners(event_bus, pe, enabled_names)

    # Create capability executor
    capability_executor: CapabilityExecutor | None = None
    try:
        if capability_declarations:
            audit_logger = AuditLogger()
            capability_executor = CapabilityExecutor(
                plugin_engine=pe,
                plugins_dir=settings.PLUGINS_DIR,
                enabled_plugins=enabled_names,
                audit_logger=audit_logger,
            )
    except Exception:
        logger.exception("Failed to initialize capability executor")

    processed_blocks: list[dict[str, Any]] = []
    turn_id = block_context.turn_id or ""

    for idx, block in enumerate(blocks):
        block_id = f"{turn_id}:{idx}"
        block_type = str(block.get("type", "unknown"))
        block_data = block.get("data")
        declaration = block_declarations.get(block_type) if block_declarations else None

        validation_errors = validate_block_data(block_type, block_data, declaration)
        if validation_errors:
            logger.warning("Invalid block skipped: type={}, errors={}", block_type, validation_errors)
            processed_blocks.append({
                "type": "notification",
                "data": {
                    "level": "error",
                    "title": "结构化数据已忽略",
                    "content": f"无效 block: {block_type} ({'; '.join(validation_errors[:2])})",
                },
                "block_id": f"{block_id}:validation_error",
            })
            continue

        enriched = await dispatch_fn(
            block, block_context, block_declarations,
            capability_executor=capability_executor,
        )
        if isinstance(enriched, list):
            for rb in enriched:
                processed_blocks.append({
                    "type": rb.get("type", "plugin_result"),
                    "data": rb.get("data", {}),
                    "block_id": f"{block_id}:cap",
                })
        else:
            processed_blocks.append({
                "type": enriched["type"],
                "data": enriched["data"],
                "block_id": block_id,
            })

    await event_bus.drain(block_context)
    return processed_blocks, event_bus
