"""Resolve effective LLM configuration from overrides/project/profile/env."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.core.config import settings
from backend.app.core.secret_store import get_secret_store
from backend.app.models.llm_profile import LlmProfile
from backend.app.models.project import Project


@dataclass(frozen=True)
class ResolvedLlmConfig:
    model: str
    api_key: str | None
    api_base: str | None
    source: str  # "call_kwargs" | "project" | "profile" | "env" | "default"

    def is_empty_key(self) -> bool:
        return not self.api_key or self.api_key.strip() == ""


def _is_empty(value: str | None) -> bool:
    return value is None or value.strip() == ""


def _resolve_project_api_key(project: Project) -> str | None:
    store = get_secret_store()
    secret_key = store.get_secret(project.llm_api_key_ref)
    if not _is_empty(secret_key):
        return secret_key
    return project.llm_api_key


def _resolve_profile_api_key(profile: LlmProfile) -> str | None:
    store = get_secret_store()
    secret_key = store.get_secret(profile.api_key_ref)
    if not _is_empty(secret_key):
        return secret_key
    return profile.api_key


def _has_any_override(overrides: dict[str, Any]) -> bool:
    return any(
        not _is_empty(overrides.get(key)) for key in ("model", "api_key", "api_base")
    )


def resolve_llm_config(
    project: Project | None = None,
    profile: LlmProfile | None = None,
    overrides: dict[str, Any] | None = None,
) -> ResolvedLlmConfig:
    """Resolve final LLM config in priority order.

    Priority:
    1. call overrides
    2. project
    3. profile
    4. env settings
    5. hard-coded default
    """
    overrides = overrides or {}

    # 1) Call overrides: allow overriding any subset of fields.
    if _has_any_override(overrides):
        override_model = str(overrides.get("model") or "").strip()
        override_api_key = str(overrides.get("api_key") or "").strip()
        override_api_base = str(overrides.get("api_base") or "").strip()
        return ResolvedLlmConfig(
            model=override_model or settings.LLM_MODEL or "gpt-4o-mini",
            api_key=override_api_key if override_api_key else settings.LLM_API_KEY,
            api_base=override_api_base if override_api_base else settings.LLM_API_BASE,
            source="call_kwargs",
        )

    # 2) Project-level config.
    if project and not _is_empty(project.llm_model):
        project_api_key = _resolve_project_api_key(project)
        return ResolvedLlmConfig(
            model=project.llm_model or settings.LLM_MODEL or "gpt-4o-mini",
            api_key=project_api_key if not _is_empty(project_api_key) else settings.LLM_API_KEY,
            api_base=project.llm_api_base if not _is_empty(project.llm_api_base) else settings.LLM_API_BASE,
            source="project",
        )

    # 3) Profile-level config.
    if profile and not _is_empty(profile.model):
        profile_api_key = _resolve_profile_api_key(profile)
        return ResolvedLlmConfig(
            model=profile.model or settings.LLM_MODEL or "gpt-4o-mini",
            api_key=profile_api_key if not _is_empty(profile_api_key) else settings.LLM_API_KEY,
            api_base=profile.api_base if not _is_empty(profile.api_base) else settings.LLM_API_BASE,
            source="profile",
        )

    # 4) Environment defaults.
    if not _is_empty(settings.LLM_MODEL):
        return ResolvedLlmConfig(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            api_base=settings.LLM_API_BASE,
            source="env",
        )

    # 5) Hard fallback.
    return ResolvedLlmConfig(
        model="gpt-4o-mini",
        api_key=None,
        api_base=None,
        source="default",
    )


def get_effective_config_for_project(project: Project | None = None) -> ResolvedLlmConfig:
    return resolve_llm_config(project=project)

