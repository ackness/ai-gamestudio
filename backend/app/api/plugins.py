from __future__ import annotations

import pathlib
import shutil

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.config import settings
from backend.app.core.plugin_registry import get_plugin_engine
from backend.app.db.engine import get_session
from backend.app.models.project import Project
from backend.app.services.plugin_service import (
    get_enabled_plugins,
    storage_get,
    toggle_plugin,
)

router = APIRouter(prefix="/api/plugins", tags=["plugins"])


@router.get("")
async def list_plugins():
    """List all available plugins found in the plugins directory."""
    engine = get_plugin_engine()
    plugins = engine.discover(settings.PLUGINS_DIR)
    return plugins


class ToggleBody(BaseModel):
    project_id: str
    enabled: bool


@router.post("/{plugin_name}/toggle")
async def toggle_plugin_endpoint(
    plugin_name: str,
    body: ToggleBody,
    session: AsyncSession = Depends(get_session),
):
    """Enable or disable a plugin for a specific project."""
    # Verify plugin exists
    pe = get_plugin_engine()
    available = pe.discover(settings.PLUGINS_DIR)
    names = [p["name"] for p in available]
    if plugin_name not in names:
        raise HTTPException(status_code=404, detail="Plugin not found")

    try:
        await toggle_plugin(
            session,
            project_id=body.project_id,
            plugin_name=plugin_name,
            enabled=body.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "plugin": plugin_name, "enabled": body.enabled}


@router.get("/enabled/{project_id}")
async def list_enabled_plugins(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """List plugins enabled for a specific project."""
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    enabled = await get_enabled_plugins(session, project_id, world_doc=project.world_doc)
    return enabled


@router.get("/block-schemas")
async def get_block_schemas(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Return UI schemas for all block types declared by enabled plugins.

    Used by the frontend to drive generic schema-based block rendering.
    """
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    enabled = await get_enabled_plugins(
        session,
        project_id,
        world_doc=project.world_doc,
    )
    enabled_names = [p["plugin_name"] for p in enabled]

    pe = get_plugin_engine()
    try:
        declarations = pe.get_block_declarations(enabled_names, settings.PLUGINS_DIR)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    schemas: dict[str, dict] = {}
    for block_type, decl in declarations.items():
        entry: dict = {}
        if decl.ui:
            entry.update(decl.ui)
        entry["requires_response"] = decl.requires_response
        entry["plugin_name"] = decl.plugin_name
        if decl.schema:
            entry["schema"] = decl.schema
        schemas[block_type] = entry

    return schemas


@router.get("/block-conflicts")
async def get_block_conflicts(
    project_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Return block type conflicts among enabled plugins for a project."""
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    enabled = await get_enabled_plugins(
        session,
        project_id,
        world_doc=project.world_doc,
    )
    enabled_names = [p["plugin_name"] for p in enabled]

    pe = get_plugin_engine()
    conflicts = pe.get_block_conflicts(enabled_names, settings.PLUGINS_DIR)
    return conflicts


# ---------------------------------------------------------------------------
# Phase C: Import validation + Audit
# ---------------------------------------------------------------------------


class ImportValidationResult(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]


class ImportValidateBody(BaseModel):
    plugin_dir: str


@router.post("/import/validate")
async def validate_plugin_import(
    plugin_dir: str | None = None,
    body: ImportValidateBody | None = None,
) -> ImportValidationResult:
    """Validate a plugin directory for import readiness.

    Runs full validation: manifest + PLUGIN.md consistency, dependencies exist,
    scripts exist, schemas parseable.
    """
    target_dir = (
        body.plugin_dir
        if body and isinstance(body.plugin_dir, str) and body.plugin_dir.strip()
        else str(plugin_dir or "").strip()
    )
    if not target_dir:
        return ImportValidationResult(
            valid=False,
            errors=["plugin_dir is required"],
            warnings=[],
        )

    path = pathlib.Path(target_dir).resolve()
    # Security: restrict target_dir to allowed roots (same as install_plugin)
    allowed_roots = [
        pathlib.Path(settings.PLUGINS_DIR).resolve(),
        pathlib.Path("/tmp").resolve(),
    ]
    if not any(path.is_relative_to(root) for root in allowed_roots):
        return ImportValidationResult(
            valid=False,
            errors=["plugin_dir must be within the plugins directory or /tmp"],
            warnings=[],
        )
    if not path.is_dir():
        return ImportValidationResult(
            valid=False, errors=[f"Directory not found: {target_dir}"], warnings=[]
        )

    errors: list[str] = []
    warnings: list[str] = []

    # Must have PLUGIN.md
    if not (path / "PLUGIN.md").is_file():
        errors.append("Missing PLUGIN.md")
        return ImportValidationResult(valid=False, errors=errors, warnings=warnings)

    # Must have manifest.json
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        errors.append("Missing manifest.json")
    else:
        from backend.app.core.manifest_loader import load_manifest

        try:
            manifest = load_manifest(path)
            if manifest is None:
                errors.append("manifest.json exists but could not be loaded")
        except ValueError as exc:
            errors.append(f"Invalid manifest.json: {exc}")

    # Run engine validation
    pe = get_plugin_engine()
    parent_dir = path.parent
    results = pe.validate(str(parent_dir))
    for r in results:
        if r["plugin"] == path.name:
            errors.extend(r.get("errors", []))

    return ImportValidationResult(
        valid=len(errors) == 0, errors=errors, warnings=warnings
    )


class ImportInstallBody(BaseModel):
    source_dir: str


@router.post("/import/install")
async def install_plugin(body: ImportInstallBody):
    """Validate and install a plugin from source directory."""
    source = pathlib.Path(body.source_dir).resolve()
    # Security: restrict source_dir to the configured plugins directory
    # or a known safe staging area to prevent arbitrary file read
    allowed_roots = [
        pathlib.Path(settings.PLUGINS_DIR).resolve(),
        pathlib.Path("/tmp").resolve(),
    ]
    if not any(source.is_relative_to(root) for root in allowed_roots):
        raise HTTPException(
            status_code=403,
            detail="source_dir must be within the plugins directory or /tmp",
        )
    if not source.is_dir():
        raise HTTPException(status_code=400, detail="Source directory not found")

    # Validate first
    result = await validate_plugin_import(body.source_dir)
    if not result.valid:
        raise HTTPException(
            status_code=400,
            detail=f"Plugin validation failed: {'; '.join(result.errors)}",
        )

    # Get plugin name from manifest or directory name
    plugin_name = source.name
    dest = pathlib.Path(settings.PLUGINS_DIR) / plugin_name
    if dest.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Plugin '{plugin_name}' already exists",
        )

    try:
        shutil.copytree(str(source), str(dest))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to install plugin: {exc}",
        ) from exc

    # Clear engine cache
    pe = get_plugin_engine()
    pe.clear_cache()

    return {"ok": True, "plugin": plugin_name}


@router.get("/codex/{project_id}")
async def get_codex_entries(
    project_id: str, db: AsyncSession = Depends(get_session)
):
    """Return all codex entries for a project, grouped by category."""
    raw = await storage_get(db, project_id, "codex", "codex-entries")
    entries = raw if isinstance(raw, list) else []

    by_category: dict[str, list] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        cat = str(entry.get("category", "unknown"))
        by_category.setdefault(cat, []).append(entry)

    return {"entries": entries, "by_category": by_category, "total": len(entries)}


@router.get("/{plugin_name}/audit")
async def get_plugin_audit(
    plugin_name: str,
    limit: int = Query(default=50, ge=1, le=500),
):
    """Return recent audit entries for a plugin's capability invocations."""
    from backend.app.core.audit_logger import AuditLogger

    audit = AuditLogger()
    entries = audit.query(plugin=plugin_name, limit=limit)
    return entries


@router.get("/{plugin_name}/detail")
async def get_plugin_detail(plugin_name: str):
    """Return full plugin details: metadata, resolved prompt content, output definitions."""
    pe = get_plugin_engine()
    loaded = pe.load(plugin_name)
    if not loaded:
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' not found")

    manifest = loaded.get("manifest")
    metadata = loaded.get("metadata", {})
    plugin_path = pathlib.Path(loaded["path"])

    # Resolve prompt template content from disk
    prompt_detail: dict | None = None
    if manifest and manifest.prompt:
        tmpl = manifest.prompt.get("template")
        content: str | None = None
        if tmpl:
            plugin_root = plugin_path.resolve()
            tmpl_path = (plugin_path / tmpl).resolve()
            if tmpl_path.is_relative_to(plugin_root) and tmpl_path.is_file():
                try:
                    content = tmpl_path.read_text(encoding="utf-8")
                except OSError:
                    content = None
        prompt_detail = {
            "position": manifest.prompt.get("position"),
            "priority": manifest.prompt.get("priority"),
            "template": tmpl,
            "content": content,
        }

    # Output definitions (instruction + schema per type)
    outputs: dict = {}
    if manifest and manifest.outputs:
        outputs = manifest.outputs

    # Capabilities summary
    capabilities: dict = {}
    if manifest and manifest.capabilities:
        for cap_name, cap_data in manifest.capabilities.items():
            capabilities[cap_name] = {
                "description": cap_data.get("description", ""),
                "type": cap_data.get("implementation", {}).get("type", ""),
            }

    return {
        "name": metadata.get("name", plugin_name),
        "version": metadata.get("version", ""),
        "description": metadata.get("description", ""),
        "type": metadata.get("type", ""),
        "required": metadata.get("required", False),
        "default_enabled": metadata.get("default_enabled", False),
        "supersedes": metadata.get("supersedes", []),
        "dependencies": metadata.get("dependencies", []),
        "prompt": prompt_detail,
        "outputs": outputs,
        "capabilities": capabilities,
        "i18n": metadata.get("i18n", {}),
    }


# ---------------------------------------------------------------------------
# Phase D: Export placeholder
# ---------------------------------------------------------------------------


@router.post("/{plugin_name}/export")
async def export_plugin(plugin_name: str):
    """Export a plugin package. (Not yet implemented.)"""
    raise HTTPException(status_code=501, detail="Plugin export not yet implemented")
