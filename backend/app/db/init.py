"""CLI script to initialize the database.

Usage:
    python -m backend.app.db.init
"""
from __future__ import annotations

import asyncio
import pathlib


async def main() -> None:
    # Ensure data/ directory exists
    data_dir = pathlib.Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)

    from backend.app.db.engine import init_db

    await init_db()
    print("Database initialized successfully.")


if __name__ == "__main__":
    asyncio.run(main())
