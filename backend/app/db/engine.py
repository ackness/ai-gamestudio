from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from backend.app.core.config import settings
from backend.app.core.secret_store import get_secret_store

engine = create_async_engine(settings.DATABASE_URL, echo=False)


async def get_session() -> AsyncGenerator[SQLModelAsyncSession, None]:
    async with SQLModelAsyncSession(engine) as session:
        yield session


async def init_db() -> None:
    # Import all models so SQLModel registers them
    import backend.app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await _migrate(conn)
    await _migrate_plaintext_api_keys()


async def _migrate(conn) -> None:
    """Add columns that may be missing from older databases."""
    migrations = [
        ("project", "llm_api_key_ref", "TEXT"),
        ("project", "llm_api_key", "TEXT"),
        ("project", "llm_api_base", "TEXT"),
        ("project", "image_model", "TEXT"),
        ("project", "image_api_key_ref", "TEXT"),
        ("project", "image_api_key", "TEXT"),
        ("project", "image_api_base", "TEXT"),
        ("project", "init_prompt", "TEXT"),
        ("llmprofile", "api_key_ref", "TEXT"),
        ("llmprofile", "api_key", "TEXT"),
        ("llmprofile", "api_base", "TEXT"),
        ("llm_profile", "api_key_ref", "TEXT"),
        ("llm_profile", "api_key", "TEXT"),
        ("llm_profile", "api_base", "TEXT"),
    ]
    for table, column, col_type in migrations:
        try:
            await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            logger.info("Migration: added column {}.{}", table, column)
        except OperationalError:
            # Column already exists — ignore
            pass
        except Exception:
            logger.warning("Migration failed for {}.{}: unexpected error", table, column, exc_info=True)


async def _migrate_plaintext_api_keys() -> None:
    """Move legacy plaintext API keys into SecretStore and clear DB plaintext."""
    from backend.app.models.llm_profile import LlmProfile
    from backend.app.models.project import Project

    store = get_secret_store()
    migrated_projects = 0
    migrated_profiles = 0

    async with SQLModelAsyncSession(engine, expire_on_commit=False) as session:
        project_result = await session.exec(select(Project))
        for project in project_result.all():
            plaintext = (project.llm_api_key or "").strip()
            if not plaintext:
                image_plaintext = (project.image_api_key or "").strip()
                if not image_plaintext:
                    continue
                project.image_api_key_ref = store.set_secret(
                    image_plaintext,
                    current_ref=project.image_api_key_ref,
                )
                project.image_api_key = None
                project.updated_at = datetime.now(timezone.utc)
                session.add(project)
                migrated_projects += 1
                continue
            project.llm_api_key_ref = store.set_secret(
                plaintext,
                current_ref=project.llm_api_key_ref,
            )
            project.llm_api_key = None
            image_plaintext = (project.image_api_key or "").strip()
            if image_plaintext:
                project.image_api_key_ref = store.set_secret(
                    image_plaintext,
                    current_ref=project.image_api_key_ref,
                )
                project.image_api_key = None
            project.updated_at = datetime.now(timezone.utc)
            session.add(project)
            migrated_projects += 1

        profile_result = await session.exec(select(LlmProfile))
        for profile in profile_result.all():
            plaintext = (profile.api_key or "").strip()
            if not plaintext:
                continue
            profile.api_key_ref = store.set_secret(
                plaintext,
                current_ref=profile.api_key_ref,
            )
            profile.api_key = None
            profile.updated_at = datetime.now(timezone.utc)
            session.add(profile)
            migrated_profiles += 1

        if migrated_projects or migrated_profiles:
            await session.commit()
            logger.info(
                "Migrated plaintext API keys into SecretStore: projects={}, profiles={}",
                migrated_projects,
                migrated_profiles,
            )
