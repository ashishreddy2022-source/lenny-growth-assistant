"""
chat.py — Streaming chat endpoint with SSE, vector retrieval, and artifact generation.

Implements architecture.md §3, §4, §5, §6:
1. Receives {session_id, message, mode, provider}
2. Embeds query & runs cosine-similarity search against transcript_chunks
3. Out-of-domain short-circuit: if 0 chunks clear 0.65 threshold, returns canned response
4. Routes to requested LLMProviderInterface (Ollama or Claude) via X-LLM-Provider / body
5. Streams tokens over Server-Sent Events (SSE)
6. If mode="ship30", validates word count band and generates an artifact in artifacts table
7. Client disconnect resilience: captures asyncio.CancelledError and saves partial message with truncated=True
"""

import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Optional
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from sse_starlette.sse import EventSourceResponse

from app.db.connection import get_db_pool
from app.db.repository import (
    create_session,
    get_session,
    get_session_messages,
    save_artifact,
    save_message,
)
from app.schemas.chat import ChatRequest
from app.services.llm.base import LLMProviderError
from app.services.llm.factory import get_llm_provider
from app.services.retrieval.citation import validate_citations
from app.services.retrieval.models import RetrievalResult
from app.services.retrieval.prompt_builder import build_grounded_prompt
from app.services.retrieval.retriever import TranscriptRetriever
from app.services.skills.ship30_writer import build_ship30_prompt, validate_ship30_essay

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger("api.chat")


def _extract_title_from_markdown(content: str, default: str) -> str:
    """Extract first H1 heading from markdown or fallback to default."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return default[:60]


@router.post("")
async def chat_endpoint(
    payload: ChatRequest,
    request: Request,
    x_llm_provider: Optional[str] = Header(None, alias="X-LLM-Provider"),
) -> EventSourceResponse:
    """
    Primary conversational endpoint. Returns an SSE stream of tokens and status events.
    """
    pool = get_db_pool()
    retriever = getattr(request.app.state, "retriever", None) or TranscriptRetriever()

    # 1. Resolve Session ID
    session_id = payload.session_id
    if pool:
        if not session_id:
            # Create new session if none provided
            new_title = payload.message[:40] + ("..." if len(payload.message) > 40 else "")
            session_row = await create_session(pool, title=new_title)
            session_id = session_row["id"]
        else:
            # Validate session exists
            existing = await get_session(pool, session_id)
            if not existing:
                session_row = await create_session(pool, title="Restored Chat")
                session_id = session_row["id"]

        # Persist user message
        await save_message(pool, session_id, role="user", content=payload.message)

    # 2. Resolve LLM Provider selection order (architecture.md §4)
    # Header > Request Body > Env > Default ("ollama")
    resolved_provider = x_llm_provider or payload.provider

    async def event_generator() -> AsyncGenerator[dict, None]:
        full_response_parts: list[str] = []
        sources: list[dict] = []
        retrieval_result: Optional[RetrievalResult] = None

        try:
            # --- Status: Retrieving ---
            yield {
                "event": "status",
                "data": json.dumps({"status": "retrieving", "message": "Searching podcast transcripts..."}),
            }

            # 3. Vector Retrieval
            if pool:
                async with pool.acquire() as conn:
                    retrieval_result = await retriever.search_async(payload.message, conn=conn)
            else:
                # Mock or standalone mode if DB not yet connected
                retrieval_result = RetrievalResult(
                    query=payload.message,
                    chunks=[],
                    is_out_of_domain=True,
                    canned_response=retriever.similarity_threshold,
                )

            sources = retrieval_result.sources

            # --- Architecture §3 Step 4: Out-of-Domain Short-Circuit ---
            if retrieval_result.is_out_of_domain:
                canned = retrieval_result.canned_response or "No relevant information found."
                logger.info("Out-of-domain short-circuit triggered for query: %s", payload.message)

                yield {
                    "event": "status",
                    "data": json.dumps({"status": "out_of_domain"}),
                }
                yield {
                    "event": "token",
                    "data": json.dumps({"token": canned}),
                }

                # Persist canned response
                msg_id = None
                if pool and session_id:
                    saved = await save_message(
                        pool, session_id, role="assistant", content=canned, sources=[]
                    )
                    msg_id = str(saved["id"])

                yield {
                    "event": "done",
                    "data": json.dumps({
                        "message_id": msg_id,
                        "session_id": str(session_id) if session_id else None,
                        "sources": [],
                        "is_out_of_domain": True,
                        "citation_validation": {
                            "valid": True,
                            "has_citations": False,
                            "warning_badge": False,
                        },
                    }),
                }
                return

            # --- Emit Sources ---
            yield {
                "event": "sources",
                "data": json.dumps({"sources": sources}),
            }

            # --- Status: Generating ---
            yield {
                "event": "status",
                "data": json.dumps({"status": "generating", "message": "Synthesizing answer..."}),
            }

            # 4. Resolve Provider and Construct Grounded Prompt
            provider_instance = get_llm_provider(resolved_provider)

            if payload.mode == "ship30":
                system_prompt, messages = build_ship30_prompt(
                    payload.message, retrieval_result.chunks
                )
            else:
                # Fetch recent conversation history if session exists
                history = []
                if pool and session_id:
                    history = await get_session_messages(pool, session_id)
                system_prompt, messages = build_grounded_prompt(
                    payload.message, retrieval_result.chunks, conversation_history=history
                )

            # 5. Stream Tokens from Provider
            async for token in provider_instance.generate_response(
                messages=messages,
                system_prompt=system_prompt,
                temperature=0.3,
            ):
                full_response_parts.append(token)
                yield {
                    "event": "token",
                    "data": json.dumps({"token": token}),
                }

            full_response = "".join(full_response_parts)

            # 6. Post-Processing: Citation Validation & Artifact Generation
            citation_res = validate_citations(full_response, retrieval_result.chunks)
            citation_data = {
                "valid": citation_res.valid,
                "has_citations": citation_res.has_citations,
                "warning_badge": citation_res.warning_badge,
                "warning_message": citation_res.warning_message,
            }

            # Persist assistant response
            msg_id = None
            if pool and session_id:
                saved = await save_message(
                    pool, session_id, role="assistant", content=full_response, sources=sources
                )
                msg_id = str(saved["id"])

            # 7. Artifact Handling (mode="ship30" or markdown document generated)
            if payload.mode == "ship30" and msg_id:
                essay_meta = validate_ship30_essay(full_response)
                artifact_title = _extract_title_from_markdown(full_response, f"Ship 30: {payload.message}")
                
                artifact_row = await save_artifact(
                    pool,
                    UUID(msg_id),
                    artifact_type="markdown",
                    title=artifact_title,
                    content=full_response,
                )

                yield {
                    "event": "artifact",
                    "data": json.dumps({
                        "id": str(artifact_row["id"]),
                        "message_id": msg_id,
                        "artifact_type": "markdown",
                        "title": artifact_title,
                        "content": full_response,
                        "word_count_meta": essay_meta,
                    }),
                }

            # --- Done Event ---
            yield {
                "event": "done",
                "data": json.dumps({
                    "message_id": msg_id,
                    "session_id": str(session_id) if session_id else None,
                    "sources": sources,
                    "is_out_of_domain": False,
                    "citation_validation": citation_data,
                    "provider": provider_instance.provider_name,
                    "model": provider_instance.model_name,
                }),
            }

        except asyncio.CancelledError:
            # Architecture §6: Handle client disconnect mid-stream
            logger.warning("Streaming client disconnected mid-response for session %s", session_id)
            if pool and session_id and full_response_parts:
                partial_text = "".join(full_response_parts)
                await save_message(
                    pool, session_id, role="assistant", content=partial_text, sources=sources, truncated=True
                )
            raise

        except LLMProviderError as exc:
            logger.error("LLM provider failure during streaming: %s", exc)
            yield {
                "event": "error",
                "data": json.dumps({
                    "error": str(exc),
                    "provider": exc.provider,
                    "status_code": exc.status_code,
                }),
            }

        except Exception as exc:
            logger.error("Unexpected error in chat stream: %s", exc, exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({"error": f"Internal error: {str(exc)}"}),
            }

    return EventSourceResponse(event_generator())
