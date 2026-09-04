"""
health.py — Deep health check endpoint probing DB, Vector Store, Ollama, and Claude.

Implements architecture.md §6 and assignment brief §3.1:
- Probes real PostgreSQL connection pool
- Validates vector store and chunk count
- Probes Ollama service /api/tags
- Probes Claude configuration
"""

from datetime import datetime, timezone
import logging

from fastapi import APIRouter

from app.db.connection import get_db_pool
from app.db.repository import probe_database_and_vectors
from app.schemas.chat import ComponentHealth, HealthResponse
from app.services.llm.claude_provider import ClaudeProvider
from app.services.llm.ollama_provider import OllamaProvider

router = APIRouter(prefix="/api/health", tags=["health"])
logger = logging.getLogger("api.health")


@router.get("", response_model=HealthResponse)
async def check_health() -> HealthResponse:
    """
    Probe all system dependencies and return detailed operational status.
    """
    pool = get_db_pool()

    # 1. Probe DB and Vector index
    db_raw, vector_raw = await probe_database_and_vectors(pool)

    # 2. Probe Ollama provider
    ollama_provider = OllamaProvider()
    ollama_raw = await ollama_provider.check_health()

    # 3. Probe Claude provider
    claude_provider = ClaudeProvider()
    claude_raw = await claude_provider.check_health()

    components = {
        "database": ComponentHealth(
            status=db_raw["status"],
            details=db_raw.get("details"),
            meta=db_raw.get("meta"),
        ),
        "vector_index": ComponentHealth(
            status=vector_raw["status"],
            details=vector_raw.get("details"),
            meta=vector_raw.get("meta"),
        ),
        "ollama": ComponentHealth(
            status=ollama_raw["status"],
            details=ollama_raw.get("details"),
            meta={"model": ollama_raw.get("model")},
        ),
        "claude": ComponentHealth(
            status=claude_raw["status"],
            details=claude_raw.get("details"),
            meta={"model": claude_raw.get("model")},
        ),
    }

    # Determine overall status:
    # If DB is down, system is DOWN
    if db_raw["status"] == "down":
        overall_status = "down"
    elif vector_raw["status"] == "down" or (ollama_raw["status"] == "down" and claude_raw["status"] == "down"):
        overall_status = "down"
    elif vector_raw["status"] == "degraded" or ollama_raw["status"] == "degraded" or claude_raw["status"] == "down":
        overall_status = "degraded"
    else:
        overall_status = "ok"

    return HealthResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        components=components,
    )
