#!/usr/bin/env python3
"""
ingest.py — Parse, chunk, embed, and load Lenny's Podcast transcripts
into PostgreSQL + pgvector.

Reads transcript.md files from backend/data/raw/episodes/ (default) or
backend/data/sample/ (via --source sample). Each file has YAML frontmatter
followed by speaker-timestamped transcript text.

Chunking:
  Recursive splitting (paragraph → sentence → word) targeting 500-800 tokens
  per chunk with 100-token overlap. Token counts via tiktoken (cl100k_base).

Embedding:
  Batch embedding via sentence-transformers (default: all-MiniLM-L6-v2, 384d).
  Model name read from EMBEDDING_MODEL env var.

Idempotency:
  Skips episodes already present in transcript_chunks (by episode_title)
  unless --force is passed.

Usage:
    python backend/scripts/ingest.py                        # ingest from raw/
    python backend/scripts/ingest.py --source sample        # ingest from sample/
    python backend/scripts/ingest.py --force                # re-embed everything
    python backend/scripts/ingest.py --source sample --force
"""

import os
# Ensure Hugging Face cache directory is always a writable location
os.environ.setdefault("HF_HOME", "/tmp/huggingface")
os.environ.setdefault("TRANSFORMERS_CACHE", "/tmp/huggingface")

import argparse
import hashlib
import logging
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Generator, Optional

import numpy as np
import psycopg
import tiktoken
import yaml
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("ingest")

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR_RAW = PROJECT_ROOT / "backend" / "data" / "raw" / "episodes"
DATA_DIR_SAMPLE = PROJECT_ROOT / "backend" / "data" / "sample"

# Chunking parameters (architecture.md §2.1)
MIN_CHUNK_TOKENS = 500
MAX_CHUNK_TOKENS = 800
OVERLAP_TOKENS = 100

# Tiktoken encoder for reliable token counting
TOKENIZER = tiktoken.get_encoding("cl100k_base")

# Timestamp pattern in transcripts:
#   "Speaker Name (HH:MM:SS):" or "(HH:MM:SS):" (most episodes)
#   "Speaker Name (MM:SS):" or "(MM:SS):" (some episodes, e.g. Gibson Biddle)
TIMESTAMP_PATTERN = re.compile(
    r"^(?:(.+?)\s+)?\((\d{2}:\d{2}(?::\d{2})?)\):\s*$", re.MULTILINE
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EpisodeMetadata:
    """Parsed YAML frontmatter from a transcript file."""
    guest: str
    title: str
    publish_date: Optional[date] = None
    youtube_url: str = ""
    video_id: str = ""
    duration: str = ""
    description: str = ""


@dataclass
class TimestampedSegment:
    """A segment of transcript text with speaker and timestamp."""
    speaker: str
    timestamp: str  # "HH:MM:SS"
    text: str


@dataclass
class TranscriptChunk:
    """A chunk ready for embedding and insertion."""
    episode_title: str
    guest_name: str
    episode_date: Optional[date]
    timestamp_ref: str
    chunk_text: str
    chunk_index: int
    embedding: Optional[np.ndarray] = None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_frontmatter(content: str) -> tuple[Optional[EpisodeMetadata], str]:
    """
    Parse YAML frontmatter from transcript.md.

    Returns (metadata, body_text). If frontmatter is missing or
    unparseable, returns (None, full_content).
    """
    # Split on --- delimiters (standard YAML frontmatter)
    parts = content.split("---")
    if len(parts) < 3:
        return None, content

    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        logger.warning("Failed to parse YAML frontmatter: %s", exc)
        return None, content

    if not isinstance(fm, dict):
        return None, content

    # Parse publish_date
    pub_date = fm.get("publish_date")
    if isinstance(pub_date, str):
        try:
            pub_date = date.fromisoformat(pub_date)
        except ValueError:
            pub_date = None
    elif isinstance(pub_date, date):
        pass  # already a date object from YAML parser
    else:
        pub_date = None

    metadata = EpisodeMetadata(
        guest=fm.get("guest", "Unknown Guest"),
        title=fm.get("title", "Unknown Episode"),
        publish_date=pub_date,
        youtube_url=fm.get("youtube_url", ""),
        video_id=fm.get("video_id", ""),
        duration=fm.get("duration", ""),
        description=fm.get("description", ""),
    )

    # Body is everything after the second ---
    body = "---".join(parts[2:]).strip()

    return metadata, body


def parse_timestamped_segments(body: str) -> list[TimestampedSegment]:
    """
    Parse the transcript body into timestamped segments.

    The transcript format is:
        Speaker Name (HH:MM:SS):
        Paragraph of text...

        (HH:MM:SS):                  <-- continuation by same speaker
        More text...
    """
    segments: list[TimestampedSegment] = []
    lines = body.split("\n")

    current_speaker = "Unknown"
    current_timestamp = "00:00:00"
    current_text_lines: list[str] = []

    for line in lines:
        # Skip markdown headers like "# Title" and "## Transcript"
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        # Check for timestamp line
        match = TIMESTAMP_PATTERN.match(stripped)
        if match:
            # Save previous segment if it has text
            text = " ".join(current_text_lines).strip()
            if text:
                segments.append(TimestampedSegment(
                    speaker=current_speaker,
                    timestamp=current_timestamp,
                    text=text,
                ))
            # Start new segment
            speaker_name = match.group(1)
            if speaker_name:
                current_speaker = speaker_name.strip()
            # else: continuation of same speaker
            current_timestamp = match.group(2)
            current_text_lines = []
        else:
            if stripped:
                current_text_lines.append(stripped)

    # Don't forget the last segment
    text = " ".join(current_text_lines).strip()
    if text:
        segments.append(TimestampedSegment(
            speaker=current_speaker,
            timestamp=current_timestamp,
            text=text,
        ))

    return segments


# ---------------------------------------------------------------------------
# Chunking (recursive: paragraph → sentence → word)
# ---------------------------------------------------------------------------

def count_tokens(text: str) -> int:
    """Count tokens using tiktoken (cl100k_base)."""
    return len(TOKENIZER.encode(text))


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using regex."""
    # Split on sentence-ending punctuation followed by space or end-of-string
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def recursive_chunk_text(
    text: str,
    min_tokens: int = MIN_CHUNK_TOKENS,
    max_tokens: int = MAX_CHUNK_TOKENS,
) -> list[str]:
    """
    Recursively split text into chunks of min_tokens to max_tokens.

    Splitting hierarchy:
    1. Paragraphs (\\n\\n)
    2. Sentences (. ! ?)
    3. Words (space)

    Returns a list of text chunks.
    """
    total_tokens = count_tokens(text)
    if total_tokens <= max_tokens:
        return [text] if text.strip() else []

    # Try paragraph split first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) > 1:
        return _merge_splits(paragraphs, min_tokens, max_tokens)

    # Try sentence split
    sentences = split_into_sentences(text)
    if len(sentences) > 1:
        return _merge_splits(sentences, min_tokens, max_tokens)

    # Last resort: word split
    words = text.split()
    return _merge_splits(words, min_tokens, max_tokens)


def _merge_splits(
    pieces: list[str],
    min_tokens: int,
    max_tokens: int,
) -> list[str]:
    """
    Merge small pieces into chunks within the token budget.

    Greedily accumulates pieces until adding the next piece would exceed
    max_tokens, then starts a new chunk.
    """
    chunks: list[str] = []
    current_pieces: list[str] = []
    current_token_count = 0

    for piece in pieces:
        piece_tokens = count_tokens(piece)

        # If a single piece exceeds max, recursively split it
        if piece_tokens > max_tokens:
            # Flush current buffer
            if current_pieces:
                chunks.append(" ".join(current_pieces))
                current_pieces = []
                current_token_count = 0
            # Recurse on the oversized piece
            sub_chunks = recursive_chunk_text(piece, min_tokens, max_tokens)
            chunks.extend(sub_chunks)
            continue

        # Would adding this piece exceed max?
        projected = current_token_count + piece_tokens + (1 if current_pieces else 0)
        if projected > max_tokens and current_pieces:
            chunks.append(" ".join(current_pieces))
            current_pieces = []
            current_token_count = 0

        current_pieces.append(piece)
        current_token_count += piece_tokens + (1 if len(current_pieces) > 1 else 0)

    # Flush remaining
    if current_pieces:
        chunks.append(" ".join(current_pieces))

    return chunks


def create_chunks_with_overlap(
    segments: list[TimestampedSegment],
    metadata: EpisodeMetadata,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[TranscriptChunk]:
    """
    Build chunks from timestamped segments with overlap.

    Strategy:
    1. Concatenate segment texts (preserving speaker/timestamp boundaries)
    2. Recursively chunk the concatenated text
    3. Apply overlap by prepending tail of previous chunk to current
    4. Assign timestamp_ref from the segment whose text starts the chunk
    """
    if not segments:
        return []

    # Build a mapping of character offsets to timestamps for reference
    full_text_parts: list[str] = []
    offset_to_timestamp: list[tuple[int, str, str]] = []  # (char_offset, timestamp, speaker)

    current_offset = 0
    for seg in segments:
        offset_to_timestamp.append((current_offset, seg.timestamp, seg.speaker))
        full_text_parts.append(seg.text)
        current_offset += len(seg.text) + 1  # +1 for the joining space

    full_text = " ".join(full_text_parts)

    # Recursive chunk the full text
    raw_chunks = recursive_chunk_text(full_text)

    if not raw_chunks:
        return []

    # Apply overlap and build TranscriptChunk objects
    chunks: list[TranscriptChunk] = []

    for idx, chunk_text in enumerate(raw_chunks):
        # Apply overlap from previous chunk
        if idx > 0 and overlap_tokens > 0:
            prev_text = raw_chunks[idx - 1]
            prev_tokens = TOKENIZER.encode(prev_text)
            overlap_text = TOKENIZER.decode(prev_tokens[-overlap_tokens:])
            chunk_text = overlap_text.strip() + " " + chunk_text

        # Find the timestamp for this chunk by locating its start in the full text
        chunk_start = full_text.find(chunk_text[:50])  # Use first 50 chars as anchor
        timestamp_ref = segments[0].timestamp  # fallback
        for offset, ts, speaker in reversed(offset_to_timestamp):
            if chunk_start >= offset:
                timestamp_ref = ts
                break

        chunks.append(TranscriptChunk(
            episode_title=metadata.title,
            guest_name=metadata.guest,
            episode_date=metadata.publish_date,
            timestamp_ref=timestamp_ref,
            chunk_text=chunk_text.strip(),
            chunk_index=idx,
        ))

    return chunks


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

def load_embedding_model() -> tuple[SentenceTransformer, str, int]:
    """
    Load the sentence-transformers model from EMBEDDING_MODEL env var.

    Returns (model, model_name, dimension).
    """
    model_name = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    expected_dim = int(os.getenv("EMBEDDING_DIMENSION", "384"))

    logger.info("Loading embedding model: %s (expected dim=%d)", model_name, expected_dim)
    model = SentenceTransformer(model_name)

    # Verify dimension
    test_embedding = model.encode(["test"])
    actual_dim = test_embedding.shape[1]
    if actual_dim != expected_dim:
        logger.error(
            "EMBEDDING_DIMENSION mismatch: env says %d but model produces %d. "
            "Update EMBEDDING_DIMENSION in .env to match your model.",
            expected_dim,
            actual_dim,
        )
        sys.exit(1)

    logger.info("Model loaded. Embedding dimension: %d", actual_dim)
    return model, model_name, actual_dim


def batch_embed(model: SentenceTransformer, texts: list[str], batch_size: int = 64) -> np.ndarray:
    """Embed texts in batches for throughput."""
    logger.info("Embedding %d chunks (batch_size=%d)...", len(texts), batch_size)
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,  # for cosine similarity
    )
    return embeddings


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def get_db_connection(max_retries: int = 5, retry_delay: float = 3.0):
    """Create a psycopg3 connection from DATABASE_URL with retry logic."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not set. See .env.example.")
        sys.exit(1)

    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Connecting to database (attempt %d/%d)...", attempt, max_retries)
            conn = psycopg.connect(db_url, autocommit=False)
            register_vector(conn)
            logger.info("Database connection established successfully.")
            return conn
        except Exception as exc:
            if attempt < max_retries:
                logger.warning("Database connection failed (%s). Retrying in %.1fs...", exc, retry_delay)
                time.sleep(retry_delay)
            else:
                logger.error("Failed to connect to database after %d attempts: %s", max_retries, exc)
                raise


def init_schema(conn):
    """Run schema.sql to create tables and indexes."""
    schema_path = SCRIPT_DIR.parent / "db" / "schema.sql"
    if not schema_path.exists():
        logger.error("schema.sql not found at %s", schema_path)
        sys.exit(1)

    with open(schema_path, "r") as f:
        sql = f.read()

    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    logger.info("Schema initialized.")


def check_corpus_metadata(conn, model_name: str, dimension: int) -> bool:
    """
    Check corpus_metadata for model/dimension mismatch.

    Returns True if safe to proceed, False if mismatch detected.
    If --force is used, caller should handle the mismatch.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT embedding_model, embedding_dimension FROM corpus_metadata "
            "ORDER BY ingested_at DESC LIMIT 1"
        )
        row = cur.fetchone()

    if row is None:
        return True  # No previous ingestion, safe to proceed

    prev_model, prev_dim = row
    if prev_model != model_name or prev_dim != dimension:
        logger.error(
            "CORPUS METADATA MISMATCH!\n"
            "  Previous ingestion: model=%s, dim=%d\n"
            "  Current config:     model=%s, dim=%d\n"
            "  The existing embeddings are INCOMPATIBLE with the current model.\n"
            "  To re-ingest with the new model, first TRUNCATE transcript_chunks\n"
            "  and DELETE FROM corpus_metadata, then re-run with --force.",
            prev_model, prev_dim, model_name, dimension,
        )
        return False

    return True


def get_existing_episodes(conn) -> set[str]:
    """Return set of episode_titles already in transcript_chunks."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT episode_title FROM transcript_chunks")
        return {row[0] for row in cur.fetchall()}


def insert_chunks(conn, chunks: list[TranscriptChunk]) -> int:
    """Bulk-insert chunks into transcript_chunks. Returns count inserted."""
    if not chunks:
        return 0

    sql = """
        INSERT INTO transcript_chunks
            (id, episode_title, guest_name, episode_date, timestamp_ref,
             chunk_text, chunk_index, embedding)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """

    with conn.cursor() as cur:
        # Batch insert using executemany with COPY-like performance via pipeline
        rows = []
        for c in chunks:
            rows.append((
                str(uuid.uuid4()),
                c.episode_title,
                c.guest_name,
                c.episode_date,
                c.timestamp_ref,
                c.chunk_text,
                c.chunk_index,
                c.embedding.tolist() if c.embedding is not None else None,
            ))
        cur.executemany(sql, rows)

    conn.commit()
    return len(rows)


def write_corpus_metadata(conn, model_name: str, dimension: int, chunk_count: int):
    """Write a new corpus_metadata row after successful ingestion."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO corpus_metadata (embedding_model, embedding_dimension, chunk_count)
            VALUES (%s, %s, %s)
            """,
            (model_name, dimension, chunk_count),
        )
    conn.commit()
    logger.info(
        "corpus_metadata updated: model=%s, dim=%d, chunks=%d",
        model_name, dimension, chunk_count,
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def discover_transcripts(data_dir: Path) -> list[Path]:
    """Find all transcript.md files in the data directory."""
    transcripts = []
    if not data_dir.exists():
        logger.error("Data directory does not exist: %s", data_dir)
        return transcripts

    for entry in sorted(data_dir.iterdir()):
        if entry.is_dir():
            transcript_file = entry / "transcript.md"
            if transcript_file.exists():
                transcripts.append(transcript_file)
    return transcripts


def process_transcript(filepath: Path) -> tuple[Optional[EpisodeMetadata], list[TranscriptChunk]]:
    """
    Parse a single transcript file into metadata + chunks.

    Returns (metadata, chunks). On parse failure, returns (None, []).
    """
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to read %s: %s", filepath, exc)
        return None, []

    metadata, body = parse_frontmatter(content)
    if metadata is None:
        logger.warning(
            "No valid frontmatter in %s. Skipping.", filepath
        )
        return None, []

    segments = parse_timestamped_segments(body)
    if not segments:
        # Fallback: treat the whole body as a single untimestamped block
        logger.warning(
            "No timestamped segments found in %s. Using full body as single segment.",
            filepath,
        )
        segments = [TimestampedSegment(
            speaker="Unknown",
            timestamp="00:00:00",
            text=body,
        )]

    chunks = create_chunks_with_overlap(segments, metadata)

    # Log chunk statistics
    token_counts = [count_tokens(c.chunk_text) for c in chunks]
    if token_counts:
        logger.debug(
            "%s: %d chunks, tokens min=%d avg=%d max=%d",
            metadata.title,
            len(chunks),
            min(token_counts),
            sum(token_counts) // len(token_counts),
            max(token_counts),
        )

    return metadata, chunks


def main():
    parser = argparse.ArgumentParser(
        description="Ingest Lenny's Podcast transcripts into PostgreSQL + pgvector"
    )
    parser.add_argument(
        "--source",
        choices=["raw", "sample"],
        default="raw",
        help="Data source: 'raw' (full archive) or 'sample' (committed samples)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-embedding of episodes already present in the database",
    )
    args = parser.parse_args()

    data_dir = DATA_DIR_RAW if args.source == "raw" else DATA_DIR_SAMPLE
    logger.info("Source directory: %s", data_dir)

    # 1. Load embedding model
    model, model_name, dimension = load_embedding_model()

    # 2. Connect to database and initialize schema
    conn = get_db_connection()
    init_schema(conn)

    # 3. Check corpus_metadata for model/dimension mismatch
    if not check_corpus_metadata(conn, model_name, dimension):
        logger.error("Aborting due to corpus metadata mismatch. See above for instructions.")
        sys.exit(1)

    # 4. Discover transcripts
    transcript_files = discover_transcripts(data_dir)
    if not transcript_files:
        logger.error("No transcript files found in %s", data_dir)
        sys.exit(1)
    logger.info("Found %d transcript files.", len(transcript_files))

    # 5. Get already-ingested episodes (for idempotency)
    existing_episodes = get_existing_episodes(conn) if not args.force else set()
    if existing_episodes:
        logger.info("%d episodes already ingested.", len(existing_episodes))

    # 6. Process transcripts
    all_chunks: list[TranscriptChunk] = []
    episodes_processed = 0
    episodes_skipped = 0
    parse_failures = 0

    for filepath in transcript_files:
        metadata, chunks = process_transcript(filepath)
        if metadata is None:
            parse_failures += 1
            continue

        if metadata.title in existing_episodes:
            logger.debug("Skipping already-ingested: %s", metadata.title)
            episodes_skipped += 1
            continue

        all_chunks.extend(chunks)
        episodes_processed += 1

    if not all_chunks:
        logger.info("No new chunks to embed. %d skipped, %d failures.",
                     episodes_skipped, parse_failures)
        conn.close()
        return

    # 7. Batch embed all chunks
    texts = [c.chunk_text for c in all_chunks]
    embeddings = batch_embed(model, texts)

    for chunk, embedding in zip(all_chunks, embeddings):
        chunk.embedding = embedding

    # 8. Insert into database
    logger.info("Inserting %d chunks into transcript_chunks...", len(all_chunks))
    start_time = time.time()

    if args.force:
        # Clear existing data on force
        with conn.cursor() as cur:
            cur.execute("TRUNCATE transcript_chunks")
            cur.execute("DELETE FROM corpus_metadata")
        conn.commit()
        logger.info("Cleared existing data (--force mode).")

    inserted = insert_chunks(conn, all_chunks)
    elapsed = time.time() - start_time
    logger.info("Inserted %d chunks in %.1fs.", inserted, elapsed)

    # 9. Write corpus_metadata
    total_chunks = inserted
    if not args.force:
        # Add existing count
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM transcript_chunks")
            total_chunks = cur.fetchone()[0]

    write_corpus_metadata(conn, model_name, dimension, total_chunks)

    # 10. Verification
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM transcript_chunks")
        db_count = cur.fetchone()[0]
        cur.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'transcript_chunks' AND indexdef LIKE '%hnsw%'"
        )
        hnsw_index = cur.fetchone()

    conn.close()

    # Final summary
    logger.info("=" * 60)
    logger.info("INGESTION SUMMARY")
    logger.info("=" * 60)
    logger.info("  Source:            %s", args.source)
    logger.info("  Episodes processed: %d", episodes_processed)
    logger.info("  Episodes skipped:   %d (already ingested)", episodes_skipped)
    logger.info("  Parse failures:     %d", parse_failures)
    logger.info("  Chunks created:     %d", inserted)
    logger.info("  Total in DB:        %d", db_count)
    logger.info("  Embedding model:    %s", model_name)
    logger.info("  Embedding dim:      %d", dimension)
    logger.info("  HNSW index:         %s", "✓ present" if hnsw_index else "✗ MISSING")

    # Token count statistics
    if all_chunks:
        token_counts = [count_tokens(c.chunk_text) for c in all_chunks]
        logger.info("  Chunk tokens:       min=%d, avg=%d, max=%d",
                     min(token_counts),
                     sum(token_counts) // len(token_counts),
                     max(token_counts))

    logger.info("=" * 60)

    if parse_failures > 0:
        logger.warning(
            "%d transcript(s) failed to parse. Check warnings above.", parse_failures
        )


if __name__ == "__main__":
    main()
