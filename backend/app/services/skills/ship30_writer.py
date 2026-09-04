"""
ship30_writer.py — Ship 30 for 30 essay generation skill.

Encodes Ship 30 for 30 writing principles per assignment brief §4.2 and architecture.md §5:
- ~1,250 words with post-generation word count tolerance validation (±15%: 1062 - 1438 words)
- Strong hook and compelling headline
- Skimmable formatting: bold lead-ins, 1-2 sentence paragraphs, numbered pillars, bullets
- Strict transcript grounding with [Episode: Guest Name, Timestamp] inline citations
- Actionable takeaways ("The Monday Morning Rule")
"""

import re
from typing import Optional
from app.services.retrieval.models import RetrievedChunk

SHIP30_TARGET_WORDS = 1250
SHIP30_TOLERANCE_PCT = 0.15
SHIP30_MIN_WORDS = int(SHIP30_TARGET_WORDS * (1.0 - SHIP30_TOLERANCE_PCT))  # 1062
SHIP30_MAX_WORDS = int(SHIP30_TARGET_WORDS * (1.0 + SHIP30_TOLERANCE_PCT))  # 1437

SHIP30_SYSTEM_TEMPLATE = """You are a master essayist and growth operator specializing in the "Ship 30 for 30" writing framework.
Your task is to transform tactical insights from Lenny's Podcast into an authoritative, engaging, publication-ready essay.

### SHIP 30 WRITING PRINCIPLES & STRUCTURE:
1. Target Length: Approximately 1,250 words (aim for ~1,200–1,300 words). Be comprehensive, detailed, and substantive. Do not write a brief summary.
2. Title & Hook (First 150 words):
   - Start with a compelling, magnetic H1 headline.
   - Lead with a provocative observation, counterintuitive truth, or the core problem leaders get wrong.
   - Use short, punchy sentences to build momentum.
3. The Context & The Stakes (Next 250 words):
   - Explain why this problem matters right now.
   - Contrast how novice operators approach this vs how elite guests on Lenny's Podcast solved it.
4. The 3–5 Core Pillars / Framework (Next 600 words):
   - Break the strategy into 3 to 5 clear, numbered sections with H2/H3 headers.
   - For every pillar, provide:
     * The Core Principle (bold 1-sentence thesis)
     * Real-world transcript proof and citation: `[Episode: Guest Name, Timestamp]`
     * Concrete step-by-step implementation guide
5. The Actionable Checklist ("The Monday Morning Rule" - Next 150 words):
   - What should the reader do tomorrow at 9:00 AM?
   - Bulleted checklist with bold lead-ins.
6. Conclusion / The Big Takeaway (Final 100 words):
   - Memorable closing sentence that cements the core lesson.

### FORMATTING RULES (SKIMMABILITY):
- Never write paragraphs longer than 3 sentences.
- Use **bold emphasis** on key takeaways and the first 2-3 words of bullet points.
- Use bullet points and numbered lists generously.
- Strictly ground every factual claim, number, and quote using `[Episode: Guest Name, Timestamp]`. Do not hallucinate outside details.
"""


def build_ship30_prompt(
    user_query: str,
    chunks: list[RetrievedChunk],
    source_context: Optional[str] = None,
) -> tuple[str, list[dict]]:
    """
    Construct the system prompt and user message for generating a Ship 30 essay.

    Args:
        user_query: The topic or instruction from the user.
        chunks: Retrieved transcript chunks that ground the essay.
        source_context: Optional pre-assembled context text.

    Returns:
        tuple[str, list[dict]]: (system_prompt_with_sources, messages_list)
    """
    # Build transcript context block
    if not source_context:
        source_blocks = []
        for idx, c in enumerate(chunks, 1):
            source_blocks.append(
                f"--- SOURCE [{idx}] ---\n"
                f"Episode: {c.episode_title}\n"
                f"Guest: {c.guest_name}\n"
                f"Timestamp: {c.timestamp_ref}\n"
                f"Content:\n{c.chunk_text}\n"
            )
        source_context = "\n".join(source_blocks)

    full_system_prompt = (
        f"{SHIP30_SYSTEM_TEMPLATE}\n\n"
        f"### PODCAST TRANSCRIPT SOURCES TO GROUND THIS ESSAY:\n"
        f"{source_context}\n\n"
        f"REMINDER: Target length is ~1,250 words. Ground every pillar in the sources above with inline citations [Episode: Guest Name, Timestamp]."
    )

    user_message = (
        f"Write an authoritative Ship 30 for 30 style essay (~1,250 words) on: '{user_query}'.\n"
        f"Ensure it has an irresistible hook, 3-5 structured pillars with tactical examples, "
        f"inline citations [Episode: Guest Name, Timestamp], and a Monday morning checklist."
    )

    messages = [{"role": "user", "content": user_message}]
    return full_system_prompt, messages


def validate_ship30_essay(content: str) -> dict:
    """
    Validate the post-generation quality and word count band of a Ship 30 essay.

    Checks:
    1. Word count against the ±15% band (1,062 to 1,437 words).
    2. Structural markers (Headline H1, subheadings H2/H3, bullet points).

    Returns:
        dict: Metadata dictionary ready for inclusion in response metadata.
    """
    if not content or not content.strip():
        return {
            "word_count": 0,
            "target_words": SHIP30_TARGET_WORDS,
            "in_tolerance": False,
            "min_words": SHIP30_MIN_WORDS,
            "max_words": SHIP30_MAX_WORDS,
            "tolerance_pct": SHIP30_TOLERANCE_PCT,
            "has_headings": False,
            "has_bullets": False,
            "status": "empty",
        }

    # Count words using whitespace tokenization
    words = content.strip().split()
    word_count = len(words)
    in_tolerance = (SHIP30_MIN_WORDS <= word_count <= SHIP30_MAX_WORDS)

    # Check structural markers
    has_h1 = bool(re.search(r"^#\s+.+", content, re.MULTILINE))
    has_subheadings = bool(re.search(r"^#{2,3}\s+.+", content, re.MULTILINE))
    has_bullets = bool(re.search(r"^\s*[-*]\s+.+", content, re.MULTILINE))

    status = (
        "in_tolerance"
        if in_tolerance
        else ("under_length" if word_count < SHIP30_MIN_WORDS else "over_length")
    )

    return {
        "word_count": word_count,
        "target_words": SHIP30_TARGET_WORDS,
        "in_tolerance": in_tolerance,
        "min_words": SHIP30_MIN_WORDS,
        "max_words": SHIP30_MAX_WORDS,
        "tolerance_pct": SHIP30_TOLERANCE_PCT,
        "has_headings": (has_h1 and has_subheadings),
        "has_bullets": has_bullets,
        "status": status,
    }
