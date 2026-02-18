"""Tests for CapabilityExecutor."""
from __future__ import annotations

import json
import pathlib
import textwrap

import pytest

from backend.app.core.audit_logger import AuditLogger
from backend.app.core.capability_executor import CapabilityExecutor
from backend.app.core.plugin_engine import PluginEngine


def _create_script_plugin(tmp_path: pathlib.Path) -> str:
    """Create a test plugin with a script-type capability."""
    plugin_dir = tmp_path / "test-cap"
    plugin_dir.mkdir()
    scripts_dir = plugin_dir / "scripts"
    scripts_dir.mkdir()

    # manifest.json
    manifest = {
        "schema_version": "2.0",
        "name": "test-cap",
        "version": "1.0.0",
        "type": "gameplay",
        "required": False,
        "description": "Test plugin with script capability",
        "capabilities": {
            "test.echo": {
                "description": "Echo input with modification",
                "implementation": {
                    "type": "script",
                    "script": "scripts/echo.py",
                    "timeout_ms": 5000,
                },
                "result_block_type": "test_result",
            }
        },
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest))

    # PLUGIN.md (minimal)
    (plugin_dir / "PLUGIN.md").write_text(
        textwrap.dedent("""\
            ---
            name: test-cap
            version: 1.0.0
            description: Test plugin with script capability
            ---
            # Test Cap
        """)
    )

    # Script
    (scripts_dir / "echo.py").write_text(
        "import json, sys\n"
        "data = json.loads(sys.stdin.read())\n"
        "data['processed'] = True\n"
        "print(json.dumps(data))\n"
    )

    return str(tmp_path)


@pytest.fixture
def engine():
    PluginEngine.clear_cache()
    return PluginEngine()


@pytest.mark.asyncio
async def test_execute_script_capability(engine: PluginEngine, tmp_path: pathlib.Path):
    plugins_dir = _create_script_plugin(tmp_path)
    audit = AuditLogger(str(tmp_path / "audit"))

    executor = CapabilityExecutor(
        plugin_engine=engine,
        plugins_dir=plugins_dir,
        enabled_plugins=["test-cap"],
        audit_logger=audit,
    )

    result = await executor.execute({
        "plugin": "test-cap",
        "capability": "test.echo",
        "args": {"value": 42},
    })

    assert result.success is True
    assert len(result.result_blocks) == 1
    assert result.result_blocks[0]["type"] == "test_result"
    assert result.result_blocks[0]["data"]["processed"] is True
    assert result.result_blocks[0]["data"]["value"] == 42


@pytest.mark.asyncio
async def test_execute_unknown_plugin(engine: PluginEngine, tmp_path: pathlib.Path):
    executor = CapabilityExecutor(
        plugin_engine=engine,
        plugins_dir=str(tmp_path),
        enabled_plugins=[],
    )

    result = await executor.execute({
        "plugin": "nonexistent",
        "capability": "test",
    })

    assert result.success is False
    assert "not enabled" in result.error


@pytest.mark.asyncio
async def test_execute_unknown_capability(engine: PluginEngine, tmp_path: pathlib.Path):
    plugins_dir = _create_script_plugin(tmp_path)

    executor = CapabilityExecutor(
        plugin_engine=engine,
        plugins_dir=plugins_dir,
        enabled_plugins=["test-cap"],
    )

    result = await executor.execute({
        "plugin": "test-cap",
        "capability": "nonexistent.cap",
    })

    assert result.success is False
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_execute_missing_fields():
    engine = PluginEngine()
    executor = CapabilityExecutor(
        plugin_engine=engine,
        plugins_dir="/tmp",
        enabled_plugins=[],
    )

    result = await executor.execute({})
    assert result.success is False
    assert "plugin" in result.error and "capability" in result.error


@pytest.mark.asyncio
async def test_execute_dice_roll_script(engine: PluginEngine):
    """Test the actual dice-roll plugin's script capability."""
    executor = CapabilityExecutor(
        plugin_engine=engine,
        plugins_dir="plugins",
        enabled_plugins=["dice-roll"],
    )

    result = await executor.execute({
        "plugin": "dice-roll",
        "capability": "dice.roll",
        "args": {"expr": "1d6"},
    })

    assert result.success is True
    assert len(result.result_blocks) == 1
    assert result.result_blocks[0]["type"] == "dice_result"
    data = result.result_blocks[0]["data"]
    assert 1 <= data["result"] <= 6
    assert data["dice"] == "1d6"
