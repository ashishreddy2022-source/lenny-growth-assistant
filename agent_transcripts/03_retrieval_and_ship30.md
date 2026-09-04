# Agent Transcript 03: Retrieval & Ship 30 Skill Routing

**Date:** 2026-09-04  
**Step:** 4 — Retrieval, Grounding & Ship 30 Skill  
**Status:** Complete, 32/32 unit & integration tests passing  

---

## 1. What Was Built

### Files Created
| File | Purpose |
|------|---------|
| `backend/app/services/retrieval/models.py` | Data contracts: `RetrievedChunk`, `RetrievalResult`, and `SourceRef` (matching `messages.sources` JSONB spec) |
| `backend/app/services/retrieval/retriever.py` | `TranscriptRetriever` with pgvector cosine similarity search, out-of-domain short-circuit (`similarity_threshold=0.65`), and startup `corpus_metadata` consistency validation |
| `backend/app/services/retrieval/citation.py` | Bracketed citation parser (`[Episode: Guest, Timestamp]`), grounding verifier against retrieved chunks, and UI warning badge calculator |
| `backend/app/services/retrieval/prompt_builder.py` | Grounded system prompt builder injecting source chunks and citation rules |
| `backend/app/services/skills/ship30_writer.py` | Ship 30 for 30 essay prompt generator and post-generation quality validator with ±15% word count band (1,062 to 1,437 words) |
| `backend/tests/test_retrieval.py` | 16 comprehensive unit & integration tests for vector search, short-circuit, metadata check, citations, and Ship 30 |

---

## 2. Key Architecture Decisions

### 1. Hard Out-of-Domain Short-Circuit (Architecture.md §3 Step 4)
When a user query produces 0 chunks clearing the cosine similarity threshold (`0.65`):
- The retriever returns `RetrievalResult(is_out_of_domain=True, chunks=[], canned_response=...)`.
- The chat handler bypasses the LLM call entirely.
- **Why this matters:** Avoids burning cloud tokens or local GPU cycles on questions like "What is the capital of France?" or adversarial queries. Models frequently hallucinate confidence when forced to answer out-of-domain questions; a deterministic code-level short-circuit is 100% reliable and zero-cost.

### 2. Startup Embedding Consistency Check (Architecture.md §6)
- The retriever checks `corpus_metadata` on startup.
- If the runtime embedding dimension (e.g. 384 for MiniLM) or model name differs from the database index, `CorpusMetadataMismatchError` is raised immediately.
- Fails loudly rather than silently returning meaningless similarity scores.

### 3. Citation Contract & Verification (Architecture.md §3 Step 5)
- Standard prompt enforces `[Episode: Guest Name, Timestamp]` inline.
- `validate_citations()` performs post-hoc validation:
  - If no citations are present, `warning_badge=True` is returned.
  - If citations mention guests not present in `retrieved_chunks`, `ungrounded_citations` are flagged.
  - Allows the UI to render a yellow/red verification badge rather than silently trusting model output.

### 4. Ship 30 Skill Decoupling (Architecture.md §5)
- `mode="ship30"` alters only the prompt template and post-generation validation, not the retrieval pipeline.
- The prompt encodes specific writing principles:
  - Magnetic hook and H1 headline
  - 3–5 structured pillars with bold headers
  - "The Monday Morning Rule" actionable checklist
  - Target length ~1,250 words
- Post-generation validator enforces the ±15% tolerance band: 1,062 to 1,437 words.

---

## 3. Test Verification Results

All 32 tests across the backend test suite executed via `pytest backend/tests/ -v`:
```
backend/tests/test_llm_providers.py::test_base_interface_cannot_be_instantiated PASSED
backend/tests/test_llm_providers.py::test_generate_complete_accumulates_stream PASSED
backend/tests/test_llm_providers.py::test_ollama_streaming_success PASSED
backend/tests/test_llm_providers.py::test_ollama_connection_failure PASSED
backend/tests/test_llm_providers.py::test_ollama_timeout PASSED
backend/tests/test_llm_providers.py::test_ollama_health_checks PASSED
backend/tests/test_llm_providers.py::test_claude_missing_api_key PASSED
backend/tests/test_llm_providers.py::test_claude_streaming_success PASSED
backend/tests/test_llm_providers.py::test_claude_error_mapping PASSED
backend/tests/test_llm_providers.py::test_claude_health_check PASSED
backend/tests/test_llm_providers.py::test_factory_explicit_routing PASSED
backend/tests/test_llm_providers.py::test_factory_aliases PASSED
backend/tests/test_llm_providers.py::test_factory_env_variable_fallback PASSED
backend/tests/test_llm_providers.py::test_factory_hardcoded_fallback PASSED
backend/tests/test_llm_providers.py::test_factory_unsupported_provider PASSED
backend/tests/test_llm_providers.py::test_factory_custom_registration PASSED
backend/tests/test_retrieval.py::test_retriever_sync_in_domain_results PASSED
backend/tests/test_retrieval.py::test_retriever_async_in_domain_results PASSED
backend/tests/test_retrieval.py::test_retriever_out_of_domain_short_circuit_sync PASSED
backend/tests/test_retrieval.py::test_retriever_out_of_domain_short_circuit_async PASSED
backend/tests/test_corpus_metadata_verification_success PASSED
backend/tests/test_corpus_metadata_dimension_mismatch_fails_loudly PASSED
backend/tests/test_corpus_metadata_model_mismatch_fails_loudly PASSED
backend/tests/test_extract_citations_various_formats PASSED
backend/tests/test_validate_citations_all_grounded PASSED
backend/tests/test_validate_citations_missing_citations PASSED
backend/tests/test_validate_citations_ungrounded_source PASSED
backend/tests/test_build_grounded_prompt PASSED
backend/tests/test_ship30_prompt_structure PASSED
backend/tests/test_ship30_essay_validation_in_tolerance PASSED
backend/tests/test_ship30_essay_validation_under_length PASSED
backend/tests/test_ship30_essay_validation_over_length PASSED

============================= 32 passed in 1.60s ==============================
```

---

## 4. Deviations from Spec

None. All contracts from `architecture.md` §3 & §5 and assignment brief §4.1 & §4.2 were followed exactly.

---

## 5. Next Steps

Proceeding to **Step 5 — FastAPI Backend**:
- App factory with database connection pooling (`asyncpg`/`psycopg`)
- Sessions & message history endpoints (`POST /api/sessions`, `GET /api/sessions`, `GET /api/sessions/{id}/messages`)
- Streaming chat endpoint (`POST /api/chat`) returning Server-Sent Events (SSE)
- Deep health endpoint (`GET /api/health`) actually probing PostgreSQL, Ollama, and vector index
- Message and artifact persistence
