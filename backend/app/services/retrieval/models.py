"""
models.py — Data structures for retrieval pipeline.

Adheres to architecture.md §2.1 and §2.2 data contracts:
- RetrievedChunk represents a chunk retrieved from transcript_chunks
- SourceRef represents the JSONB schema stored on messages
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from uuid import UUID


@dataclass
class RetrievedChunk:
    """Represents a transcript chunk retrieved from pgvector."""
    id: str
    episode_title: str
    guest_name: str
    episode_date: Optional[str]
    timestamp_ref: str
    chunk_text: str
    chunk_index: int
    score: float  # Cosine similarity score (0.0 to 1.0)

    def to_source_ref(self) -> dict[str, Any]:
        """Format as message sources JSONB item per architecture.md §2.2."""
        return {
            "episode": self.episode_title,
            "guest": self.guest_name,
            "timestamp": self.timestamp_ref,
            "score": round(self.score, 4),
        }


@dataclass
class SourceRef:
    """Provenance entry stored in messages.sources JSONB."""
    episode: str
    guest: str
    timestamp: str
    score: float


@dataclass
class RetrievalResult:
    """Encapsulates the complete outcome of a retrieval query."""
    query: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    is_out_of_domain: bool = False
    canned_response: Optional[str] = None

    @property
    def sources(self) -> list[dict[str, Any]]:
        """List of sources formatted for JSONB persistence."""
        return [c.to_source_ref() for c in self.chunks]

    @property
    def top_score(self) -> float:
        """Highest cosine similarity score among retrieved chunks."""
        return self.chunks[0].score if self.chunks else 0.0
