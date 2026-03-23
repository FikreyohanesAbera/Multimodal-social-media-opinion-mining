# app/db/pool.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import asyncpg
from asyncpg import Pool, Connection

from app.config import settings

logger = logging.getLogger(__name__)

_pool: Pool | None = None


async def init_pool() -> None:
    """Create the asyncpg connection pool. Call once at startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=20,
        command_timeout=30,
        ssl="require" if settings.is_production else None,
    )
    logger.info("[DB] Connection pool initialised")


async def close_pool() -> None:
    """Gracefully close the pool. Call at shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("[DB] Connection pool closed")


def get_pool() -> Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialised. Call init_pool() first.")
    return _pool


async def fetch(query: str, *args: Any) -> list[asyncpg.Record]:
    """Fetch multiple rows."""
    async with get_pool().acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    """Fetch a single row."""
    async with get_pool().acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query: str, *args: Any) -> str:
    """Execute a statement (INSERT / UPDATE / DELETE)."""
    async with get_pool().acquire() as conn:
        return await conn.execute(query, *args)


@asynccontextmanager
async def transaction() -> AsyncGenerator[Connection, None]:
    """Async context manager that provides a connection inside a transaction."""
    async with get_pool().acquire() as conn:
        async with conn.transaction():
            yield conn
