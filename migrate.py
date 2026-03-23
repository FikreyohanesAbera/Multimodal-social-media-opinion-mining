#!/usr/bin/env python3
# app/db/migrate.py
"""
Run SQL migrations from the /migrations directory in order.
Usage: python -m app.db.migrate
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import asyncpg

from app.config import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "migrations"


async def migrate() -> None:
    conn = await asyncpg.connect(dsn=settings.database_url)

    try:
        # Ensure tracking table exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                id          SERIAL PRIMARY KEY,
                filename    VARCHAR(255) UNIQUE NOT NULL,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

        for filepath in migration_files:
            filename = filepath.name

            exists = await conn.fetchval(
                "SELECT id FROM _migrations WHERE filename = $1", filename
            )
            if exists:
                logger.info(f"[migrate] Skipping {filename} (already applied)")
                continue

            sql = filepath.read_text(encoding="utf-8")
            logger.info(f"[migrate] Applying {filename}...")

            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO _migrations (filename) VALUES ($1)", filename
                )

            logger.info(f"[migrate] ✓ {filename}")

        logger.info("[migrate] All migrations applied successfully.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
