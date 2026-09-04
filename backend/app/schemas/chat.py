"""
schemas/chat.py — Pydantic models for API requests and responses.

Defines schemas for:
- Chat request and streaming events
- Session CRUD operations
- Message history with sources and artifacts
- Deep health check breakdown
"""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sessions & Messages
# ---------------------------------------------------------------------------

class SessionCreateRequest(BaseModel):
    title: Optional[str] = Field(default="New Chat", description="Optional title for the chat session")


class SessionResponse(BaseModel):
    id: UUID
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ArtifactResponse(BaseModel):
    id: UUID
    message_id: UUID
    artifact_type: Literal["markdown", "html"]
    title: Optional[str] = None
    content: str
    created_at: datetime


class MessageResponse(BaseModel):
    id: UUID
    session_id: UUID
    role: Literal["user", "assistant"]
    content: str
    sources: Optional[list[dict[str, Any]]] = None
    created_at: datetime
    artifact: Optional[ArtifactResponse] = None


class SessionDetailResponse(BaseModel):
    session: SessionResponse
    messages: list[MessageResponse] = []


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: Optional[UUID] = Field(default=None, description="Session ID. If not provided, a new session is created.")
    message: str = Field(..., min_length=1, description="User prompt or question")
    mode: Literal["default", "ship30"] = Field(default="default", description="Execution mode: standard Q&A or Ship 30 essay generation")
    provider: Optional[str] = Field(default=None, description="Override LLM provider ('ollama' or 'claude')")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class ComponentHealth(BaseModel):
    status: Literal["ok", "degraded", "down"]
    details: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    timestamp: datetime
    components: dict[str, ComponentHealth]
