from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_API_BASE_ALLOWED_HOSTS = [
    "api.openai.com",
    "openrouter.ai",
    "api.deepseek.com",
    "api.anthropic.com",
    "dashscope.aliyuncs.com",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATA_DIR: str | None = None
    LOG_DIR: str | None = None
    DATABASE_URL: str | None = None
    LLM_MODEL: str = "deepseek/deepseek-chat"
    LLM_API_KEY: str | None = None
    LLM_API_BASE: str | None = "https://api.deepseek.com"
    PLUGIN_LLM_MODEL: str | None = None  # defaults to LLM_MODEL if unset
    PLUGIN_LLM_API_KEY: str | None = None  # defaults to LLM_API_KEY if unset
    PLUGIN_LLM_API_BASE: str | None = None  # defaults to LLM_API_BASE if unset
    IMAGE_GEN_MODEL: str = "gemini-2.5-flash-image-preview"
    IMAGE_GEN_API_KEY: str | None = None
    IMAGE_GEN_API_BASE: str | None = None
    API_BASE_ALLOW_HTTP: bool = False
    API_BASE_ALLOW_PRIVATE_NET: bool = False
    API_BASE_ALLOWED_HOSTS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: DEFAULT_API_BASE_ALLOWED_HOSTS.copy()
    )
    CORS_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    ACCESS_KEY: str | None = None  # if set, all API requests must include X-Access-Key header
    PLUGINS_DIR: str = "plugins"
    TEMPLATES_DIR: str = "templates/worlds"
    SECRET_STORE_DIR: str | None = None
    PLUGIN_BLOCK_STRICT_CONFLICTS: bool = False
    DEBUG_ENDPOINTS_ENABLED: bool = False
    MAX_LOG_SESSIONS: int = 200
    LOG_TTL_MINUTES: int = 30

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value):
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    @field_validator("API_BASE_ALLOWED_HOSTS", mode="before")
    @classmethod
    def _parse_allowed_hosts(cls, value):
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        return [str(item).strip().lower() for item in parsed if str(item).strip()]
                except Exception:
                    pass
            return [item.strip().lower() for item in raw.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        return []

    @model_validator(mode="after")
    def _apply_runtime_defaults(self):
        running_on_vercel = bool(os.getenv("VERCEL"))
        default_data_dir = "/tmp/ai-gamestudio-data" if running_on_vercel else "data"
        data_dir = (self.DATA_DIR or "").strip() or default_data_dir
        self.DATA_DIR = data_dir

        if not (self.LOG_DIR or "").strip():
            self.LOG_DIR = str(Path(data_dir) / "logs")

        if not (self.SECRET_STORE_DIR or "").strip():
            self.SECRET_STORE_DIR = str(Path(data_dir) / "secrets")

        db_url = (self.DATABASE_URL or "").strip()
        if not db_url:
            db_path = Path(data_dir) / "db.sqlite"
            self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path.as_posix()}"
            return self

        if running_on_vercel and db_url.startswith("sqlite+aiosqlite:///data/"):
            db_path = Path(data_dir) / "db.sqlite"
            self.DATABASE_URL = f"sqlite+aiosqlite:///{db_path.as_posix()}"
            return self

        self.DATABASE_URL = db_url
        return self


settings = Settings()
