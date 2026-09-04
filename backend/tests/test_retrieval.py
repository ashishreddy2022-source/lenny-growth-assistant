"""
test_retrieval.py — Comprehensive tests for Step 4 (Retrieval, Grounding, Citations & Ship 30 Skill).

Validates:
1. TranscriptRetriever pgvector query execution and result mapping
2. Out-of-domain short-circuit (0 chunks >= 0.65 threshold returns canned response)
3. Corpus metadata consistency check on startup (fails loudly on mismatch)
4. Citation extraction, grounding verification, and UI warning badge triggers
5. Ship 30 prompt builder and post-generation word count tolerance (±15% band)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.services.retrieval.citation import (
    CitationValidationResult,
    extract_citations,
    validate_citations,
)
from app.services.retrieval.models import RetrievalResult, RetrievedChunk
from app.services.retrieval.prompt_builder import build_grounded_prompt
from app.services.retrieval.retriever import (
    CANNED_OUT_OF_DOMAIN_RESPONSE,
    CorpusMetadataMismatchError,
    TranscriptRetriever,
)
from app.services.skills.ship30_writer import (
    SHIP30_MAX_WORDS,
    SHIP30_MIN_WORDS,
    SHIP30_TARGET_WORDS,
    build_ship30_prompt,
    validate_ship30_essay,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_embedder():
    """Provides a fast mock embedder returning a dummy 384-dimensional unit vector."""
    def _embed(query: str) -> list[float]:
        vec = [0.0] * 384
        vec[0] = 1.0  # Normalized unit vector
        return vec
    return _embed


@pytest.fixture
def sample_chunks():
    """Sample retrieved chunks representing grounded podcast knowledge."""
    return [
        RetrievedChunk(
            id=str(uuid.uuid4()),
            episode_title="Designing the Future of Airbnb",
            guest_name="Brian Chesky",
            episode_date="2023-11-01",
            timestamp_ref="00:14:32",
            chunk_text="We got rid of the traditional product management function and merged PM with product marketing.",
            chunk_index=3,
            score=0.875,
        ),
        RetrievedChunk(
            id=str(uuid.uuid4()),
            episode_title="The Making of a Manager",
            guest_name="Julie Zhuo",
            episode_date="2023-08-15",
            timestamp_ref="00:22:10",
            chunk_text="Early managers often confuse giving feedback with finding fault. Great feedback is a forward-looking gift.",
            chunk_index=5,
            score=0.742,
        ),
    ]


# ---------------------------------------------------------------------------
# Test 1: Vector Search & In-Domain Retrieval
# ---------------------------------------------------------------------------

def test_retriever_sync_in_domain_results(mock_embedder):
    """Verify synchronous vector retrieval returns properly ranked chunks and sources JSONB."""
    retriever = TranscriptRetriever(
        dimension=384,
        similarity_threshold=0.65,
        top_k=5,
        embedder=mock_embedder,
    )

    # Mock DB connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [
        (
            str(uuid.uuid4()),
            "Designing the Future of Airbnb",
            "Brian Chesky",
            "2023-11-01",
            "00:14:32",
            "We merged PM with product marketing.",
            3,
            0.875,
        ),
        (
            str(uuid.uuid4()),
            "L1 to L3 Product Strategy",
            "Shreyas Doshi",
            "2023-05-10",
            "00:09:15",
            "Good product leaders distinguish between execution and strategy.",
            1,
            0.760,
        ),
    ]
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    result = retriever.search_sync("What did Chesky change about PMs?", conn=mock_conn)

    assert result.is_out_of_domain is False
    assert result.canned_response is None
    assert len(result.chunks) == 2
    assert result.chunks[0].guest_name == "Brian Chesky"
    assert result.chunks[0].score == 0.875

    # Check sources format matches architecture.md §2.2 JSONB schema
    sources = result.sources
    assert len(sources) == 2
    assert sources[0] == {
        "episode": "Designing the Future of Airbnb",
        "guest": "Brian Chesky",
        "timestamp": "00:14:32",
        "score": 0.875,
    }


@pytest.mark.asyncio
async def test_retriever_async_in_domain_results(mock_embedder):
    """Verify asynchronous vector retrieval returns ranked chunks."""
    retriever = TranscriptRetriever(
        dimension=384,
        similarity_threshold=0.65,
        top_k=3,
        embedder=mock_embedder,
    )

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [
        {
            "id": uuid.uuid4(),
            "episode_title": "Designing the Future of Airbnb",
            "guest_name": "Brian Chesky",
            "episode_date": "2023-11-01",
            "timestamp_ref": "00:14:32",
            "chunk_text": "We merged PM with product marketing.",
            "chunk_index": 3,
            "score": 0.85,
        }
    ]

    result = await retriever.search_async("Airbnb PM structure", conn=mock_conn)

    assert result.is_out_of_domain is False
    assert len(result.chunks) == 1
    assert result.chunks[0].guest_name == "Brian Chesky"


# ---------------------------------------------------------------------------
# Test 2: Out-of-Domain Short-Circuit (Architecture.md §3)
# ---------------------------------------------------------------------------

def test_retriever_out_of_domain_short_circuit_sync(mock_embedder):
    """
    Verify that when 0 chunks clear the similarity threshold, the retriever
    immediately short-circuits with canned out-of-domain response without calling LLM.
    """
    retriever = TranscriptRetriever(
        dimension=384,
        similarity_threshold=0.65,
        embedder=mock_embedder,
    )

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    # 0 chunks cleared the threshold
    mock_cursor.fetchall.return_value = []
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    result = retriever.search_sync("What is the recipe for chocolate chip cookies?", conn=mock_conn)

    assert result.is_out_of_domain is True
    assert len(result.chunks) == 0
    assert result.canned_response == CANNED_OUT_OF_DOMAIN_RESPONSE
    assert "strictly grounded in the podcast episodes" in result.canned_response


@pytest.mark.asyncio
async def test_retriever_out_of_domain_short_circuit_async(mock_embedder):
    """Verify async short-circuit behavior when no chunks match."""
    retriever = TranscriptRetriever(
        dimension=384,
        similarity_threshold=0.65,
        embedder=mock_embedder,
    )

    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = []

    result = await retriever.search_async("Who won the 1994 World Cup?", conn=mock_conn)

    assert result.is_out_of_domain is True
    assert result.chunks == []
    assert result.canned_response == CANNED_OUT_OF_DOMAIN_RESPONSE


# ---------------------------------------------------------------------------
# Test 3: Corpus Metadata Startup Validation (Architecture.md §6)
# ---------------------------------------------------------------------------

def test_corpus_metadata_verification_success():
    """Verify clean startup when database metadata matches retriever configuration."""
    retriever = TranscriptRetriever(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
    )

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ("sentence-transformers/all-MiniLM-L6-v2", 384, 123)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    res = retriever.verify_corpus_metadata(mock_conn)
    assert res["status"] == "ok"
    assert res["chunk_count"] == 123


def test_corpus_metadata_dimension_mismatch_fails_loudly():
    """Verify startup fails loudly with CorpusMetadataMismatchError on dimension mismatch."""
    retriever = TranscriptRetriever(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
    )

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    # Database was ingested with a 768d model
    mock_cursor.fetchone.return_value = ("nomic-embed-text", 768, 123)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with pytest.raises(CorpusMetadataMismatchError) as exc_info:
        retriever.verify_corpus_metadata(mock_conn)

    assert "Embedding dimension mismatch" in str(exc_info.value)
    assert "768" in str(exc_info.value)
    assert "384" in str(exc_info.value)


def test_corpus_metadata_model_mismatch_fails_loudly():
    """Verify startup fails loudly when model name differs even if dimension matches."""
    retriever = TranscriptRetriever(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
    )

    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = ("sentence-transformers/paraphrase-MiniLM-L6-v2", 384, 123)
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    with pytest.raises(CorpusMetadataMismatchError) as exc_info:
        retriever.verify_corpus_metadata(mock_conn)

    assert "Embedding model mismatch" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 4: Citation Parsing & Grounding Verification (Architecture.md §3)
# ---------------------------------------------------------------------------

def test_extract_citations_various_formats():
    """Verify regex correctly parses standard and variant citation formats."""
    text = (
        "Brian Chesky restructured Airbnb [Episode: Brian Chesky, 00:14:32]. "
        "Later, he addressed designer ratios [Brian Chesky, 00:28:10]. "
        "Julie Zhuo agreed [Ep: Julie Zhuo, Feedback Framework]."
    )
    citations = extract_citations(text)
    assert len(citations) == 3

    assert citations[0].guest_or_episode == "Brian Chesky"
    assert citations[0].timestamp_or_topic == "00:14:32"

    assert citations[1].guest_or_episode == "Brian Chesky"
    assert citations[1].timestamp_or_topic == "00:28:10"

    assert citations[2].guest_or_episode == "Julie Zhuo"
    assert citations[2].timestamp_or_topic == "Feedback Framework"


def test_validate_citations_all_grounded(sample_chunks):
    """Verify valid grounded response does not trigger warning badge."""
    response = (
        "At Airbnb, PM and PMM roles were merged into a single function [Episode: Brian Chesky, 00:14:32]. "
        "Similarly, management feedback should be forward-looking [Episode: Julie Zhuo, 00:22:10]."
    )
    result = validate_citations(response, sample_chunks)
    assert result.valid is True
    assert result.has_citations is True
    assert result.warning_badge is False
    assert len(result.citations) == 2
    assert all(c.is_grounded for c in result.citations)


def test_validate_citations_missing_citations(sample_chunks):
    """Verify response without citations triggers the UI warning badge."""
    response = "Brian Chesky merged PM and PMM into a single function without citing sources."
    result = validate_citations(response, sample_chunks)
    assert result.valid is False
    assert result.has_citations is False
    assert result.warning_badge is True
    assert "contains no source citations" in result.warning_message


def test_validate_citations_ungrounded_source(sample_chunks):
    """Verify citation referencing a guest not in the retrieved context triggers warning."""
    response = (
        "Brian Chesky merged PM and PMM [Episode: Brian Chesky, 00:14:32]. "
        "Sam Altman also mentioned founders doing sales [Episode: Sam Altman, 00:05:00]."
    )
    # sample_chunks only has Chesky and Zhuo, NOT Sam Altman
    result = validate_citations(response, sample_chunks)
    assert result.valid is False
    assert result.warning_badge is True
    assert len(result.ungrounded_citations) == 1
    assert result.ungrounded_citations[0].guest_or_episode == "Sam Altman"
    assert "not in the retrieved context" in result.warning_message


# ---------------------------------------------------------------------------
# Test 5: Grounded Prompt Builder
# ---------------------------------------------------------------------------

def test_build_grounded_prompt(sample_chunks):
    """Verify build_grounded_prompt packages sources and citation instructions."""
    system_prompt, messages = build_grounded_prompt(
        user_query="How did Airbnb change PMs?",
        chunks=sample_chunks,
        conversation_history=[
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ],
    )

    assert "Brian Chesky" in system_prompt
    assert "00:14:32" in system_prompt
    assert "[Episode: Guest Name, Timestamp]" in system_prompt
    assert len(messages) == 3
    assert messages[0] == {"role": "user", "content": "Hi"}
    assert messages[2] == {"role": "user", "content": "How did Airbnb change PMs?"}


# ---------------------------------------------------------------------------
# Test 6: Ship 30 for 30 Skill & Word Count Tolerance (Brief §4.2, PRD §5)
# ---------------------------------------------------------------------------

def test_ship30_prompt_structure(sample_chunks):
    """Verify Ship 30 prompt builder injects writing principles and retrieved context."""
    system_prompt, messages = build_ship30_prompt(
        user_query="The death of traditional product management",
        chunks=sample_chunks,
    )

    assert "Ship 30 for 30" in system_prompt
    assert "~1,250 words" in system_prompt
    assert "Monday Morning Rule" in system_prompt
    assert "Brian Chesky" in system_prompt
    assert len(messages) == 1
    assert "The death of traditional product management" in messages[0]["content"]


def test_ship30_essay_validation_in_tolerance():
    """Verify essay within ±15% band (1,062 - 1,437 words) passes with in_tolerance=True."""
    # Generate mock essay text with 1,200 words
    header = "# The Death of the Feature PM\n\n## 1. The Core Problem\n\n"
    body = "Product management is evolving into business ownership. " * 150  # ~1,200 words
    checklist = "\n\n## The Monday Morning Rule\n- **Audit your backlog**: Delete unused tickets.\n"
    content = header + body + checklist

    res = validate_ship30_essay(content)
    assert res["in_tolerance"] is True
    assert res["status"] == "in_tolerance"
    assert SHIP30_MIN_WORDS <= res["word_count"] <= SHIP30_MAX_WORDS
    assert res["has_headings"] is True
    assert res["has_bullets"] is True


def test_ship30_essay_validation_under_length():
    """Verify essay below minimum tolerance threshold is tagged under_length."""
    short_content = (
        "# Short Essay\n\n## Section\n\n"
        + "Word " * 500  # 500 words, below 1062 minimum
    )
    res = validate_ship30_essay(short_content)
    assert res["in_tolerance"] is False
    assert res["status"] == "under_length"
    assert res["word_count"] < SHIP30_MIN_WORDS


def test_ship30_essay_validation_over_length():
    """Verify essay above maximum tolerance threshold is tagged over_length."""
    long_content = (
        "# Very Long Essay\n\n## Section\n\n"
        + "Word " * 1600  # 1,600 words, above 1437 maximum
    )
    res = validate_ship30_essay(long_content)
    assert res["in_tolerance"] is False
    assert res["status"] == "over_length"
    assert res["word_count"] > SHIP30_MAX_WORDS
