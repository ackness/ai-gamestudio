"""Plugin engine: discover, load, validate, and render PLUGIN.md plugins.

CLI usage:
    python -m backend.app.core.plugin_engine validate plugins/
    python -m backend.app.core.plugin_engine list plugins/
"""
from __future__ import annotations

import copy
import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import Any

import frontmatter
from jinja2 import BaseLoader, Environment
from loguru import logger

REQUIRED_FIELDS = {"name", "description", "type", "required"}
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$")


@dataclass
class BlockDeclaration:
    """Declarative block type defined in a plugin's PLUGIN.md frontmatter."""

    block_type: str
    plugin_name: str
    instruction: str | None = None
    schema: dict | None = None
    handler: dict | None = None
    ui: dict | None = None
    requires_response: bool = False


class PluginEngine:
    """Discovers, loads, validates, and renders PLUGIN.md plugins."""

    _plugin_cache: dict[str, tuple[tuple[int, int], dict[str, Any]]] = {}
    _template_cache: dict[str, tuple[tuple[int, int], str]] = {}

    def __init__(self) -> None:
        self._last_block_conflicts: list[dict[str, str]] = []

    @staticmethod
    def _file_signature(path: pathlib.Path) -> tuple[int, int] | None:
        """Return a stable file signature (mtime_ns, size) if file exists."""
        if not path.is_file():
            return None
        stat = path.stat()
        return (int(stat.st_mtime_ns), int(stat.st_size))

    @classmethod
    def clear_cache(cls) -> None:
        """Clear plugin and template caches (mainly for tests/dev tooling)."""
        cls._plugin_cache.clear()
        cls._template_cache.clear()

    def discover(self, plugins_dir: str) -> list[dict[str, Any]]:
        """Scan plugins_dir for subdirectories containing PLUGIN.md.

        Returns a list of lightweight plugin metadata dicts (level 1 loading):
        [{name, description, type, required, path}, ...]
        """
        root = pathlib.Path(plugins_dir)
        if not root.is_dir():
            return []

        plugins: list[dict[str, Any]] = []
        for child in sorted(root.iterdir()):
            plugin_md = child / "PLUGIN.md"
            if child.is_dir() and plugin_md.is_file():
                try:
                    loaded = self.load(child.name, plugins_dir)
                    if not loaded:
                        continue
                    meta = loaded["metadata"]
                    plugins.append(
                        {
                            "name": meta.get("name", child.name),
                            "description": meta.get("description", ""),
                            "type": meta.get("type", ""),
                            "required": meta.get("required", False),
                            "version": meta.get("version", ""),
                            "dependencies": meta.get("dependencies", []),
                            "path": str(child),
                        }
                    )
                except Exception:
                    logger.warning("Failed to parse {}", plugin_md)
        return plugins

    def load(self, plugin_name: str, plugins_dir: str | None = None) -> dict[str, Any] | None:
        """Load full plugin content (level 2 loading).

        Returns metadata + full markdown body, or None if not found.
        """
        from backend.app.core.config import settings

        plugins_dir = plugins_dir or settings.PLUGINS_DIR
        plugin_path = pathlib.Path(plugins_dir) / plugin_name / "PLUGIN.md"
        if not plugin_path.is_file():
            return None

        signature = self._file_signature(plugin_path)
        cache_key = str(plugin_path.resolve())
        cached = self._plugin_cache.get(cache_key)
        if (
            signature is not None
            and cached is not None
            and cached[0] == signature
        ):
            return copy.deepcopy(cached[1])

        try:
            post = frontmatter.load(str(plugin_path))
        except Exception:
            logger.warning("Failed to parse {}", plugin_path)
            return None

        loaded = {
            "name": post.get("name", plugin_name),
            "metadata": dict(post.metadata),
            "content": post.content,
            "path": str(plugin_path.parent),
        }
        if signature is not None:
            self._plugin_cache[cache_key] = (signature, copy.deepcopy(loaded))
        return loaded

    def _read_template_cached(self, template_path: pathlib.Path) -> str:
        signature = self._file_signature(template_path)
        cache_key = str(template_path.resolve())
        cached = self._template_cache.get(cache_key)
        if signature is not None and cached is not None and cached[0] == signature:
            return cached[1]

        text = template_path.read_text(encoding="utf-8")
        if signature is not None:
            self._template_cache[cache_key] = (signature, text)
        return text

    def resolve_dependencies(self, enabled_plugins: list[str], plugins_dir: str | None = None) -> list[str]:
        """Topological sort of enabled plugins based on declared dependencies.

        Returns ordered list with dependencies before dependents.
        """
        from backend.app.core.config import settings

        plugins_dir = plugins_dir or settings.PLUGINS_DIR

        # Build adjacency
        dep_map: dict[str, list[str]] = {}
        for name in enabled_plugins:
            data = self.load(name, plugins_dir)
            if data:
                dep_map[name] = data["metadata"].get("dependencies", [])
            else:
                dep_map[name] = []

        # Kahn's algorithm
        in_degree: dict[str, int] = {n: 0 for n in enabled_plugins}
        for name, deps in dep_map.items():
            for d in deps:
                if d in in_degree:
                    in_degree[name] = in_degree.get(name, 0) + 1

        queue = [n for n in enabled_plugins if in_degree.get(n, 0) == 0]
        result: list[str] = []
        while queue:
            node = queue.pop(0)
            result.append(node)
            for name, deps in dep_map.items():
                if node in deps:
                    in_degree[name] -= 1
                    if in_degree[name] == 0 and name not in result:
                        queue.append(name)

        # Add any remaining (circular deps) at the end
        for name in enabled_plugins:
            if name not in result:
                result.append(name)

        return result

    def get_prompt_injections(
        self,
        enabled_plugins: list[str],
        context: dict[str, Any],
        plugins_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        """Render Jinja2 prompt templates for enabled plugins.

        Returns list of {position, priority, content} dicts ready for PromptBuilder.
        """
        from backend.app.core.config import settings

        plugins_dir = plugins_dir or settings.PLUGINS_DIR

        ordered = self.resolve_dependencies(enabled_plugins, plugins_dir)
        injections: list[dict[str, Any]] = []

        jinja_env = Environment(loader=BaseLoader(), autoescape=False)

        for name in ordered:
            data = self.load(name, plugins_dir)
            if not data:
                continue

            meta = data["metadata"]
            prompt_cfg = meta.get("prompt")
            if not prompt_cfg:
                # If no prompt config, inject the markdown body as world-state
                if data["content"].strip():
                    injections.append(
                        {
                            "position": "world-state",
                            "priority": 50,
                            "content": data["content"],
                        }
                    )
                continue

            position = prompt_cfg.get("position", "world-state")
            priority = prompt_cfg.get("priority", 50)
            template_path = prompt_cfg.get("template")

            if template_path:
                tpl_file = pathlib.Path(data["path"]) / template_path
                if tpl_file.is_file():
                    tpl_text = self._read_template_cached(tpl_file)
                else:
                    tpl_text = data["content"]
            else:
                tpl_text = data["content"]

            # Render template with context
            try:
                template = jinja_env.from_string(tpl_text)
                rendered = template.render(**context)
            except Exception:
                logger.warning("Failed to render template for plugin {}", name)
                rendered = tpl_text

            injections.append(
                {
                    "position": position,
                    "priority": priority,
                    "content": rendered,
                }
            )

        return injections

    def get_block_declarations(
        self,
        enabled_plugins: list[str],
        plugins_dir: str | None = None,
        *,
        strict_conflicts: bool | None = None,
    ) -> dict[str, BlockDeclaration]:
        """Extract block declarations from enabled plugins.

        Returns a dict mapping block_type to BlockDeclaration, ordered by
        plugin dependency resolution.
        """
        from backend.app.core.config import settings

        plugins_dir = plugins_dir or settings.PLUGINS_DIR
        strict_conflicts = (
            settings.PLUGIN_BLOCK_STRICT_CONFLICTS
            if strict_conflicts is None
            else strict_conflicts
        )
        ordered = self.resolve_dependencies(enabled_plugins, plugins_dir)
        declarations: dict[str, BlockDeclaration] = {}
        conflicts: list[dict[str, str]] = []

        for name in ordered:
            data = self.load(name, plugins_dir)
            if not data:
                continue
            blocks = data["metadata"].get("blocks")
            if not blocks or not isinstance(blocks, dict):
                continue
            for block_type, block_cfg in blocks.items():
                if not isinstance(block_cfg, dict):
                    continue
                if block_type in declarations:
                    prev = declarations[block_type]
                    conflict = {
                        "block_type": block_type,
                        "overridden_plugin": prev.plugin_name,
                        "winner_plugin": name,
                    }
                    conflicts.append(conflict)
                    message = (
                        f"Block type conflict: '{block_type}' declared by "
                        f"'{prev.plugin_name}' and '{name}'. '{name}' wins."
                    )
                    if strict_conflicts:
                        raise ValueError(message)
                    logger.warning(message)
                declarations[block_type] = BlockDeclaration(
                    block_type=block_type,
                    plugin_name=name,
                    instruction=block_cfg.get("instruction"),
                    schema=block_cfg.get("schema"),
                    handler=block_cfg.get("handler"),
                    ui=block_cfg.get("ui"),
                    requires_response=block_cfg.get("requires_response", False),
                )

        self._last_block_conflicts = conflicts
        return declarations

    def get_last_block_conflicts(self) -> list[dict[str, str]]:
        """Return block conflicts discovered during the last declaration scan."""
        return list(self._last_block_conflicts)

    def get_block_conflicts(
        self,
        enabled_plugins: list[str],
        plugins_dir: str | None = None,
    ) -> list[dict[str, str]]:
        """Compute block conflicts for enabled plugins without strict-failing."""
        self.get_block_declarations(
            enabled_plugins,
            plugins_dir=plugins_dir,
            strict_conflicts=False,
        )
        return self.get_last_block_conflicts()

    def validate(self, plugins_dir: str) -> list[dict[str, Any]]:
        """Validate all plugins in plugins_dir against spec rules.

        Returns list of {plugin, errors} dicts.
        """
        root = pathlib.Path(plugins_dir)
        results: list[dict[str, Any]] = []

        if not root.is_dir():
            return [{"plugin": plugins_dir, "errors": ["Directory not found"]}]

        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            plugin_md = child / "PLUGIN.md"
            errors: list[str] = []

            # Rule 1: must have PLUGIN.md
            if not plugin_md.is_file():
                errors.append("Missing PLUGIN.md")
                results.append({"plugin": child.name, "errors": errors})
                continue

            # Rule 2: valid YAML frontmatter
            try:
                post = frontmatter.load(str(plugin_md))
            except Exception as e:
                errors.append(f"Invalid frontmatter: {e}")
                results.append({"plugin": child.name, "errors": errors})
                continue

            meta = post.metadata

            # Rule 3: required fields
            for field in REQUIRED_FIELDS:
                if field not in meta:
                    errors.append(f"Missing required field: {field}")

            # Rule 4: name matches directory
            if meta.get("name") != child.name:
                errors.append(
                    f"name '{meta.get('name')}' does not match directory '{child.name}'"
                )

            # Rule 5: name format
            name = meta.get("name", "")
            if name and not NAME_RE.match(name):
                errors.append(
                    f"name '{name}' must be lowercase alphanumeric + hyphens, "
                    "not starting/ending with hyphen"
                )

            # Rule 6: dependencies exist
            for dep in meta.get("dependencies", []):
                dep_dir = root / dep
                if not dep_dir.is_dir() or not (dep_dir / "PLUGIN.md").is_file():
                    errors.append(f"Dependency '{dep}' not found")

            # Rule 7: hook scripts exist
            hooks = meta.get("hooks", {})
            for hook_name, script_path in hooks.items():
                if hook_name == "on-cron":
                    continue  # cron is a string expression, not a file
                script_file = child / script_path
                if not script_file.is_file():
                    errors.append(f"Hook script not found: {script_path}")

            # Rule 8: prompt template exists
            prompt_cfg = meta.get("prompt", {})
            if prompt_cfg and prompt_cfg.get("template"):
                tpl = child / prompt_cfg["template"]
                if not tpl.is_file():
                    errors.append(f"Prompt template not found: {prompt_cfg['template']}")

            results.append({"plugin": child.name, "errors": errors})

        return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m backend.app.core.plugin_engine <validate|list> <plugins_dir>")
        sys.exit(1)

    command = sys.argv[1]
    plugins_dir = sys.argv[2]
    engine = PluginEngine()

    if command == "validate":
        results = engine.validate(plugins_dir)
        has_errors = False
        for r in results:
            if r["errors"]:
                has_errors = True
                print(f"  FAIL  {r['plugin']}")
                for err in r["errors"]:
                    print(f"        - {err}")
            else:
                print(f"  OK    {r['plugin']}")
        sys.exit(1 if has_errors else 0)

    elif command == "list":
        plugins = engine.discover(plugins_dir)
        if not plugins:
            print("No plugins found.")
        for p in plugins:
            required_tag = " [REQUIRED]" if p.get("required") else ""
            print(f"  {p['name']:<20} {p['type']:<10}{required_tag}")
            if p.get("description"):
                desc = p["description"][:80]
                print(f"    {desc}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
