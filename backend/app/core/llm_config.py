"""LLM 配置解析器 - 统一处理配置优先级和边界情况."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.app.core.config import settings
from backend.app.core.secret_store import get_secret_store
from backend.app.models.llm_profile import LlmProfile
from backend.app.models.project import Project


@dataclass(frozen=True)
class ResolvedLlmConfig:
    """解析后的 LLM 配置."""
    model: str
    api_key: Optional[str]
    api_base: Optional[str]
    source: str  # 'call_kwargs' | 'project' | 'profile' | 'env' | 'default'

    def is_empty_key(self) -> bool:
        """检查 api_key 是否为空（None 或空字符串）."""
        return not self.api_key or self.api_key.strip() == ""


def _is_empty(value: Optional[str]) -> bool:
    """检查值是否为空（None 或空字符串）."""
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


def resolve_llm_config(
    project: Optional[Project] = None,
    profile: Optional[LlmProfile] = None,
    overrides: Optional[dict] = None,
) -> ResolvedLlmConfig:
    """
    解析最终的 LLM 配置。

    优先级（从高到低）:
    1. overrides (调用参数) - 用于单次调用覆盖
    2. project (项目级配置)
    3. profile (用户保存的 Profile)
    4. settings (全局 .env 配置)
    5. default (硬编码默认值)

    空字符串被视为"未设置"，会触发 fallback。

    Args:
        project: 当前项目，可为 None
        profile: 选中的 Profile，可为 None
        overrides: 调用时的覆盖参数，如 {"model": "gpt-4o"}

    Returns:
        ResolvedLlmConfig 包含最终配置和来源信息
    """
    overrides = overrides or {}

    # 1. 检查 overrides
    override_model = overrides.get("model")
    if not _is_empty(override_model):
        override_api_key = overrides.get("api_key")
        override_api_base = overrides.get("api_base")
        return ResolvedLlmConfig(
            model=override_model,
            api_key=override_api_key if not _is_empty(override_api_key) else settings.LLM_API_KEY,
            api_base=override_api_base if not _is_empty(override_api_base) else settings.LLM_API_BASE,
            source="call_kwargs",
        )

    # 2. 检查 project（项目级配置）
    if project and not _is_empty(project.llm_model):
        project_api_key = _resolve_project_api_key(project)
        return ResolvedLlmConfig(
            model=project.llm_model,
            api_key=project_api_key if not _is_empty(project_api_key) else settings.LLM_API_KEY,
            api_base=project.llm_api_base if not _is_empty(project.llm_api_base) else settings.LLM_API_BASE,
            source="project",
        )

    # 3. 检查 profile（用户 Profile）
    if profile and not _is_empty(profile.model):
        profile_api_key = _resolve_profile_api_key(profile)
        return ResolvedLlmConfig(
            model=profile.model,
            api_key=profile_api_key if not _is_empty(profile_api_key) else settings.LLM_API_KEY,
            api_base=profile.api_base if not _is_empty(profile.api_base) else settings.LLM_API_BASE,
            source="profile",
        )

    # 4. 使用全局配置
    if not _is_empty(settings.LLM_MODEL):
        return ResolvedLlmConfig(
            model=settings.LLM_MODEL,
            api_key=settings.LLM_API_KEY,
            api_base=settings.LLM_API_BASE,
            source="env",
        )

    # 5. 默认值
    return ResolvedLlmConfig(
        model="gpt-4o-mini",
        api_key=None,
        api_base=None,
        source="default",
    )


def get_effective_config_for_project(project: Optional[Project] = None) -> ResolvedLlmConfig:
    """获取项目生效的配置（简化版，无 overrides）."""
    return resolve_llm_config(project=project)
