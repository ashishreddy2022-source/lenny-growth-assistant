"""
sessions.py — Session CRUD endpoints for chat session management.

Enforces architecture.md §2.2 and assignment brief §3.1:
- Create new chat session
- List existing sessions
- Retrieve message history with sources and artifacts
- Delete session
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.db.connection import get_db_pool
from app.db.repository import (
    create_session,
    delete_session,
    get_session,
    get_session_messages,
    list_sessions,
)
from app.schemas.chat import (
    MessageResponse,
    SessionCreateRequest,
    SessionResponse,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _require_pool():
    pool = get_db_pool()
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection is unavailable. Check server logs.",
        )
    return pool


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_new_session(payload: Optional[SessionCreateRequest] = None) -> SessionResponse:
    """Create a new conversational session."""
    pool = _require_pool()
    title = payload.title if payload else "New Chat"
    row = await create_session(pool, title=title)
    return SessionResponse(**row)


@router.get("", response_model=list[SessionResponse])
async def get_all_sessions() -> list[SessionResponse]:
    """List all sessions ordered by last update time."""
    pool = _require_pool()
    rows = await list_sessions(pool)
    return [SessionResponse(**r) for r in rows]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_single_session(session_id: UUID) -> SessionResponse:
    """Retrieve details for a specific session."""
    pool = _require_pool()
    row = await get_session(pool, session_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return SessionResponse(**row)


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages_for_session(session_id: UUID) -> list[MessageResponse]:
    """Retrieve chronological message history for a session."""
    pool = _require_pool()
    # Check session exists
    session = await get_session(pool, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )

    rows = await get_session_messages(pool, session_id)
    return [MessageResponse(**r) for r in rows]


@router.delete("/{session_id}", status_code=status.HTTP_200_OK)
async def delete_single_session(session_id: UUID) -> dict:
    """Delete a session and cascade delete its messages and artifacts."""
    pool = _require_pool()
    deleted = await delete_session(pool, session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    return {"status": "deleted", "id": str(session_id)}
