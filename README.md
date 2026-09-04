# The Lenny Growth Assistant

> **A grounded conversational AI assistant and Ship 30 essay engine powered by Lenny’s Podcast transcripts.**  
> Built as a Forward Deployed Engineering assessment for Oogway Labs.

---

## 1. System Overview & Architecture

```
┌───────────────────────────────┐                  ┌─────────────────────────────────┐
│     Next.js 16 Frontend       │                  │       FastAPI Backend API       │
│  - Dual-Pane UI (Chat/Artifact│  HTTPS / SSE     │  - Session & Message Repository │
│  - SandboxedIframe Security   │◄────────────────►│  - SSE Streaming Dispatcher     │
│  - Clickable Citation Chips   │                  │  - Out-of-Domain Short-Circuit  │
│  - Model Selector (Ollama/Cl.)│                  │  - Ship 30 Prompt & Post-Check  │
└───────────────────────────────┘                  └──────┬────────────┬─────────────┘
                                                          │            │
                                       ┌──────────────────┘            └─────────────────┐
                                       ▼                                                 ▼
                        ┌──────────────────────────────┐                  ┌──────────────────────────────┐
                        │   PostgreSQL 16 + pgvector   │                  │     LLM Provider Layer       │
                        │  - HNSW Index (cosine ops)   │                  │  - OllamaProvider (Local)    │
                        │  - transcript_chunks table   │                  │  - ClaudeProvider (Cloud)    │
                        │  - sessions / messages tables│                  │  - Dynamic Header Routing    │
                        │  - corpus_metadata validator │                  │  - Unified Exception Model   │
                        └──────────────────────────────┘                  └──────────────────────────────┘
```

The backend acts as the single source of truth. The frontend never accesses PostgreSQL, the vector store, or the cloud LLM directly. All interactions are routed and streamed through FastAPI to enforce citation contracts, prevent credential leakage, and validate artifact safety.

---

## 2. Key Features

- **Grounded Transcript RAG:** Queries 269 podcast transcripts across product management, growth loops, marketplace dynamics, and organizational leadership.
- **Deterministic Out-of-Domain Short-Circuit:** If 0 chunks clear the cosine similarity threshold (`0.65`), the system immediately returns a canned refusal without calling the LLM—saving latency, inference cost, and hallucination risk.
- **Dual-Pane Interface:** 55% left chat pane and 45% collapsible right pane. The artifact viewer opens automatically upon essay generation or artifact selection.
- **Clickable Citation Chips:** Every factual claim includes an inline chip `[Episode: Guest, Timestamp]`. Clicking it reveals the exact retrieved chunk, guest, and cosine similarity percentage.
- **Ship 30 for 30 Content Engine:** One-click `✎ Ship 30` affordance transforms grounded answers into ~1,250-word publish-ready essays with bold lead-ins, structured pillars, and an actionable "Monday Morning Rule" checklist.
- **Sandboxed HTML/Markdown Artifact Viewer:** Isolates untrusted HTML using `sandbox="allow-scripts"` **STRICTLY WITHOUT** `allow-same-origin`, preventing access to parent cookies, storage, or origin.
- **Multi-Provider Parity:** Real-time toggle between **Ollama (Local Llama 3.2)** and **Anthropic Claude 3.5 Sonnet (Cloud)** via `X-LLM-Provider` request header.

---

## 3. Quickstart (One-Command Deployment)

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) and Docker Compose v2+
- [Ollama](https://ollama.ai) running on your host machine (or run containerized via `--profile full`)

### 1. Clone & Configure
```bash
git clone <repo-url>
cd "The Lenny Growth Assistant"

# Create environment file from template
cp .env.example .env
```

### 2. Launch Services
```bash
docker compose up --build
```
This boots:
1. **`db`** (`localhost:5432`): PostgreSQL 16 + pgvector with schema pre-initialized.
2. **`backend`** (`localhost:8000`): FastAPI API server with health probes.
3. **`frontend`** (`localhost:3000`): Next.js App Router dual-pane web application.

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 4. Ingestion & Vector Indexing

The project comes pre-bundled with 5 committed sample transcripts (Brian Chesky, Julie Zhuo, Shreyas Doshi, Gibson Biddle, Deb Liu).

### Ingest the Sample Transcripts (Fast)
```bash
# Ingest the 5 sample episodes into pgvector
python backend/scripts/ingest.py --source sample
```

### Ingest the Full Corpus (269 Episodes)
```bash
# Download the complete archive (~38MB tarball from ChatPRD/lennys-podcast-transcripts)
python backend/scripts/download_transcripts.py

# Ingest and embed all episodes
python backend/scripts/ingest.py
```

### Ingestion Validation Dry-Run (No Database Needed)
```bash
# Validates frontmatter parsing, recursive chunking, and embedding normalization offline
python backend/scripts/test_ingest_dryrun.py
```

---

## 5. Model Configuration & Provider Setup

The system implements a 3-tier model resolution hierarchy:
1. Request Header: `X-LLM-Provider` (controlled by the frontend `ModelSelector` badge)
2. Environment Variable: `DEFAULT_LLM_PROVIDER` in `.env`
3. Fallback: `"ollama"`

### Local Inference (Ollama — Mandatory for Demo)
1. Install Ollama and pull the default model:
   ```bash
   ollama pull llama3.2:3b
   ollama serve
   ```
2. Verify Ollama is accessible at `http://localhost:11434`.

### Cloud Inference (Anthropic Claude)
1. Set your API key in `.env`:
   ```env
   ANTHROPIC_API_KEY=sk-ant-api03-...
   CLAUDE_MODEL=claude-3-5-sonnet-20241022
   ```
2. Switch to **Claude 3.5 (Cloud)** using the header badge in the UI.

---

## 6. Environment Variables Reference

| Variable | Default | Purpose |
|:---|:---|:---|
| `DATABASE_URL` | `postgresql://lenny_app:lenny_secret@localhost:5432/lenny_growth` | PostgreSQL connection string |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model for ingestion & retrieval |
| `EMBEDDING_DIMENSION` | `384` | Vector dimension (checked against `corpus_metadata`) |
| `DEFAULT_LLM_PROVIDER` | `ollama` | Default LLM provider (`ollama` or `claude`) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama HTTP endpoint (`http://host.docker.internal:11434` in Docker) |
| `OLLAMA_MODEL` | `llama3.2:3b` | Target Ollama model name |
| `ANTHROPIC_API_KEY` | *(empty)* | API key for Anthropic Claude cloud inference |
| `CLAUDE_MODEL` | `claude-3-5-sonnet-20241022` | Target Claude model name |
| `LOG_LEVEL` | `INFO` | Application log verbosity (`DEBUG`, `INFO`, `WARNING`) |

---

## 7. Automated Test Suite

The project includes 39 automated tests covering provider streaming, vector retrieval, short-circuiting, session persistence, and FastAPI endpoints.

### Run Backend Tests (Python / Pytest)
```bash
# Run all 39 unit & integration tests
python -m pytest backend/tests/ -v
```

### Run Frontend Build & Typecheck (Next.js / TypeScript)
```bash
cd frontend
npm run build
```

---

## 8. Manual UI Test Plan

Follow this verification checklist during evaluation:

| # | Test Scenario | Steps | Expected Result |
|:---:|:---|:---|:---|
| **1** | **Health Probe** | Navigate to `http://localhost:8000/api/health` | Returns JSON status `ok` with deep breakdown of `database`, `vector_index`, `ollama`, and `claude`. |
| **2** | **Starter Prompts** | Click the Brian Chesky card on an empty chat | Sends query; status displays *"Searching podcast transcripts..."*, then streams tokens. |
| **3** | **Citation Inspection** | Click any `[Episode: Guest, Timestamp]` chip under an answer | Modal opens displaying the exact retrieved chunk, guest, timestamp, and similarity match percentage. |
| **4** | **Out-of-Domain Refusal** | Ask *"What is the recipe for beef bourguignon?"* | Instant short-circuit (<200ms); refusal banner rendered in muted style with 0 citations; LLM is bypassed. |
| **5** | **Ship 30 Essay Generation** | Click the `✎ Ship 30` button under a grounded answer | Streams an essay; right pane automatically slides open showing title, word count tag (±15% band), and Copy/Download buttons. |
| **6** | **Provider Toggle** | Switch header badge from *Ollama (Local)* to *Claude 3.5 (Cloud)* | Next message sends `X-LLM-Provider: claude` header; response reflects Claude reasoning. |
| **7** | **Session History** | Click `+ New Chat`, send a message, then switch between sessions in sidebar | Conversations maintain independent context; message history and citations persist across reloads. |

---

## 9. Key Technical Trade-Offs

1. **Local 8B/3B vs. Cloud Reasoning Depth:**
   - *Trade-off:* Small local models synthesize less reliably over long context (especially multi-chunk Ship 30 essays).
   - *Mitigation:* Low temperature (`0.3`), rigid section-by-section prompting, and post-generation word-count tolerance validation (`1,062` to `1,437` words).
2. **HNSW vs. IVFFlat Indexing:**
   - *Trade-off:* HNSW trades index build memory for sub-10ms query times at runtime.
   - *Decision:* Optimal for corpus sizes under 50,000 chunks; provides instant retrieval response during interactive chat.
3. **Strict Sandboxing vs. Artifact Interactivity:**
   - *Trade-off:* Omission of `allow-same-origin` prevents embedded scripts from reading cookies or localStorage.
   - *Decision:* Non-negotiable security ceiling. Untrusted LLM-generated HTML must never execute in the parent security origin.
4. **Single-Tenant Deployment vs. Multi-Tenant SaaS:**
   - *Trade-off:* Auth, RBAC, and billing are intentionally omitted.
   - *Decision:* Scoped strictly as a forward-deployed, single-tenant internal tool designed to run inside a client's private VPC or laptop.

---

## 10. Troubleshooting

- **Ollama unreachable:** Ensure `ollama serve` is running. In Docker, `OLLAMA_BASE_URL` should be `http://host.docker.internal:11434`.
- **Database connection error:** Ensure the `db` service is healthy via `docker compose ps`.
- **Embedding model mismatch:** If you swap embedding models after ingestion, the retriever will abort with `CorpusMetadataMismatchError`. Re-run `python backend/scripts/ingest.py --force` to re-embed.
