"""
connection.py — Database pool management with retry/backoff.

Implements architecture.md §6:
- asyncpg connection pool with exponential backoff (3 attempts)
- Graceful degradation: app still starts if DB is down, enabling health probe reporting
"""

import asyncio
import logging
import os
from typing import Optional

import asyncpg

logger = logging.getLogger("db.connection")

_POOL: Optional[asyncpg.Pool] = None


async def init_db_pool(
    database_url: Optional[str] = None,
    min_size: int = 2,
    max_size: int = 10,
    max_retries: int = 3,
    base_delay: float = 1.0,
) -> Optional[asyncpg.Pool]:
    """
    Initialize global asyncpg pool with exponential backoff.
    """
    global _POOL
    url = database_url or os.getenv("DATABASE_URL")
    if not url:
        logger.warning("DATABASE_URL is not set. Database operations will be unavailable.")
        return None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Connecting to PostgreSQL (attempt %d/%d)...", attempt, max_retries)
            _POOL = await asyncpg.create_pool(
                dsn=url,
                min_size=min_size,
                max_size=max_size,
                timeout=10.0,
                command_timeout=30.0,
            )
            logger.info("PostgreSQL connection pool established.")
            return _POOL
        except Exception as exc:
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Failed to connect to PostgreSQL on attempt %d: %s. Retrying in %.1fs...",
                attempt, exc, delay
            )
            if attempt < max_retries:
                await asyncio.sleep(delay)

    logger.error("Could not establish PostgreSQL connection after %d attempts. Running in degraded mode.", max_retries)
    _POOL = None
    return None


def get_db_pool() -> Optional[asyncpg.Pool]:
    """Get the current asyncpg connection pool instance."""
    return _POOL


def set_db_pool(pool: Optional[asyncpg.Pool]) -> None:
    """Set the pool explicitly (used in test fixtures)."""
    global _POOL
    _POOL = pool


async def close_db_pool() -> None:
    """Close all connections in the pool."""
    global _POOL
    if _POOL is not None:
        logger.info("Closing PostgreSQL connection pool...")
        await _POOL.close()
        _POOL = None
