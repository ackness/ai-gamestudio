"""Plugin engine: discover, load, validate, and render PLUGIN.md plugins.

V2 plugins use manifest.json as the machine truth source. When manifest.json
exists, metadata is loaded from it; PLUGIN.md retains only LLM-facing fields.
When manifest.json is absent, the engine falls back to V1 behavior (full
frontmatter parsing with a deprecation warning).

CLI usage:
    python -m backend.app.core.plugin_engine validate plugins/
    python -m backend.app.core.plugin_engine list plugins/
"""
from __future__ import annotations

import copy
import pathlib
import re
import sys
from dataclasses import dataclass
from typing import Any

import frontmatter
from jinja2 import BaseLoader, Environment
from loguru import logger

REQUIRED_FIELDS = {"name", "description", "type", "required"}
NAME_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$")

# V1 frontmatter fields that are LLM-only in V2 (merged from PLUGIN.md)
_LLM_ONLY_FIELDS = {"when_to_use", "avoid_when", "capability_summary"}


@dataclass
class BlockDeclaration:
    """Declarative block type defined in a plugin's manifest.json or PLUGIN.md frontmatter."""

    block_type: str
    plugin_name: str
    instruction: str | None = None
    schema: dict | None = None
    schema_ref: str | None = None
    handler: dict | None = None
    ui: dict | None = None
    requires_response: bool = False


class PluginEngine:
    """Discovers, loads, validates, and renders PLUGIN.md plugins."""

    _plugin_cache: dict[str, tuple[tuple[tuple[int, int] | None, tuple[int, int] | None], dict[str, Any]]] = {}
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
        [{name, description, type, required, version, dependencies, manifest_source, capabilities, path}, ...]
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
                    manifest = loaded.get("manifest")
                    has_script_capability = False
                    if manifest and getattr(manifest, "capabilities", None):
                        for cap_cfg in manifest.capabilities.values():
                            if not isinstance(cap_cfg, dict):
                                continue
                            impl = cap_cfg.get("implementation")
                            if isinstance(impl, dict) and impl.get("type") == "script":
                                has_script_capability = True
                                break
                    entry: dict[str, Any] = {
                        "name": meta.get("name", child.name),
                        "description": meta.get("description", ""),
                        "type": meta.get("type", ""),
                        "required": meta.get("required", False),
                        "default_enabled": meta.get("default_enabled", False),
                        "supersedes": meta.get("supersedes", []),
                        "version": meta.get("version", ""),
                        "dependencies": meta.get("dependencies", []),
                        "manifest_source": loaded.get("manifest_source", "v1_fallback"),
                        "capabilities": list(loaded.get("manifest").capabilities.keys())
                        if loaded.get("manifest")
                        else [],
                        "has_script_capability": has_script_capability,
                        "i18n": meta.get("i18n", {}),
                        "path": str(child),
                    }
                    plugins.append(entry)
                except Exception:
                    logger.warning("Failed to parse {}", plugin_md)
        return plugins

    def load(self, plugin_name: str, plugins_dir: str | None = None) -> dict[str, Any] | None:
        """Load full plugin content (level 2 loading).

        Returns metadata + full markdown body, or None if not found.
        V2: If manifest.json exists, loads metadata from it and merges
        LLM-only fields from PLUGIN.md frontmatter.
        """
        from backend.app.core.config import settings

        plugins_dir = plugins_dir or settings.PLUGINS_DIR
        plugin_dir = pathlib.Path(plugins_dir) / plugin_name
        plugin_path = plugin_dir / "PLUGIN.md"
        manifest_path = plugin_dir / "manifest.json"

        if not plugin_path.is_file():
            return None

        # Compute combined file signature for cache key
        md_sig = self._file_signature(plugin_path)
        manifest_sig = self._file_signature(manifest_path)
        combined_sig = (md_sig, manifest_sig)
        cache_key = str(plugin_path.resolve())
        cached = self._plugin_cache.get(cache_key)
        if cached is not None and cached[0] == combined_sig:
            return copy.deepcopy(cached[1])

        # Parse PLUGIN.md
        try:
            post = frontmatter.load(str(plugin_path))
        except Exception:
            logger.warning("Failed to parse {}", plugin_path)
            return None

        # Try V2 manifest loading
        has_manifest = manifest_path.is_file()
        if has_manifest:
            from backend.app.core.manifest_loader import load_manifest, manifest_to_v1_metadata

            try:
                manifest = load_manifest(plugin_dir)
            except ValueError as exc:
                logger.warning("Invalid manifest.json for '{}': {}", plugin_name, exc)
                manifest = None

            if manifest is not None:
                # V2 path: metadata from manifest, LLM-only fields from PLUGIN.md
                metadata = manifest_to_v1_metadata(manifest)
                # Merge LLM-only fields from PLUGIN.md frontmatter
                for field_name in _LLM_ONLY_FIELDS:
                    if field_name in post.metadata:
                        metadata[field_name] = post.metadata[field_name]

                loaded: dict[str, Any] = {
                    "name": manifest.name,
                    "metadata": metadata,
                    "content": post.content,
                    "path": str(plugin_dir),
                    "manifest_source": "manifest",
                    "manifest": manifest,
                }
                self._plugin_cache[cache_key] = (combined_sig, copy.deepcopy(loaded))
                return loaded

        # V1 fallback
        if has_manifest:
            # manifest.json existed but was invalid — already warned above
            pass
        else:
            logger.warning(
                "Plugin '{}' has no manifest.json, using V1 fallback", plugin_name
            )

        loaded = {
            "name": post.get("name", plugin_name),
            "metadata": dict(post.metadata),
            "content": post.content,
            "path": str(plugin_dir),
            "manifest_source": "v1_fallback",
            "manifest": None,
        }
        self._plugin_cache[cache_key] = (combined_sig, copy.deepcopy(loaded))
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

                # Handle schema: if string, store as schema_ref; if dict, store as schema
                raw_schema = block_cfg.get("schema")
                schema: dict | None = None
                schema_ref: str | None = None
                if isinstance(raw_schema, dict):
                    schema = raw_schema
                elif isinstance(raw_schema, str):
                    schema_ref = raw_schema

                declarations[block_type] = BlockDeclaration(
                    block_type=block_type,
                    plugin_name=name,
                    instruction=block_cfg.get("instruction"),
                    schema=schema,
                    schema_ref=schema_ref,
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

    def get_capability_declarations(
        self,
        enabled_plugins: list[str],
        plugins_dir: str | None = None,
    ) -> list[dict[str, Any]]:
        """Collect capability declarations from enabled plugins' manifests.

        Returns a list of {plugin, capability_id, description, result_block_type} dicts.
        """
        from backend.app.core.config import settings

        plugins_dir = plugins_dir or settings.PLUGINS_DIR
        ordered = self.resolve_dependencies(enabled_plugins, plugins_dir)
        capabilities: list[dict[str, Any]] = []

        for name in ordered:
            data = self.load(name, plugins_dir)
            if not data:
                continue
            manifest = data.get("manifest")
            if not manifest or not manifest.capabilities:
                continue
            for cap_id, cap_cfg in manifest.capabilities.items():
                capabilities.append({
                    "plugin": name,
                    "capability_id": cap_id,
                    "description": cap_cfg.get("description", ""),
                    "result_block_type": cap_cfg.get("result_block_type"),
                })

        return capabilities

    def get_template_path(
        self,
        plugin_name: str,
        template_rel_path: str,
        plugins_dir: str | None = None,
        project_overrides_dir: str | None = None,
    ) -> pathlib.Path | None:
        """Resolve a template path, checking project overrides first.

        Phase D stub: project_overrides_dir is currently unused.
        """
        from backend.app.core.config import settings

        plugins_dir = plugins_dir or settings.PLUGINS_DIR
        plugin_dir = pathlib.Path(plugins_dir) / plugin_name

        # Future: check project_overrides_dir/plugin_name/template_rel_path first

        resolved = plugin_dir / template_rel_path
        return resolved if resolved.is_file() else None

    def validate(self, plugins_dir: str) -> list[dict[str, Any]]:
        """Validate all plugins in plugins_dir against spec rules.

        V2 enhanced: when manifest.json exists, validates it; also checks
        name/version consistency between manifest.json and PLUGIN.md.
        """
        from backend.app.core.manifest_loader import load_manifest, validate_manifest

        root = pathlib.Path(plugins_dir)
        results: list[dict[str, Any]] = []

        if not root.is_dir():
            return [{"plugin": plugins_dir, "errors": ["Directory not found"]}]

        for child in sorted(root.iterdir()):
            if not child.is_dir():
                continue
            plugin_md = child / "PLUGIN.md"
            manifest_json = child / "manifest.json"
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

            # V2: validate manifest.json if present
            if manifest_json.is_file():
                try:
                    manifest = load_manifest(child)
                except ValueError as exc:
                    errors.append(f"Invalid manifest.json: {exc}")
                    results.append({"plugin": child.name, "errors": errors})
                    continue

                if manifest is not None:
                    # Check name/version consistency between manifest and PLUGIN.md
                    md_name = meta.get("name")
                    if md_name and md_name != manifest.name:
                        errors.append(
                            f"Name mismatch: PLUGIN.md says '{md_name}', "
                            f"manifest.json says '{manifest.name}'"
                        )
                    md_version = meta.get("version")
                    if md_version and str(md_version) != str(manifest.version):
                        errors.append(
                            f"Version mismatch: PLUGIN.md says '{md_version}', "
                            f"manifest.json says '{manifest.version}'"
                        )

                    # Validate manifest against its own rules
                    import json
                    raw = json.loads(manifest_json.read_text(encoding="utf-8"))
                    manifest_errors = validate_manifest(raw, child.name)
                    errors.extend(manifest_errors)

                    # Check prompt template exists (from manifest)
                    if manifest.prompt and manifest.prompt.get("template"):
                        tpl = child / manifest.prompt["template"]
                        if not tpl.is_file():
                            errors.append(
                                f"Prompt template not found: {manifest.prompt['template']}"
                            )

                    # Check capability script paths exist
                    for cap_id, cap_cfg in manifest.capabilities.items():
                        impl = cap_cfg.get("implementation", {})
                        if impl.get("type") == "script":
                            script = impl.get("script", "")
                            if script and not (child / script).is_file():
                                errors.append(
                                    f"Capability '{cap_id}' script not found: {script}"
                                )

                    # Check dependencies exist
                    for dep in manifest.dependencies:
                        dep_dir = root / dep
                        if not dep_dir.is_dir() or not (dep_dir / "PLUGIN.md").is_file():
                            errors.append(f"Dependency '{dep}' not found")

                    results.append({"plugin": child.name, "errors": errors})
                    continue

            # V1 fallback validation
            # Rule 3: required fields
            for field_name in REQUIRED_FIELDS:
                if field_name not in meta:
                    errors.append(f"Missing required field: {field_name}")

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
            source_tag = f" [{p.get('manifest_source', '?')}]"
            print(f"  {p['name']:<20} {p['type']:<10}{required_tag}{source_tag}")
            if p.get("description"):
                desc = p["description"][:80]
                print(f"    {desc}")
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    _cli()
