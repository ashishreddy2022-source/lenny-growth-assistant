"""
prompt_builder.py — Grounded prompt construction for Q&A.

Builds system prompt and context envelope for standard conversational queries,
enforcing citation syntax and grounding contracts per architecture.md §3.
"""

from typing import Optional
from app.services.retrieval.models import RetrievedChunk

BASE_SYSTEM_PROMPT = """You are "The Lenny Growth Assistant" — an expert product, growth, and startup advisor whose knowledge is strictly grounded in conversations from Lenny's Podcast.

### Grounding & Citation Rules (MANDATORY):
1. Rely EXCLUSIVELY on the provided podcast excerpts below. Do not draw on outside knowledge or speculate beyond what guests explicitly stated.
2. Ground every major claim, framework, or tactic by citing its source inline using this exact bracketed format:
   `[Episode: Guest Name, Timestamp]` (e.g. `[Episode: Brian Chesky, 00:14:32]`)
3. Attribute quotes and perspectives to the specific guest speaking in the transcript.
4. If the excerpts only partially address the user's question, provide what is known from the transcripts and explicitly state what is not covered.
5. Be direct, tactical, and clear. Emphasize actionable takeaways that a product or growth lead can immediately apply.
"""


def build_grounded_prompt(
    user_query: str,
    chunks: list[RetrievedChunk],
    conversation_history: Optional[list[dict]] = None,
) -> tuple[str, list[dict]]:
    """
    Construct the system prompt and formatted message list with retrieved sources.

    Args:
        user_query: The current query from the user.
        chunks: Retrieved transcript chunks that cleared the similarity threshold.
        conversation_history: Previous message history in the session (optional).

    Returns:
        tuple[str, list[dict]]: (system_prompt_with_sources, messages_list)
    """
    # Build the context block
    source_blocks = []
    for idx, c in enumerate(chunks, 1):
        source_blocks.append(
            f"--- SOURCE [{idx}] ---\n"
            f"Episode: {c.episode_title}\n"
            f"Guest: {c.guest_name}\n"
            f"Timestamp: {c.timestamp_ref}\n"
            f"Transcript Excerpt:\n{c.chunk_text}\n"
        )

    context_str = "\n".join(source_blocks)
    full_system_prompt = (
        f"{BASE_SYSTEM_PROMPT}\n"
        f"### RETRIEVED PODCAST TRANSCRIPTS (CONTEXT):\n"
        f"{context_str}\n"
        f"Remember: Every key statement must include `[Episode: Guest Name, Timestamp]` inline."
    )

    messages: list[dict] = []
    if conversation_history:
        # Include prior conversation turns, excluding any system messages
        for msg in conversation_history:
            if msg.get("role") in ("user", "assistant"):
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

    # Append current turn
    messages.append({
        "role": "user",
        "content": user_query,
    })

    return full_system_prompt, messages
