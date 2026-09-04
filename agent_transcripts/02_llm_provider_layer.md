# Agent Transcript 02: Multi-Provider LLM Layer

**Date:** 2026-09-04  
**Step:** 3 — Multi-Provider LLM Layer  
**Status:** Complete, 16/16 unit & integration tests passing  

---

## 1. What Was Built

### Files Created & Modified
| File | Purpose |
|------|---------|
| `backend/app/services/llm/base.py` | Abstract interface `LLMProviderInterface` (alias `BaseLLMProvider`), unified error types (`LLMConnectionError`, `LLMAuthenticationError`, `LLMTimeoutError`, `LLMResponseError`, `LLMProviderNotFoundError`) |
| `backend/app/services/llm/ollama_provider.py` | Concrete local provider using `httpx.AsyncClient` to stream NDJSON from Ollama `/api/chat`, health check probing `/api/tags` |
| `backend/app/services/llm/claude_provider.py` | Concrete cloud provider using official `anthropic.AsyncAnthropic` SDK, extracts system prompt to top-level kwarg per API contract, maps vendor errors |
| `backend/app/services/llm/factory.py` | Dynamic provider factory implementing the 3-tier routing hierarchy: header/argument (`X-LLM-Provider`) → `DEFAULT_LLM_PROVIDER` env var → hardcoded fallback (`"ollama"`), with singleton connection pooling and provider registry |
| `backend/app/services/llm/__init__.py` | Package exports for convenient imports across backend |
| `backend/tests/test_llm_providers.py` | Comprehensive test suite covering streaming, error mapping, health checks, routing hierarchy, and extensibility |
| `.env.example` | Updated with `OLLAMA_MODEL=llama3.2:3b` and `CLAUDE_MODEL=claude-3-5-sonnet-20241022` |
| `backend/requirements.txt` | Added `anthropic`, `pytest`, and `pytest-asyncio` |

---

## 2. Architecture & Design Decisions

### 1. Unified Interface with Identical Streaming Semantics (Architecture Spec §4)
Both `OllamaProvider` and `ClaudeProvider` implement:
```python
async def generate_response(
    self, messages: list[dict], system_prompt: str = "", temperature: float = 0.3
) -> AsyncGenerator[str, None]
```
- `chat.py` in Step 5 will never branch on provider type.
- Switching between local (Ollama) and cloud (Claude) is completely transparent to the retrieval pipeline and SSE streaming response generator.

### 2. Provider Selection & Routing Order
The factory resolves provider selection according to the binding specification:
1. Explicit request parameter / `X-LLM-Provider` header from client.
2. `DEFAULT_LLM_PROVIDER` environment variable.
3. Fallback: `"ollama"` (zero-cost, offline default).
Aliases are automatically resolved: `"local"` → `"ollama"`, `"anthropic"` → `"claude"`.

### 3. Error Normalization
Vendor-specific exceptions are caught inside the provider and re-raised as typed domain exceptions inheriting from `LLMProviderError`:
- `LLMConnectionError`: Ollama daemon unreachable or Anthropic connection drops.
- `LLMAuthenticationError`: Missing or invalid `ANTHROPIC_API_KEY`.
- `LLMTimeoutError`: Inference exceeds configured deadline.
- `LLMResponseError`: 4xx/5xx or rate limit responses.
This shields the FastAPI router and SSE stream from vendor-specific error structures.

### 4. System Prompt Handling Discrepancy
- Ollama API expects `role: "system"` in the `messages` array.
- Anthropic API strictly prohibits `role: "system"` in `messages` and requires `system` as a top-level parameter.
`ClaudeProvider` automatically strips any misplaced system messages from the list and appends them to the top-level `system` kwarg, preventing Anthropic API 400 Bad Request errors.

### 5. Health Check & Degraded State Detection
- `OllamaProvider.check_health()` probes `GET /api/tags`. If the daemon is running but the requested model is not downloaded, it returns `status: "degraded"` with instructions (`"Run 'ollama pull ...'"`), rather than falsely reporting "down" or "ok".
- `ClaudeProvider.check_health()` detects whether `ANTHROPIC_API_KEY` is configured before any user message is dispatched.

---

## 3. Test Verification Results

All 16 tests executed via `pytest backend/tests/test_llm_providers.py -v`:
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

============================= 16 passed in 1.65s ==============================
```

---

## 4. Deviations from Spec

None. The implementation strictly adheres to Section 4 of `architecture.md` and Section 3.2 of the take-home assignment brief.

---

## 5. Next Steps

Proceeding to **Step 4 — Retrieval & Ship 30 Skill Routing**:
- `backend/app/services/retrieval/retriever.py`: pgvector cosine similarity search (`top_k=4-6`, `similarity_threshold=0.65`), query embedding via `EMBEDDING_MODEL`, canned out-of-domain short-circuit.
- `backend/app/services/retrieval/citation.py`: Citation syntax validation (`[Episode: Guest Name, Timestamp/Topic]`) and confidence badge calculation.
- `backend/app/services/skills/ship30_writer.py`: Prompt builder encoding Ship 30 for 30 writing principles (~1,250 words, strong hook, skimmable formatting, ±15% word-count verification).
