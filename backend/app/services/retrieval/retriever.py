"""
retriever.py — Vector retrieval over podcast transcript chunks via pgvector.

Enforces architecture.md §3 and §6:
1. Embeds query using EMBEDDING_MODEL (enforcing ingest/retrieval consistency)
2. Runs cosine-similarity search against transcript_chunks using HNSW index
3. Hard short-circuit: if 0 chunks clear similarity_threshold (default 0.65), returns
   canned out-of-domain response without calling the LLM
4. Verifies corpus_metadata on startup to fail loudly on dimension or model mismatch
"""

import logging
import os
from typing import Any, Callable, Optional

import numpy as np

from app.services.retrieval.models import RetrievalResult, RetrievedChunk

logger = logging.getLogger("retrieval.retriever")

CANNED_OUT_OF_DOMAIN_RESPONSE = (
    "I don't have relevant information in Lenny's Podcast transcripts to answer this question. "
    "My knowledge is strictly grounded in the podcast episodes covering product management, "
    "growth tactics, and company building."
)


class CorpusMetadataMismatchError(RuntimeError):
    """Raised when the database embedding model/dimension does not match runtime configuration."""
    pass


class TranscriptRetriever:
    """
    Retriever for podcast transcripts using pgvector cosine similarity.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        dimension: Optional[int] = None,
        similarity_threshold: float = 0.65,
        top_k: int = 5,
        embedder: Optional[Callable[[str], list[float]]] = None,
        db_connection_factory: Optional[Callable[[], Any]] = None,
    ):
        self.model_name = model_name or os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        self.dimension = dimension or int(os.getenv("EMBEDDING_DIMENSION", "384"))
        self.similarity_threshold = similarity_threshold
        self.top_k = top_k
        self._custom_embedder = embedder
        self._model = None
        self._db_factory = db_connection_factory

    def _get_model(self):
        """Lazy load SentenceTransformer embedder if no custom embedder injected."""
        if self._custom_embedder:
            return None
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model for retrieval: %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_query(self, query: str) -> list[float]:
        """
        Embed a single search query into a normalized vector.
        """
        if self._custom_embedder:
            return self._custom_embedder(query)

        model = self._get_model()
        vec = model.encode(query, normalize_embeddings=True)
        if isinstance(vec, np.ndarray):
            return vec.tolist()
        return list(vec)

    def verify_corpus_metadata(self, conn) -> dict:
        """
        Verify that database corpus_metadata matches runtime embedding config.
        Fails loudly per architecture.md §6.
        """
        query = """
            SELECT embedding_model, embedding_dimension, chunk_count
            FROM corpus_metadata
            ORDER BY ingested_at DESC
            LIMIT 1;
        """
        with conn.cursor() as cur:
            cur.execute(query)
            row = cur.fetchone()

        if not row:
            logger.warning("corpus_metadata table is empty. Ensure ingestion has been run.")
            return {"status": "uninitialized"}

        # Handle tuple or dict row depending on cursor type
        if isinstance(row, dict):
            stored_model = row["embedding_model"]
            stored_dim = row["embedding_dimension"]
            chunk_count = row["chunk_count"]
        else:
            stored_model, stored_dim, chunk_count = row[0], row[1], row[2]

        if stored_dim != self.dimension:
            raise CorpusMetadataMismatchError(
                f"Embedding dimension mismatch: Database indexed with dimension {stored_dim}, "
                f"but retriever configured for {self.dimension} (model: {self.model_name}). "
                f"Re-ingest transcripts or update EMBEDDING_DIMENSION."
            )

        if stored_model != self.model_name:
            raise CorpusMetadataMismatchError(
                f"Embedding model mismatch: Database indexed with '{stored_model}', "
                f"but retriever configured for '{self.model_name}'. "
                f"Re-ingest transcripts or update EMBEDDING_MODEL."
            )

        logger.info(
            "Corpus metadata verified: model=%s, dimension=%d, chunks=%d",
            stored_model, stored_dim, chunk_count
        )
        return {
            "status": "ok",
            "model": stored_model,
            "dimension": stored_dim,
            "chunk_count": chunk_count,
        }

    async def search_async(
        self,
        query: str,
        conn,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ) -> RetrievalResult:
        """
        Asynchronously search chunks using an async connection (e.g. asyncpg or psycopg AsyncConnection).
        """
        k = top_k or self.top_k
        thresh = similarity_threshold if similarity_threshold is not None else self.similarity_threshold

        query_vec = self.embed_query(query)
        vec_str = f"[{','.join(str(x) for x in query_vec)}]"

        sql = """
            SELECT
                id,
                episode_title,
                guest_name,
                episode_date,
                timestamp_ref,
                chunk_text,
                chunk_index,
                1 - (embedding <=> $1::vector) AS score
            FROM transcript_chunks
            WHERE 1 - (embedding <=> $1::vector) >= $2
            ORDER BY score DESC
            LIMIT $3;
        """
        rows = await conn.fetch(sql, vec_str, thresh, k)

        chunks: list[RetrievedChunk] = []
        for r in rows:
            chunks.append(RetrievedChunk(
                id=str(r["id"]),
                episode_title=r["episode_title"],
                guest_name=r["guest_name"],
                episode_date=str(r["episode_date"]) if r["episode_date"] else None,
                timestamp_ref=r["timestamp_ref"],
                chunk_text=r["chunk_text"],
                chunk_index=r["chunk_index"],
                score=float(r["score"]),
            ))

        # Architecture §3 Step 4: Out-of-Domain Short-Circuit
        if not chunks:
            logger.info("Query '%s' cleared 0 chunks above threshold %.2f -> Short-circuiting", query, thresh)
            return RetrievalResult(
                query=query,
                chunks=[],
                is_out_of_domain=True,
                canned_response=CANNED_OUT_OF_DOMAIN_RESPONSE,
            )

        return RetrievalResult(
            query=query,
            chunks=chunks,
            is_out_of_domain=False,
            canned_response=None,
        )

    def search_sync(
        self,
        query: str,
        conn,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ) -> RetrievalResult:
        """
        Synchronously search chunks using a psycopg3 connection.
        """
        k = top_k or self.top_k
        thresh = similarity_threshold if similarity_threshold is not None else self.similarity_threshold

        query_vec = self.embed_query(query)
        vec_str = f"[{','.join(str(x) for x in query_vec)}]"

        sql = """
            SELECT
                id,
                episode_title,
                guest_name,
                episode_date,
                timestamp_ref,
                chunk_text,
                chunk_index,
                1 - (embedding <=> %s::vector) AS score
            FROM transcript_chunks
            WHERE 1 - (embedding <=> %s::vector) >= %s
            ORDER BY score DESC
            LIMIT %s;
        """

        with conn.cursor() as cur:
            cur.execute(sql, (vec_str, vec_str, thresh, k))
            rows = cur.fetchall()

        chunks: list[RetrievedChunk] = []
        for r in rows:
            if isinstance(r, dict):
                chunk = RetrievedChunk(
                    id=str(r["id"]),
                    episode_title=r["episode_title"],
                    guest_name=r["guest_name"],
                    episode_date=str(r["episode_date"]) if r.get("episode_date") else None,
                    timestamp_ref=r["timestamp_ref"],
                    chunk_text=r["chunk_text"],
                    chunk_index=r["chunk_index"],
                    score=float(r["score"]),
                )
            else:
                chunk = RetrievedChunk(
                    id=str(r[0]),
                    episode_title=r[1],
                    guest_name=r[2],
                    episode_date=str(r[3]) if r[3] else None,
                    timestamp_ref=r[4],
                    chunk_text=r[5],
                    chunk_index=r[6],
                    score=float(r[7]),
                )
            chunks.append(chunk)

        # Architecture §3 Step 4: Out-of-Domain Short-Circuit
        if not chunks:
            logger.info("Query '%s' cleared 0 chunks above threshold %.2f -> Short-circuiting", query, thresh)
            return RetrievalResult(
                query=query,
                chunks=[],
                is_out_of_domain=True,
                canned_response=CANNED_OUT_OF_DOMAIN_RESPONSE,
            )

        return RetrievalResult(
            query=query,
            chunks=chunks,
            is_out_of_domain=False,
            canned_response=None,
        )
