-- ============================================================
-- The Lenny Growth Assistant — Database Schema
-- Architecture.md §2.1, §2.2
-- ============================================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- § Corpus Metadata (architecture.md §6)
-- Written once per successful ingest run. The retriever checks
-- embedding_model + embedding_dimension at startup and aborts
-- loudly on a mismatch rather than returning garbage scores.
-- ============================================================
CREATE TABLE IF NOT EXISTS corpus_metadata (
    id              SERIAL PRIMARY KEY,
    embedding_model TEXT NOT NULL,
    embedding_dimension INT NOT NULL,
    chunk_count     INT NOT NULL DEFAULT 0,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- § Transcript Chunks — Vector Store (architecture.md §2.1)
-- ============================================================
CREATE TABLE IF NOT EXISTS transcript_chunks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    episode_title   TEXT NOT NULL,
    guest_name      TEXT NOT NULL,
    episode_date    DATE,
    timestamp_ref   TEXT,          -- e.g. "14:32" or section label
    chunk_text      TEXT NOT NULL,
    chunk_index     INT NOT NULL,  -- position within episode
    embedding       VECTOR(384),   -- MiniLM dim; recreate table if using 768d model
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- HNSW index — cosine ops, m=16, ef_construction=64
-- (architecture.md: sufficient below ~50k rows)
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
    ON transcript_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================================
-- § Application State Tables (architecture.md §2.2)
-- ============================================================
CREATE TABLE IF NOT EXISTS sessions (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT NOT NULL,
    sources     JSONB,  -- [{episode, guest, timestamp, score}, ...]
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS artifacts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    message_id      UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    artifact_type   TEXT NOT NULL CHECK (artifact_type IN ('markdown', 'html')),
    title           TEXT,
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
