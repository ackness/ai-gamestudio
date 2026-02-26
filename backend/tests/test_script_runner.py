"""Tests for ScriptRunner."""
from __future__ import annotations

import pathlib

import pytest

from backend.app.core.audit_logger import AuditLogger
from backend.app.core.script_runner import (
    PythonScriptRunner,
    ScriptRunnerFactory,
    create_default_factory,
)


@pytest.fixture
def runner() -> PythonScriptRunner:
    return PythonScriptRunner()


@pytest.mark.asyncio
async def test_run_simple_script(runner: PythonScriptRunner, tmp_path: pathlib.Path):
    """Test executing a simple Python script that reads stdin JSON."""
    script = tmp_path / "echo.py"
    script.write_text(
        "import json, sys\n"
        "data = json.loads(sys.stdin.read())\n"
        "data['doubled'] = data.get('value', 0) * 2\n"
        "print(json.dumps(data))\n"
    )
    result = await runner.run(script, {"value": 21}, plugin_name="test", capability_id="echo")
    assert result.exit_code == 0
    assert result.parsed_output is not None
    assert result.parsed_output["doubled"] == 42


@pytest.mark.asyncio
async def test_run_script_not_found(runner: PythonScriptRunner, tmp_path: pathlib.Path):
    result = await runner.run(
        tmp_path / "missing.py", {}, plugin_name="test", capability_id="missing"
    )
    assert result.exit_code == -1
    assert "not found" in result.stderr


@pytest.mark.asyncio
async def test_run_script_timeout(runner: PythonScriptRunner, tmp_path: pathlib.Path):
    script = tmp_path / "slow.py"
    script.write_text("import time; time.sleep(10)\n")
    result = await runner.run(
        script, {}, timeout_ms=200, plugin_name="test", capability_id="slow"
    )
    assert result.exit_code == -1
    assert "timed out" in result.stderr


@pytest.mark.asyncio
async def test_run_script_invalid_json_output(
    runner: PythonScriptRunner, tmp_path: pathlib.Path
):
    script = tmp_path / "bad_output.py"
    script.write_text("print('not json')\n")
    result = await runner.run(
        script, {}, plugin_name="test", capability_id="bad_output"
    )
    assert result.exit_code == 0
    assert result.parsed_output is None
    assert result.stdout.strip() == "not json"


@pytest.mark.asyncio
async def test_audit_logging(db_session, sample_session, tmp_path: pathlib.Path):
    audit = AuditLogger(db_session)
    runner = PythonScriptRunner(audit)

    script = tmp_path / "echo.py"
    script.write_text("import json, sys; print(json.dumps({'ok': True}))\n")
    await runner.run(
        script, {}, plugin_name="test", capability_id="echo",
        session_id=sample_session.id,
    )

    entries = await audit.query(plugin="test")
    assert len(entries) == 1
    assert entries[0].capability == "echo"
    assert entries[0].exit_code == 0


@pytest.mark.asyncio
async def test_no_audit_without_session_id(db_session, sample_session, tmp_path: pathlib.Path):
    """Without session_id, audit logging is skipped."""
    audit = AuditLogger(db_session)
    runner = PythonScriptRunner(audit)

    script = tmp_path / "echo.py"
    script.write_text("import json, sys; print(json.dumps({'ok': True}))\n")
    await runner.run(script, {}, plugin_name="test", capability_id="echo")

    entries = await audit.query(plugin="test")
    assert len(entries) == 0


@pytest.mark.asyncio
async def test_non_py_script_rejected(runner: PythonScriptRunner, tmp_path: pathlib.Path):
    script = tmp_path / "script.sh"
    script.write_text("echo hello\n")
    result = await runner.run(script, {})
    assert result.exit_code == -1
    assert ".py" in result.stderr


class TestScriptRunnerFactory:
    def test_get_python_runner(self):
        factory = create_default_factory()
        runner = factory.get_runner("python")
        assert isinstance(runner, PythonScriptRunner)

    def test_get_unknown_language_raises(self):
        factory = create_default_factory()
        with pytest.raises(ValueError, match="javascript"):
            factory.get_runner("javascript")

    def test_register_and_get(self):
        factory = ScriptRunnerFactory()
        runner = PythonScriptRunner()
        factory.register("custom", runner)
        assert factory.get_runner("custom") is runner
