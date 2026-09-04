"""
Retrieval package initialization.
"""

from app.services.retrieval.citation import CitationValidationResult, validate_citations
from app.services.retrieval.models import RetrievedChunk, RetrievalResult, SourceRef
from app.services.retrieval.prompt_builder import build_grounded_prompt
from app.services.retrieval.retriever import (
    CANNED_OUT_OF_DOMAIN_RESPONSE,
    TranscriptRetriever,
)

__all__ = [
    "RetrievedChunk",
    "RetrievalResult",
    "SourceRef",
    "TranscriptRetriever",
    "CANNED_OUT_OF_DOMAIN_RESPONSE",
    "validate_citations",
    "CitationValidationResult",
    "build_grounded_prompt",
]
