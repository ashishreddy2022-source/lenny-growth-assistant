"""
main.py — FastAPI application entry point for The Lenny Growth Assistant.

Features:
- Async lifespan event management (DB pool init/shutdown, auto schema init, corpus metadata validation)
- Permissive CORS for local Next.js frontend communication
- Standardized error handling and health probes
- Routers for chat (SSE), sessions, and health
"""

from contextlib import asynccontextmanager
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.endpoints import chat_router, health_router, sessions_router
from app.db.connection import close_db_pool, get_db_pool, init_db_pool
from app.services.retrieval.retriever import TranscriptRetriever

load_dotenv()

# Setup structured logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("main")

# Path to schema file (relative to this file's location in backend/app/)
_SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


async def _init_schema(pool) -> None:
    """
    Auto-initialize database schema on first boot.
    Reads schema.sql and runs it idempotently (all statements use IF NOT EXISTS).
    Safe to run on every startup — existing tables/indexes are never dropped.
    """
    if not _SCHEMA_PATH.exists():
        logger.warning("schema.sql not found at %s — skipping auto-init", _SCHEMA_PATH)
        return

    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    try:
        async with pool.acquire() as conn:
            await conn.execute(schema_sql)
        logger.info("Database schema initialized successfully from %s", _SCHEMA_PATH)
    except Exception as exc:
        logger.error("Schema auto-init failed: %s", exc, exc_info=True)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Initializes DB pool, auto-creates schema, checks corpus metadata, registers retriever.
    """
    logger.info("Booting The Lenny Growth Assistant API...")

    # 1. Initialize PostgreSQL connection pool
    pool = await init_db_pool()
    if pool:
        # 1a. Auto-initialize schema (idempotent — safe on every restart)
        try:
            await _init_schema(pool)
        except Exception as exc:
            logger.error("Fatal: could not initialize schema: %s", exc)

        # 1b. Check corpus metadata consistency
        try:
            async with pool.acquire() as conn:
                meta = await conn.fetchrow(
                    "SELECT embedding_model, embedding_dimension, chunk_count FROM corpus_metadata ORDER BY ingested_at DESC LIMIT 1;"
                )
                if meta:
                    logger.info(
                        "Corpus metadata check passed: model=%s, dim=%d, chunks=%d",
                        meta["embedding_model"],
                        meta["embedding_dimension"],
                        meta["chunk_count"],
                    )
                else:
                    logger.warning("corpus_metadata is empty — no transcripts ingested yet.")
        except Exception as exc:
            logger.warning("Could not probe corpus_metadata at startup: %s", exc)
    else:
        logger.warning("Starting without active PostgreSQL connection. Database endpoints will report degraded.")

    # 2. Register global retriever instance
    app.state.retriever = TranscriptRetriever()

    yield

    # Teardown
    logger.info("Shutting down The Lenny Growth Assistant API...")
    await close_db_pool()



# Create FastAPI application
app = FastAPI(
    title="The Lenny Growth Assistant API",
    description="Conversational assistant and Ship 30 essay engine grounded in Lenny's Podcast transcripts.",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS for Next.js frontend
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Register endpoint routers
app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(chat_router)


@app.api_route("/", methods=["GET", "HEAD"], tags=["root"])
async def root():
    return {
        "app": "The Lenny Growth Assistant API",
        "status": "online",
        "docs": "/docs",
        "health": "/api/health",
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal server error", "detail": str(exc)},
    )
