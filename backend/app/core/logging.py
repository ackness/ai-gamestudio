"""Loguru logging configuration.

Configures loguru as the sole logging backend, intercepting stdlib ``logging``
so that third-party libraries (uvicorn, sqlalchemy, litellm …) also flow
through the same sink.
"""
from __future__ import annotations

import logging
import sys

from loguru import logger


class _InterceptHandler(logging.Handler):
    """Bridge stdlib logging → loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        # Find caller from where the logged message originated
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(log_dir: str = "data/logs") -> None:
    """Call once at application startup (in lifespan)."""
    # Remove loguru default handler
    logger.remove()

    # Console sink — human-friendly, coloured
    logger.add(
        sys.stderr,
        level="DEBUG",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
    )

    # File sink — rotated daily, kept 30 days
    logger.add(
        f"{log_dir}/app_{{time:YYYY-MM-DD}}.log",
        level="INFO",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level:<8} | "
            "{name}:{function}:{line} — {message}"
        ),
    )

    # Intercept stdlib logging
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    # Silence noisy third-party loggers
    for name in (
        "httpcore", "httpx", "hpack",
        "LiteLLM", "LiteLLM Router", "LiteLLM Proxy",
        "sqlalchemy", "sqlalchemy.engine", "aiosqlite",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
