"""Database connection pool and query helpers using asyncpg (Neon Postgres)."""

import json
import asyncpg
import structlog
from contextlib import asynccontextmanager
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from app.core.config import get_settings

logger = structlog.get_logger()

# Global connection pool
_pool: asyncpg.Pool | None = None

# Parameters in the DSN that asyncpg doesn't understand (libpq-only)
_UNSUPPORTED_DSN_PARAMS = {"channel_binding"}


def _clean_dsn(dsn: str) -> str:
    """Remove libpq-only parameters that asyncpg cannot handle."""
    parsed = urlparse(dsn)
    params = parse_qs(parsed.query)
    cleaned = {k: v for k, v in params.items() if k not in _UNSUPPORTED_DSN_PARAMS}
    # parse_qs returns lists; flatten single values for urlencode
    flat = {k: v[0] if len(v) == 1 else v for k, v in cleaned.items()}
    new_query = urlencode(flat, doseq=True)
    return urlunparse(parsed._replace(query=new_query))


async def init_pool() -> asyncpg.Pool:
    """Initialize the connection pool. Called on app startup."""
    global _pool
    settings = get_settings()
    dsn = _clean_dsn(settings.database_url)
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    logger.info("database_pool_initialized", dsn=dsn[:40] + "...")
    return _pool


async def close_pool():
    """Close the connection pool. Called on app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("database_pool_closed")


def get_pool() -> asyncpg.Pool:
    """Get the current connection pool."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")
    return _pool


@asynccontextmanager
async def get_connection():
    """Get a connection from the pool as async context manager."""
    pool = get_pool()
    async with pool.acquire() as conn:
        yield conn


# ============================================
# Query Helpers
# ============================================

async def fetch_all(query: str, *args) -> list[dict]:
    """Execute a query and return all rows as dicts."""
    async with get_connection() as conn:
        rows = await conn.fetch(query, *args)
        return [dict(row) for row in rows]


async def fetch_one(query: str, *args) -> dict | None:
    """Execute a query and return the first row as dict."""
    async with get_connection() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def fetch_val(query: str, *args):
    """Execute a query and return a single value."""
    async with get_connection() as conn:
        return await conn.fetchval(query, *args)


async def execute(query: str, *args) -> str:
    """Execute a query (INSERT/UPDATE/DELETE) and return status."""
    async with get_connection() as conn:
        return await conn.execute(query, *args)


async def execute_returning(query: str, *args) -> dict | None:
    """Execute an INSERT/UPDATE with RETURNING and return the row."""
    async with get_connection() as conn:
        row = await conn.fetchrow(query, *args)
        return dict(row) if row else None


async def execute_many(query: str, args_list: list) -> None:
    """Execute a query for multiple parameter sets."""
    async with get_connection() as conn:
        await conn.executemany(query, args_list)


# ============================================
# Vector Search (pgvector)
# ============================================

async def vector_search(
    query_embedding: list[float],
    match_count: int = 10,
    filter_sector: str | None = None,
    filter_layer: int | None = None,
    filter_category: str | None = None,
    similarity_threshold: float = 0.7,
) -> list[dict]:
    """
    Search knowledge base using vector similarity.
    Calls the match_knowledge_chunks database function.
    """
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM match_knowledge_chunks(
                $1::vector(1024), $2, $3::float, $4, $5, $6
            )
            """,
            embedding_str,
            match_count,
            similarity_threshold,
            filter_sector,
            filter_layer,
            filter_category,
        )
        return [dict(row) for row in rows]
