"""CapabilityExecutor: dispatch json:plugin_use blocks to plugin capabilities.

Validates the invocation, routes to the correct implementation (script/builtin/template),
and wraps results in the appropriate block type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from loguru import logger

from backend.app.core.audit_logger import AuditLogger
from backend.app.core.manifest_loader import PluginManifest
from backend.app.core.plugin_engine import PluginEngine
from backend.app.core.script_runner import ScriptRunnerFactory, create_default_factory


@dataclass
class CapabilityResult:
    success: bool
    result_blocks: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


class CapabilityExecutor:
    """Execute plugin capability invocations from json:plugin_use blocks."""

    def __init__(
        self,
        plugin_engine: PluginEngine,
        plugins_dir: str,
        enabled_plugins: list[str],
        audit_logger: AuditLogger | None = None,
        script_factory: ScriptRunnerFactory | None = None,
    ) -> None:
        self._engine = plugin_engine
        self._plugins_dir = plugins_dir
        self._enabled = set(enabled_plugins)
        self._audit = audit_logger or AuditLogger()
        self._script_factory = script_factory or create_default_factory(self._audit)

    async def execute(
        self,
        data: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> CapabilityResult:
        """Execute a plugin_use invocation.

        Expected data shape:
        {
            "plugin": "dice-roll",
            "capability": "dice.roll",
            "args": {"expr": "2d6+3"}
        }
        """
        plugin_name = data.get("plugin")
        capability_id = data.get("capability")
        args = data.get("args") or {}

        if not plugin_name or not capability_id:
            return CapabilityResult(
                success=False,
                error="plugin_use requires 'plugin' and 'capability' fields",
            )

        # Check plugin is enabled
        if plugin_name not in self._enabled:
            return CapabilityResult(
                success=False,
                error=f"Plugin '{plugin_name}' is not enabled",
            )

        # Load plugin and find capability
        plugin_data = self._engine.load(plugin_name, self._plugins_dir)
        if not plugin_data:
            return CapabilityResult(
                success=False,
                error=f"Plugin '{plugin_name}' not found",
            )

        manifest: PluginManifest | None = plugin_data.get("manifest")
        if not manifest or not manifest.capabilities:
            return CapabilityResult(
                success=False,
                error=f"Plugin '{plugin_name}' has no capabilities",
            )

        cap_cfg = manifest.capabilities.get(capability_id)
        if not cap_cfg:
            return CapabilityResult(
                success=False,
                error=f"Capability '{capability_id}' not found in plugin '{plugin_name}'",
            )

        implementation = cap_cfg.get("implementation", {})
        impl_type = implementation.get("type", "")
        result_block_type = cap_cfg.get("result_block_type")

        try:
            if impl_type == "script":
                return await self._execute_script(
                    plugin_name, capability_id, implementation, args, result_block_type
                )
            elif impl_type == "builtin":
                return CapabilityResult(
                    success=False,
                    error=f"Builtin capability execution not yet implemented for '{capability_id}'",
                )
            elif impl_type == "template":
                return CapabilityResult(
                    success=False,
                    error=f"Template capability execution not yet implemented for '{capability_id}'",
                )
            else:
                return CapabilityResult(
                    success=False,
                    error=f"Unknown implementation type: '{impl_type}'",
                )
        except Exception as exc:
            logger.error("Capability execution failed: {}.{}: {}", plugin_name, capability_id, exc)
            return CapabilityResult(
                success=False,
                error=f"Execution error: {exc}",
            )

    async def _execute_script(
        self,
        plugin_name: str,
        capability_id: str,
        implementation: dict[str, Any],
        args: dict[str, Any],
        result_block_type: str | None,
    ) -> CapabilityResult:
        """Execute a script-type capability."""
        script_rel = implementation.get("script", "")
        timeout_ms = implementation.get("timeout_ms", 10_000)
        language = implementation.get("language", "python")

        plugin_dir = self._engine._resolve_plugin_dir(plugin_name, self._plugins_dir)
        if plugin_dir is None:
            return CapabilityResult(
                success=False,
                error=f"Plugin directory not found for '{plugin_name}'",
            )
        script_path = (plugin_dir / script_rel).resolve()

        # Prevent path traversal — script must be inside plugin directory
        if not script_path.is_relative_to(plugin_dir.resolve()):
            return CapabilityResult(
                success=False,
                error=f"Script path escapes plugin directory: {script_rel}",
            )

        try:
            runner = self._script_factory.get_runner(language)
        except ValueError as exc:
            return CapabilityResult(success=False, error=str(exc))

        result = await runner.run(
            script_path,
            args,
            timeout_ms=timeout_ms,
            plugin_name=plugin_name,
            capability_id=capability_id,
        )

        if result.exit_code != 0:
            return CapabilityResult(
                success=False,
                error=f"Script exited with code {result.exit_code}: {result.stderr}",
            )

        # Wrap parsed output in result block
        result_blocks: list[dict[str, Any]] = []
        if result.parsed_output and result_block_type:
            result_blocks.append({
                "type": result_block_type,
                "data": result.parsed_output,
            })
        elif result.parsed_output:
            result_blocks.append({
                "type": "plugin_result",
                "data": result.parsed_output,
            })

        return CapabilityResult(success=True, result_blocks=result_blocks)
