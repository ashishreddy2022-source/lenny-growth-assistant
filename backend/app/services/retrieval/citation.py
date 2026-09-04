"""
citation.py — Citation syntax parsing, post-hoc validation, and grounding verification.

Enforces architecture.md §3:
  "citation syntax [Episode: Guest Name, Timestamp/Topic] is enforced in the prompt,
   then validated post-hoc: any response missing at least one bracketed citation is
   flagged for a UI warning badge, not silently accepted."
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from app.services.retrieval.models import RetrievedChunk

# Regex to capture citations in forms:
#   [Episode: Brian Chesky, 00:14:32]
#   [Episode: Shreyas Doshi, L1 Product Work]
#   [Julie Zhuo, 12:45]
CITATION_REGEX = re.compile(
    r"\[(?:(?:Episode|Ep\.?):\s*)?([^,\]\n]+?),\s*([^\]\n]+?)\]",
    re.IGNORECASE,
)


@dataclass
class ExtractedCitation:
    """Represents a single parsed citation from the assistant response."""
    raw_text: str
    guest_or_episode: str
    timestamp_or_topic: str
    is_grounded: bool = False
    matched_chunk_id: Optional[str] = None


@dataclass
class CitationValidationResult:
    """Outcome of validating citations in a generated response."""
    valid: bool
    has_citations: bool
    citations: list[ExtractedCitation] = field(default_factory=list)
    ungrounded_citations: list[ExtractedCitation] = field(default_factory=list)
    warning_badge: bool = False
    warning_message: Optional[str] = None


def extract_citations(text: str) -> list[ExtractedCitation]:
    """
    Find all bracketed citations in the text.
    """
    citations: list[ExtractedCitation] = []
    for match in CITATION_REGEX.finditer(text):
        raw_text = match.group(0)
        guest_or_ep = match.group(1).strip()
        ref = match.group(2).strip()
        citations.append(ExtractedCitation(
            raw_text=raw_text,
            guest_or_episode=guest_or_ep,
            timestamp_or_topic=ref,
        ))
    return citations


def validate_citations(
    response_text: str,
    retrieved_chunks: list[RetrievedChunk],
) -> CitationValidationResult:
    """
    Validate citations in an LLM response against the retrieved source chunks.

    Checks:
    1. Does the response contain at least one citation? (Flagged for UI badge if false)
    2. Does each citation match a retrieved guest or episode title?
    """
    if not response_text or not response_text.strip():
        return CitationValidationResult(
            valid=False,
            has_citations=False,
            warning_badge=True,
            warning_message="Empty response received.",
        )

    extracted = extract_citations(response_text)

    if not extracted:
        return CitationValidationResult(
            valid=False,
            has_citations=False,
            citations=[],
            ungrounded_citations=[],
            warning_badge=True,
            warning_message="Answer contains no source citations. Verification badge flagged.",
        )

    # Build lookup sets for retrieved sources (lowercased for case-insensitive matching)
    retrieved_guests = {c.guest_name.lower() for c in retrieved_chunks}
    retrieved_titles = {c.episode_title.lower() for c in retrieved_chunks}

    ungrounded: list[ExtractedCitation] = []

    for citation in extracted:
        cited_target = citation.guest_or_episode.lower()
        matched_chunk = None

        # Check for matching guest or episode title (fuzzy prefix/substring match)
        for chunk in retrieved_chunks:
            chunk_guest = chunk.guest_name.lower()
            chunk_title = chunk.episode_title.lower()
            if (
                cited_target in chunk_guest
                or chunk_guest in cited_target
                or cited_target in chunk_title
                or chunk_title in cited_target
            ):
                matched_chunk = chunk
                break

        if matched_chunk:
            citation.is_grounded = True
            citation.matched_chunk_id = matched_chunk.id
        else:
            citation.is_grounded = False
            ungrounded.append(citation)

    warning_badge = len(ungrounded) > 0
    warning_message = (
        f"{len(ungrounded)} citation(s) reference episodes not in the retrieved context."
        if ungrounded
        else None
    )

    return CitationValidationResult(
        valid=(not warning_badge),
        has_citations=True,
        citations=extracted,
        ungrounded_citations=ungrounded,
        warning_badge=warning_badge,
        warning_message=warning_message,
    )
