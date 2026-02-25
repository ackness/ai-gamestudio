"""ScriptRunner: execute plugin scripts in isolated subprocesses.

Currently supports Python scripts. Phase D adds BaseScriptRunner ABC
and multi-language support via ScriptRunnerFactory.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import uuid
from dataclasses import dataclass
from typing import Any

from loguru import logger

from backend.app.core.audit_logger import AuditEntry, AuditLogger

_DEFAULT_TIMEOUT_MS = 10_000


@dataclass
class ScriptResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    parsed_output: dict[str, Any] | None = None


class BaseScriptRunner:
    """Abstract base for script runners (Phase D multi-language support)."""

    async def run(
        self,
        script_path: pathlib.Path,
        args: dict[str, Any],
        *,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
        plugin_name: str = "",
        capability_id: str = "",
    ) -> ScriptResult:
        raise NotImplementedError


class PythonScriptRunner(BaseScriptRunner):
    """Execute Python scripts via subprocess, passing args as JSON on stdin."""

    def __init__(self, audit_logger: AuditLogger | None = None) -> None:
        self._audit = audit_logger

    async def run(
        self,
        script_path: pathlib.Path,
        args: dict[str, Any],
        *,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
        plugin_name: str = "",
        capability_id: str = "",
    ) -> ScriptResult:
        """Run a Python script, return structured result.

        1. Validate script_path is .py
        2. Create subprocess with JSON args on stdin
        3. Apply timeout
        4. Parse stdout as JSON
        5. Log audit entry
        """
        invocation_id = uuid.uuid4().hex[:12]

        if not script_path.is_file():
            return ScriptResult(exit_code=-1, stderr=f"Script not found: {script_path}")

        if script_path.suffix != ".py":
            return ScriptResult(exit_code=-1, stderr=f"Only .py scripts supported: {script_path}")

        stdin_data = json.dumps(args, ensure_ascii=False).encode("utf-8")
        start = asyncio.get_event_loop().time()

        try:
            # Security: run plugin scripts in isolated mode with minimal env
            # to prevent access to server secrets and API keys
            safe_env = {
                "PATH": "/usr/bin:/bin",
                "PYTHONPATH": "",
                "HOME": "/tmp",
                "LANG": "en_US.UTF-8",
            }
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",  # isolated mode: no user site-packages, no PYTHON* env vars
                str(script_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=safe_env,
                cwd=str(script_path.parent),
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(input=stdin_data),
                    timeout=timeout_ms / 1000.0,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                elapsed = int((asyncio.get_event_loop().time() - start) * 1000)
                result = ScriptResult(
                    exit_code=-1,
                    stderr=f"Script timed out after {timeout_ms}ms",
                    duration_ms=elapsed,
                )
                self._log_audit(invocation_id, plugin_name, capability_id, str(script_path), args, result)
                return result

        except Exception as exc:
            elapsed = int((asyncio.get_event_loop().time() - start) * 1000)
            result = ScriptResult(
                exit_code=-1,
                stderr=f"Failed to execute script: {exc}",
                duration_ms=elapsed,
            )
            self._log_audit(invocation_id, plugin_name, capability_id, str(script_path), args, result)
            return result

        elapsed = int((asyncio.get_event_loop().time() - start) * 1000)
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        parsed_output = None
        if process.returncode == 0 and stdout.strip():
            try:
                parsed_output = json.loads(stdout)
            except json.JSONDecodeError:
                logger.warning("Script stdout not valid JSON: {}", script_path)

        result = ScriptResult(
            exit_code=process.returncode or 0,
            stdout=stdout,
            stderr=stderr,
            duration_ms=elapsed,
            parsed_output=parsed_output,
        )

        self._log_audit(invocation_id, plugin_name, capability_id, str(script_path), args, result)
        return result

    def _log_audit(
        self,
        invocation_id: str,
        plugin_name: str,
        capability_id: str,
        script: str,
        args: dict[str, Any],
        result: ScriptResult,
    ) -> None:
        if not self._audit:
            return
        entry = AuditEntry(
            invocation_id=invocation_id,
            plugin=plugin_name,
            capability=capability_id,
            script=script,
            args=args,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            stdout=result.stdout[:2000],  # Truncate for log safety
            stderr=result.stderr[:2000],
        )
        self._audit.log(entry)


class ScriptRunnerFactory:
    """Registry for script runners by language (Phase D)."""

    def __init__(self) -> None:
        self._runners: dict[str, BaseScriptRunner] = {}

    def register(self, language: str, runner: BaseScriptRunner) -> None:
        self._runners[language] = runner

    def get_runner(self, language: str) -> BaseScriptRunner:
        runner = self._runners.get(language)
        if runner is None:
            raise ValueError(f"No script runner registered for language: {language}")
        return runner


def create_default_factory(audit_logger: AuditLogger | None = None) -> ScriptRunnerFactory:
    """Create a factory with the default Python runner registered."""
    factory = ScriptRunnerFactory()
    factory.register("python", PythonScriptRunner(audit_logger))
    return factory
