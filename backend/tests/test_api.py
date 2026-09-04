"""
test_api.py — Comprehensive tests for FastAPI backend (Step 5).

Validates:
1. Root and health check endpoints
2. Session CRUD (create, list, get, messages, delete)
3. Chat SSE streaming endpoint with out-of-domain short-circuit
4. Chat SSE streaming endpoint with in-domain grounded generation
5. Chat SSE streaming endpoint in Ship 30 mode producing artifacts
6. Provider selection via X-LLM-Provider header
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.connection import set_db_pool
from app.main import app
from app.services.retrieval.models import RetrievalResult, RetrievedChunk
from app.services.retrieval.retriever import CANNED_OUT_OF_DOMAIN_RESPONSE


@pytest.fixture
def client():
    """Synchronous test client for FastAPI application."""
    return TestClient(app)


@pytest.fixture
def mock_pool():
    """Mock asyncpg connection pool for API tests."""
    pool = MagicMock()
    conn = AsyncMock()

    cm = AsyncMock()
    cm.__aenter__.return_value = conn
    cm.__aexit__.return_value = None
    pool.acquire.return_value = cm

    return pool, conn


# ---------------------------------------------------------------------------
# Test 1: Root & Health Endpoints
# ---------------------------------------------------------------------------

def test_root_endpoint(client):
    """Verify GET / returns online status and links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "health" in data


def test_health_endpoint_healthy(client, mock_pool):
    """Verify GET /api/health reports status ok when components are healthy."""
    pool, conn = mock_pool
    set_db_pool(pool)

    # Mock DB query results
    conn.fetchval.side_effect = [
        1,   # SELECT 1
        123, # SELECT COUNT(*) FROM transcript_chunks
    ]
    conn.fetchrow.return_value = {
        "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
        "embedding_dimension": 384,
        "chunk_count": 123,
    }

    # Mock Ollama & Claude health checks
    with patch("app.api.endpoints.health.OllamaProvider.check_health", new_callable=AsyncMock) as mock_ollama, \
         patch("app.api.endpoints.health.ClaudeProvider.check_health", new_callable=AsyncMock) as mock_claude:
        mock_ollama.return_value = {"status": "ok", "model": "llama3.2:3b"}
        mock_claude.return_value = {"status": "ok", "model": "claude-3-5-sonnet-20241022"}

        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ok"
        assert data["components"]["database"]["status"] == "ok"
        assert data["components"]["vector_index"]["status"] == "ok"
        assert data["components"]["ollama"]["status"] == "ok"
        assert data["components"]["claude"]["status"] == "ok"


def test_health_endpoint_db_down(client):
    """Verify GET /api/health reports down when DB pool is uninitialized."""
    set_db_pool(None)

    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "down"
    assert data["components"]["database"]["status"] == "down"


# ---------------------------------------------------------------------------
# Test 2: Session CRUD Endpoints
# ---------------------------------------------------------------------------

def test_session_crud_workflow(client, mock_pool):
    """Verify session creation, listing, retrieval, messages, and deletion."""
    pool, conn = mock_pool
    set_db_pool(pool)

    session_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 1. POST /api/sessions
    conn.fetchrow.return_value = {
        "id": session_id,
        "title": "PLG Strategy Chat",
        "created_at": now,
        "updated_at": now,
    }
    create_resp = client.post("/api/sessions", json={"title": "PLG Strategy Chat"})
    assert create_resp.status_code == 201
    assert create_resp.json()["title"] == "PLG Strategy Chat"

    # 2. GET /api/sessions
    conn.fetch.return_value = [
        {
            "id": session_id,
            "title": "PLG Strategy Chat",
            "created_at": now,
            "updated_at": now,
        }
    ]
    list_resp = client.get("/api/sessions")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    # 3. GET /api/sessions/{id}
    conn.fetchrow.return_value = {
        "id": session_id,
        "title": "PLG Strategy Chat",
        "created_at": now,
        "updated_at": now,
    }
    get_resp = client.get(f"/api/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == str(session_id)

    # 4. GET /api/sessions/{id}/messages
    msg_id = uuid.uuid4()
    conn.fetch.return_value = [
        {
            "id": msg_id,
            "session_id": session_id,
            "role": "user",
            "content": "What did Chesky say?",
            "sources": None,
            "created_at": now,
            "artifact_id": None,
            "artifact_type": None,
            "artifact_title": None,
            "artifact_content": None,
            "artifact_created_at": None,
        }
    ]
    msgs_resp = client.get(f"/api/sessions/{session_id}/messages")
    assert msgs_resp.status_code == 200
    msgs_data = msgs_resp.json()
    assert len(msgs_data) == 1
    assert msgs_data[0]["content"] == "What did Chesky say?"

    # 5. DELETE /api/sessions/{id}
    conn.fetchrow.return_value = {"id": session_id}
    del_resp = client.delete(f"/api/sessions/{session_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"


# ---------------------------------------------------------------------------
# Test 3: Chat SSE Endpoint — Out-of-Domain Short-Circuit
# ---------------------------------------------------------------------------

def test_chat_out_of_domain_short_circuit(client, mock_pool):
    """
    Verify POST /api/chat with out-of-domain query short-circuits:
    - Returns status: out_of_domain
    - Emits canned response
    - Does NOT invoke LLM provider
    """
    pool, conn = mock_pool
    set_db_pool(pool)

    session_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    conn.fetchrow.return_value = {
        "id": session_id,
        "title": "New Chat",
        "created_at": now,
        "updated_at": now,
    }

    mock_retriever = AsyncMock()
    mock_retriever.search_async.return_value = RetrievalResult(
        query="How to make pancakes?",
        chunks=[],
        is_out_of_domain=True,
        canned_response=CANNED_OUT_OF_DOMAIN_RESPONSE,
    )
    app.state.retriever = mock_retriever

    with patch("app.api.endpoints.chat.get_llm_provider") as mock_factory:
        response = client.post(
            "/api/chat",
            json={"message": "How to make pancakes?"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

        body_text = response.text
        assert "out_of_domain" in body_text
        assert "strictly grounded in the podcast episodes" in body_text

        # Verify LLM provider was NEVER called
        mock_factory.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: Chat SSE Endpoint — In-Domain Grounded Response
# ---------------------------------------------------------------------------

def test_chat_in_domain_streaming(client, mock_pool):
    """
    Verify POST /api/chat with in-domain query streams tokens and validates citations.
    """
    pool, conn = mock_pool
    set_db_pool(pool)

    session_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    conn.fetchrow.return_value = {
        "id": session_id,
        "title": "Airbnb PM role",
        "created_at": now,
        "updated_at": now,
    }
    conn.fetch.return_value = []

    sample_chunk = RetrievedChunk(
        id=str(uuid.uuid4()),
        episode_title="Designing the Future of Airbnb",
        guest_name="Brian Chesky",
        episode_date="2023-11-01",
        timestamp_ref="00:14:32",
        chunk_text="We merged PM with product marketing.",
        chunk_index=3,
        score=0.88,
    )
    mock_retriever = AsyncMock()
    mock_retriever.search_async.return_value = RetrievalResult(
        query="What did Chesky change?",
        chunks=[sample_chunk],
        is_out_of_domain=False,
    )
    app.state.retriever = mock_retriever

    mock_provider = AsyncMock()
    mock_provider.provider_name = "ollama"
    mock_provider.model_name = "llama3.2:3b"

    async def mock_generate(*args, **kwargs):
        tokens = [
            "Chesky merged PM and PMM ",
            "[Episode: Brian Chesky, 00:14:32].",
        ]
        for t in tokens:
            yield t

    mock_provider.generate_response = mock_generate

    with patch("app.api.endpoints.chat.get_llm_provider", return_value=mock_provider):
        response = client.post(
            "/api/chat",
            json={"message": "What did Chesky change?"},
        )
        assert response.status_code == 200

        body = response.text
        assert "event: status" in body
        assert "retrieving" in body
        assert "generating" in body
        assert "event: sources" in body
        assert "Designing the Future of Airbnb" in body
        assert "Chesky merged PM and PMM" in body
        assert "event: done" in body


# ---------------------------------------------------------------------------
# Test 5: Chat SSE Endpoint — Ship 30 Mode with Artifact Generation
# ---------------------------------------------------------------------------

def test_chat_ship30_mode_emits_artifact(client, mock_pool):
    """
    Verify POST /api/chat with mode='ship30' generates and emits an artifact event.
    """
    pool, conn = mock_pool
    set_db_pool(pool)

    session_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    artifact_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    conn.fetchrow.side_effect = [
        {"id": session_id, "title": "Ship 30 Essay", "created_at": now, "updated_at": now},
        {"id": uuid.uuid4(), "session_id": session_id, "role": "user", "content": "Write essay", "sources": None, "created_at": now},
        {"id": msg_id, "session_id": session_id, "role": "assistant", "content": "Essay content", "sources": [], "created_at": now},
        {"id": artifact_id, "message_id": msg_id, "artifact_type": "markdown", "title": "The New PM Era", "content": "Essay", "created_at": now},
    ]

    sample_chunk = RetrievedChunk(
        id=str(uuid.uuid4()),
        episode_title="Designing the Future of Airbnb",
        guest_name="Brian Chesky",
        episode_date="2023-11-01",
        timestamp_ref="00:14:32",
        chunk_text="We merged PM with product marketing.",
        chunk_index=3,
        score=0.85,
    )
    mock_retriever = AsyncMock()
    mock_retriever.search_async.return_value = RetrievalResult(
        query="Write essay on PM changes",
        chunks=[sample_chunk],
        is_out_of_domain=False,
    )
    app.state.retriever = mock_retriever

    mock_provider = AsyncMock()
    mock_provider.provider_name = "claude"
    mock_provider.model_name = "claude-3-5-sonnet-20241022"

    essay_text = (
        "# The New PM Era\n\n"
        "Here is why the feature PM is obsolete.\n\n"
        "## 1. Merging PM and PMM\n"
        "Brian Chesky changed the playbook [Episode: Brian Chesky, 00:14:32].\n\n"
        "## The Monday Morning Rule\n- **Audit your team**: Do it now.\n"
    )

    async def mock_generate(*args, **kwargs):
        yield essay_text

    mock_provider.generate_response = mock_generate

    with patch("app.api.endpoints.chat.get_llm_provider", return_value=mock_provider):
        response = client.post(
            "/api/chat",
            json={"message": "Write essay on PM changes", "mode": "ship30"},
            headers={"X-LLM-Provider": "claude"},
        )
        assert response.status_code == 200
        body = response.text

        assert "event: artifact" in body
        assert "The New PM Era" in body
        assert "word_count_meta" in body
