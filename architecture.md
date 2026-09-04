# Architecture Spec — The Lenny Growth Assistant

## 1. System Overview

```
┌──────────────┐      HTTPS/SSE      ┌───────────────────┐
│   Frontend   │◄───────────────────►│   FastAPI Backend   │
│  (Next.js)   │                     │                     │
└──────────────┘                     └─────────┬───────────┘
                                                │
                     ┌──────────────────────────┼──────────────────────────┐
                     ▼                          ▼                          ▼
            ┌────────────────┐        ┌──────────────────┐       ┌─────────────────┐
            │  PostgreSQL 16  │        │  LLM Provider Layer│      │  Embedding Model │
            │  + pgvector     │        │  (Ollama | Claude) │      │ (MiniLM / nomic) │
            └────────────────┘        └──────────────────┘       └─────────────────┘
```

The backend is the single source of truth. The frontend never talks to Postgres, Ollama, or the cloud LLM directly — everything is proxied and streamed through FastAPI, which keeps API keys server-side and gives us one place to enforce the citation/grounding contract.

## 2. Data Contracts

### 2.1 `transcript_chunks` (vector store)

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `episode_title` | TEXT | |
| `guest_name` | TEXT | |
| `episode_date` | DATE | |
| `timestamp_ref` | TEXT | e.g. `"14:32"` or section label |
| `chunk_text` | TEXT | 500–800 tokens, 100-token overlap |
| `chunk_index` | INT | position within episode, for reconstructing context |
| `embedding` | VECTOR(384) | MiniLM dim; adjust if using `nomic-embed-text` (768) |
| `created_at` | TIMESTAMPTZ | |

**Index:** `CREATE INDEX ON transcript_chunks USING hnsw (embedding vector_cosine_ops);`
HNSW chosen over IVFFlat for query-time speed at this corpus size; `m=16, ef_construction=64` defaults are sufficient below ~50k rows.

### 2.2 Relational tables (application state)

```sql
sessions(id UUID PK, title TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ)

messages(
  id UUID PK,
  session_id UUID FK -> sessions.id,
  role TEXT CHECK (role IN ('user','assistant')),
  content TEXT,
  sources JSONB,        -- [{episode, guest, timestamp, score}, ...]
  created_at TIMESTAMPTZ
)

artifacts(
  id UUID PK,
  message_id UUID FK -> messages.id,
  artifact_type TEXT CHECK (artifact_type IN ('markdown','html')),
  title TEXT,
  content TEXT,
  created_at TIMESTAMPTZ
)
```

`sources` is stored as JSONB on the message itself (not a join table) — retrieval provenance is immutable once a message is generated, so there's no need for relational flexibility there, and it keeps message hydration to a single query.

## 3. Retrieval Flow

1. Client sends `POST /api/chat` with `{session_id, message, mode, provider}`.
2. Backend embeds the query (same embedding model used at ingestion — this consistency is enforced by a single `EMBEDDING_MODEL` env var read by both the ingestion script and the retriever).
3. `TranscriptRetriever` runs cosine-similarity search via `pgvector`, `top_k=4–6`, `similarity_threshold=0.65`.
4. If **zero** chunks clear the threshold → skip the LLM call entirely and return the canned out-of-domain response. This is a deliberate short-circuit: it's cheaper, faster, and more reliable than trusting the model to self-report low confidence.
5. If chunks clear the threshold → build the grounded system prompt (citation syntax `[Episode: Guest Name, Timestamp/Topic]` is enforced in the prompt, then validated post-hoc: any response missing at least one bracketed citation is flagged for a UI warning badge, not silently accepted).
6. Route to the selected `LLMProviderInterface` implementation and stream tokens back over SSE.
7. Persist the message + `sources` JSONB once the stream completes.

## 4. Model Routing

`LLMProviderInterface` is the only contract the rest of the app depends on:

```python
class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate_response(
        self, messages, system_prompt, temperature=0.3
    ) -> AsyncGenerator[str, None]: ...
```

- **Selection order:** request header `X-LLM-Provider` (frontend toggle) → `DEFAULT_LLM_PROVIDER` env var → hardcoded fallback `ollama`.
- **Why a header and not just env config:** the assignment requires *instant* frontend toggling without redeploying the backend — a per-request header is the only mechanism that satisfies that without a settings-write round trip.
- Both providers implement identical streaming semantics so `chat.py` never branches on provider type beyond the factory lookup — this is what makes "add OpenAI later" a one-file change (`providers/openai_provider.py` + one line in the factory).

## 5. Ship 30 Skill Routing

`mode="ship30"` does not change the retrieval step — it changes only the system prompt template used in step 5 above (`ship30_writer.build_ship30_prompt`). This keeps retrieval and generation-style fully decoupled: any future "skill" (e.g., a tweet-thread generator) is a new prompt template, not a new retrieval path.

## 6. Failure Modes & Resilience

| Failure | Handling |
|---|---|
| Ollama unreachable | `/api/health` reports `ollama: down`; chat endpoint returns a typed error the frontend renders as a banner, not a silent hang |
| Postgres connection drop | `asyncpg` pool with retry/backoff (3 attempts, exponential); health probe surfaces `db: degraded` |
| Streaming client disconnect mid-response | Backend still persists the partial message to `messages` on `asyncio.CancelledError`, tagged `truncated: true` |
| Embedding dimension mismatch (model swapped post-ingestion) | Ingestion script writes the embedding model name + dimension into a `corpus_metadata` table; retriever checks it at startup and fails loudly rather than silently returning garbage similarity scores |

## 7. Deployment Topology

Four Docker services (`db`, `backend`, `frontend`, optional `ollama`) as specified in the assignment. `backend` depends on `db` via `service_healthy`; `ollama` is optional because most reviewers will already run it natively on the host (hence `host.docker.internal` in the default config rather than forcing a containerized Ollama, which is slower to pull models and loses GPU passthrough on most setups).
