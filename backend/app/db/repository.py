"""
repository.py — Data access functions for sessions, messages, artifacts, and health.

All operations use parameterized queries against PostgreSQL via asyncpg.
"""

import json
import logging
from typing import Any, Optional
from uuid import UUID, uuid4

import asyncpg

logger = logging.getLogger("db.repository")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

async def create_session(pool: asyncpg.Pool, title: Optional[str] = None) -> dict[str, Any]:
    """Create a new chat session."""
    session_title = title or "New Chat"
    query = """
        INSERT INTO sessions (title)
        VALUES ($1)
        RETURNING id, title, created_at, updated_at;
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, session_title)
        return dict(row)


async def list_sessions(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """List all chat sessions ordered by most recently updated."""
    query = """
        SELECT id, title, created_at, updated_at
        FROM sessions
        ORDER BY updated_at DESC;
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        return [dict(r) for r in rows]


async def get_session(pool: asyncpg.Pool, session_id: UUID) -> Optional[dict[str, Any]]:
    """Get a single chat session by ID."""
    query = """
        SELECT id, title, created_at, updated_at
        FROM sessions
        WHERE id = $1;
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, session_id)
        return dict(row) if row else None


async def update_session_title(pool: asyncpg.Pool, session_id: UUID, title: str) -> Optional[dict[str, Any]]:
    """Update session title and touch updated_at."""
    query = """
        UPDATE sessions
        SET title = $2, updated_at = NOW()
        WHERE id = $1
        RETURNING id, title, created_at, updated_at;
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, session_id, title)
        return dict(row) if row else None


async def touch_session(pool: asyncpg.Pool, session_id: UUID) -> None:
    """Touch updated_at on session."""
    query = "UPDATE sessions SET updated_at = NOW() WHERE id = $1;"
    async with pool.acquire() as conn:
        await conn.execute(query, session_id)


async def delete_session(pool: asyncpg.Pool, session_id: UUID) -> bool:
    """Delete a session (cascades to messages and artifacts)."""
    query = "DELETE FROM sessions WHERE id = $1 RETURNING id;"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, session_id)
        return bool(row)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

async def save_message(
    pool: asyncpg.Pool,
    session_id: UUID,
    role: str,
    content: str,
    sources: Optional[list[dict[str, Any]]] = None,
    truncated: bool = False,
) -> dict[str, Any]:
    """
    Persist a user or assistant message.
    Handles partial streaming disconnects by tagging sources with truncated: true.
    """
    sources_data = sources or []
    if truncated:
        # Tag provenance with truncated per architecture.md §6
        sources_payload = json.dumps({"sources": sources_data, "truncated": True})
    else:
        sources_payload = json.dumps(sources_data)

    query = """
        INSERT INTO messages (session_id, role, content, sources)
        VALUES ($1, $2, $3, $4::jsonb)
        RETURNING id, session_id, role, content, sources, created_at;
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, session_id, role, content, sources_payload)
        await conn.execute("UPDATE sessions SET updated_at = NOW() WHERE id = $1;", session_id)
        
        result = dict(row)
        if isinstance(result.get("sources"), str):
            result["sources"] = json.loads(result["sources"])
        return result


async def get_session_messages(pool: asyncpg.Pool, session_id: UUID) -> list[dict[str, Any]]:
    """
    Get all messages for a session in chronological order, with attached artifacts if any.
    """
    query = """
        SELECT
            m.id,
            m.session_id,
            m.role,
            m.content,
            m.sources,
            m.created_at,
            a.id AS artifact_id,
            a.artifact_type,
            a.title AS artifact_title,
            a.content AS artifact_content,
            a.created_at AS artifact_created_at
        FROM messages m
        LEFT JOIN artifacts a ON m.id = a.message_id
        WHERE m.session_id = $1
        ORDER BY m.created_at ASC;
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, session_id)
        messages = []
        for r in rows:
            sources_val = r["sources"]
            if isinstance(sources_val, str):
                try:
                    sources_val = json.loads(sources_val)
                except Exception:
                    sources_val = None

            artifact_dict = None
            if r["artifact_id"]:
                artifact_dict = {
                    "id": r["artifact_id"],
                    "message_id": r["id"],
                    "artifact_type": r["artifact_type"],
                    "title": r["artifact_title"],
                    "content": r["artifact_content"],
                    "created_at": r["artifact_created_at"],
                }

            messages.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "role": r["role"],
                "content": r["content"],
                "sources": sources_val,
                "created_at": r["created_at"],
                "artifact": artifact_dict,
            })
        return messages


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

async def save_artifact(
    pool: asyncpg.Pool,
    message_id: UUID,
    artifact_type: str,
    title: str,
    content: str,
) -> dict[str, Any]:
    """Persist generated artifact (markdown or html)."""
    query = """
        INSERT INTO artifacts (message_id, artifact_type, title, content)
        VALUES ($1, $2, $3, $4)
        RETURNING id, message_id, artifact_type, title, content, created_at;
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, message_id, artifact_type, title, content)
        return dict(row)


# ---------------------------------------------------------------------------
# Health Probes
# ---------------------------------------------------------------------------

async def probe_database_and_vectors(pool: Optional[asyncpg.Pool]) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Probe PostgreSQL database and pgvector transcript_chunks table.
    Returns (db_health, vector_health).
    """
    if pool is None:
        return (
            {"status": "down", "details": "Database connection pool is not initialized"},
            {"status": "down", "details": "Database connection is unavailable"},
        )

    try:
        async with pool.acquire() as conn:
            # 1. Probe basic query execution
            await conn.fetchval("SELECT 1;")
            db_health = {"status": "ok", "details": "PostgreSQL connection pool healthy"}

            # 2. Probe transcript_chunks and corpus_metadata
            chunk_count = await conn.fetchval("SELECT COUNT(*) FROM transcript_chunks;")
            metadata_row = await conn.fetchrow(
                "SELECT embedding_model, embedding_dimension, chunk_count FROM corpus_metadata ORDER BY ingested_at DESC LIMIT 1;"
            )

            if metadata_row:
                vector_health = {
                    "status": "ok" if chunk_count > 0 else "degraded",
                    "details": f"{chunk_count} chunks indexed with {metadata_row['embedding_model']}",
                    "meta": {
                        "chunk_count": chunk_count,
                        "model": metadata_row["embedding_model"],
                        "dimension": metadata_row["embedding_dimension"],
                    },
                }
            else:
                vector_health = {
                    "status": "degraded",
                    "details": f"{chunk_count} chunks found, but corpus_metadata is empty. Run ingestion.",
                    "meta": {"chunk_count": chunk_count},
                }

            return db_health, vector_health

    except Exception as exc:
        logger.error("Health probe error: %s", exc)
        return (
            {"status": "down", "details": f"Database error: {str(exc)}"},
            {"status": "down", "details": "Vector store unreachable"},
        )
