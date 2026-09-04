"""
test_llm_providers.py — Comprehensive unit tests for Multi-Provider LLM Layer.

Validates:
1. Base interface contracts and abstract constraints
2. OllamaProvider streaming, error handling (connection, timeout), and health check
3. ClaudeProvider streaming, role formatting, error mapping, and health check
4. Factory provider resolution order: header/arg -> env var -> hardcoded fallback
5. Factory alias resolution and custom provider registration
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from anthropic import (
    APIConnectionError,
    AuthenticationError,
    RateLimitError,
)

from app.services.llm.base import (
    BaseLLMProvider,
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderInterface,
    LLMProviderNotFoundError,
    LLMResponseError,
    LLMTimeoutError,
)
from app.services.llm.claude_provider import ClaudeProvider
from app.services.llm.factory import (
    get_llm_provider,
    register_provider,
    reset_provider_registry,
    resolve_provider_name,
)
from app.services.llm.ollama_provider import OllamaProvider


# ---------------------------------------------------------------------------
# Test 1: Base Interface & Abstract Methods
# ---------------------------------------------------------------------------

def test_base_interface_cannot_be_instantiated():
    """Verify that BaseLLMProvider / LLMProviderInterface cannot be instantiated directly."""
    with pytest.raises(TypeError):
        LLMProviderInterface()  # type: ignore

    with pytest.raises(TypeError):
        BaseLLMProvider()  # type: ignore


@pytest.mark.asyncio
async def test_generate_complete_accumulates_stream():
    """Verify that default generate_complete() correctly joins stream chunks."""
    class DummyProvider(LLMProviderInterface):
        @property
        def provider_name(self) -> str:
            return "dummy"

        @property
        def model_name(self) -> str:
            return "dummy-1"

        async def generate_response(self, messages, system_prompt="", temperature=0.3):
            for word in ["Testing ", "1, ", "2, ", "3."]:
                yield word

        async def check_health(self):
            return {"status": "ok"}

    provider = DummyProvider()
    result = await provider.generate_complete([{"role": "user", "content": "hi"}])
    assert result == "Testing 1, 2, 3."


# ---------------------------------------------------------------------------
# Test 2: Ollama Provider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ollama_streaming_success():
    """Verify OllamaProvider streams tokens from NDJSON response."""
    ndjson_lines = [
        json.dumps({"message": {"content": "Product "}, "done": False}),
        json.dumps({"message": {"content": "market "}, "done": False}),
        json.dumps({"message": {"content": "fit."}, "done": True}),
    ]

    async def mock_aiter_lines():
        for line in ndjson_lines:
            yield line

    mock_stream_response = AsyncMock()
    mock_stream_response.status_code = 200
    mock_stream_response.aiter_lines = mock_aiter_lines

    # Mock context manager returned by client.stream()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_stream_response
    mock_cm.__aexit__.return_value = None

    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.stream = MagicMock(return_value=mock_cm)

    provider = OllamaProvider(
        base_url="http://mock-ollama:11434",
        model="llama3.2:3b",
        client=mock_client,
    )

    tokens = []
    messages = [{"role": "user", "content": "What is PMF?"}]
    async for token in provider.generate_response(messages, system_prompt="You are Lenny."):
        tokens.append(token)

    assert tokens == ["Product ", "market ", "fit."]
    assert "".join(tokens) == "Product market fit."

    # Verify payload format
    mock_client.stream.assert_called_once()
    _, call_kwargs = mock_client.stream.call_args
    payload = call_kwargs["json"]
    assert payload["model"] == "llama3.2:3b"
    assert payload["stream"] is True
    assert payload["options"]["temperature"] == 0.3
    # Check that system prompt is prepended as first message
    assert payload["messages"][0] == {"role": "system", "content": "You are Lenny."}
    assert payload["messages"][1] == {"role": "user", "content": "What is PMF?"}


@pytest.mark.asyncio
async def test_ollama_connection_failure():
    """Verify OllamaProvider raises LLMConnectionError on network connection failure."""
    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_cm = AsyncMock()
    mock_cm.__aenter__.side_effect = httpx.ConnectError("Connection refused")
    mock_client.stream = MagicMock(return_value=mock_cm)

    provider = OllamaProvider(
        base_url="http://localhost:11434",
        client=mock_client,
    )

    with pytest.raises(LLMConnectionError) as exc_info:
        async for _ in provider.generate_response([{"role": "user", "content": "hi"}]):
            pass

    assert "Cannot connect to Ollama" in str(exc_info.value)
    assert exc_info.value.provider == "ollama"


@pytest.mark.asyncio
async def test_ollama_timeout():
    """Verify OllamaProvider raises LLMTimeoutError on timeout."""
    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_cm = AsyncMock()
    mock_cm.__aenter__.side_effect = httpx.TimeoutException("Read timed out")
    mock_client.stream = MagicMock(return_value=mock_cm)

    provider = OllamaProvider(client=mock_client)

    with pytest.raises(LLMTimeoutError):
        async for _ in provider.generate_response([{"role": "user", "content": "hi"}]):
            pass


@pytest.mark.asyncio
async def test_ollama_health_checks():
    """Verify Ollama health check reporting ok, degraded, and down."""
    mock_client = AsyncMock()
    mock_client.is_closed = False

    # 1. OK case: model is present
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [{"name": "llama3.2:3b:latest"}]
    }
    mock_client.get.return_value = mock_resp

    provider = OllamaProvider(model="llama3.2:3b", client=mock_client)
    health = await provider.check_health()
    assert health["status"] == "ok"

    # 2. Degraded case: server reachable, but model missing
    mock_resp.json.return_value = {
        "models": [{"name": "mistral:latest"}]
    }
    health_degraded = await provider.check_health()
    assert health_degraded["status"] == "degraded"
    assert "ollama pull" in health_degraded["details"]

    # 3. Down case: server unreachable
    mock_client.get.side_effect = httpx.ConnectError("Daemon down")
    health_down = await provider.check_health()
    assert health_down["status"] == "down"


# ---------------------------------------------------------------------------
# Test 3: Claude Provider
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_claude_missing_api_key():
    """Verify ClaudeProvider raises LLMAuthenticationError if ANTHROPIC_API_KEY is missing."""
    with patch.dict("os.environ", {}, clear=True):
        provider = ClaudeProvider(api_key=None)
        with pytest.raises(LLMAuthenticationError) as exc_info:
            async for _ in provider.generate_response([{"role": "user", "content": "hello"}]):
                pass
        assert "ANTHROPIC_API_KEY is not configured" in str(exc_info.value)


@pytest.mark.asyncio
async def test_claude_streaming_success():
    """Verify ClaudeProvider formats messages and streams tokens from AsyncAnthropic."""
    mock_stream = AsyncMock()
    
    async def mock_text_stream():
        for chunk in ["Great ", "growth ", "loop."]:
            yield chunk

    mock_stream.text_stream = mock_text_stream()
    mock_stream_cm = AsyncMock()
    mock_stream_cm.__aenter__.return_value = mock_stream
    mock_stream_cm.__aexit__.return_value = None

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.stream.return_value = mock_stream_cm

    provider = ClaudeProvider(
        api_key="sk-ant-test-mock-key",
        model="claude-3-5-sonnet-20241022",
        client=mock_client,
    )

    tokens = []
    messages = [{"role": "user", "content": "How to build growth loops?"}]
    async for token in provider.generate_response(messages, system_prompt="Expert PM Advisor."):
        tokens.append(token)

    assert tokens == ["Great ", "growth ", "loop."]
    
    # Verify Anthropic API structure:
    # - system must be a kwarg, NOT in messages
    # - messages only has user/assistant
    mock_client.messages.stream.assert_called_once()
    call_kwargs = mock_client.messages.stream.call_args[1]
    assert call_kwargs["system"] == "Expert PM Advisor."
    assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"
    assert call_kwargs["messages"] == [{"role": "user", "content": "How to build growth loops?"}]


@pytest.mark.asyncio
async def test_claude_error_mapping():
    """Verify ClaudeProvider maps vendor errors to unified LLM exceptions."""
    mock_client = MagicMock()
    mock_client.messages = MagicMock()

    # 1. Authentication Error
    mock_client.messages.stream.side_effect = AuthenticationError(
        message="Invalid API Key",
        response=httpx.Response(401, request=httpx.Request("POST", "http://test")),
        body=None,
    )
    provider = ClaudeProvider(api_key="invalid-key", client=mock_client)
    with pytest.raises(LLMAuthenticationError):
        async for _ in provider.generate_response([{"role": "user", "content": "hi"}]):
            pass

    # 2. Rate Limit Error
    mock_client.messages.stream.side_effect = RateLimitError(
        message="Rate limit exceeded",
        response=httpx.Response(429, request=httpx.Request("POST", "http://test")),
        body=None,
    )
    with pytest.raises(LLMResponseError) as exc_info:
        async for _ in provider.generate_response([{"role": "user", "content": "hi"}]):
            pass
    assert exc_info.value.status_code == 429

    # 3. Connection Error
    mock_client.messages.stream.side_effect = APIConnectionError(
        request=httpx.Request("POST", "http://test")
    )
    with pytest.raises(LLMConnectionError):
        async for _ in provider.generate_response([{"role": "user", "content": "hi"}]):
            pass


@pytest.mark.asyncio
async def test_claude_health_check():
    """Verify ClaudeProvider health check output."""
    provider_no_key = ClaudeProvider(api_key="")
    health = await provider_no_key.check_health()
    assert health["status"] == "down"

    provider_with_key = ClaudeProvider(api_key="sk-ant-test")
    health = await provider_with_key.check_health()
    assert health["status"] == "ok"


# ---------------------------------------------------------------------------
# Test 4: Factory Routing Hierarchy
# ---------------------------------------------------------------------------

def test_factory_explicit_routing():
    """Verify factory returns appropriate provider when requested explicitly."""
    reset_provider_registry()

    ollama = get_llm_provider("ollama", reuse_cached=False)
    assert isinstance(ollama, OllamaProvider)
    assert ollama.provider_name == "ollama"

    claude = get_llm_provider("claude", reuse_cached=False)
    assert isinstance(claude, ClaudeProvider)
    assert claude.provider_name == "claude"


def test_factory_aliases():
    """Verify factory aliases ('local' -> Ollama, 'anthropic' -> Claude)."""
    local = get_llm_provider("local", reuse_cached=False)
    assert isinstance(local, OllamaProvider)

    anthropic = get_llm_provider("anthropic", reuse_cached=False)
    assert isinstance(anthropic, ClaudeProvider)


def test_factory_env_variable_fallback():
    """Verify factory honors DEFAULT_LLM_PROVIDER env variable when no header/arg provided."""
    reset_provider_registry()

    with patch.dict("os.environ", {"DEFAULT_LLM_PROVIDER": "claude"}):
        provider = get_llm_provider(None, reuse_cached=False)
        assert isinstance(provider, ClaudeProvider)

    with patch.dict("os.environ", {"DEFAULT_LLM_PROVIDER": "ollama"}):
        provider = get_llm_provider(None, reuse_cached=False)
        assert isinstance(provider, OllamaProvider)


def test_factory_hardcoded_fallback():
    """Verify factory falls back to 'ollama' when no arg and no env var are present."""
    reset_provider_registry()
    with patch.dict("os.environ", {}, clear=True):
        provider = get_llm_provider(None, reuse_cached=False)
        assert isinstance(provider, OllamaProvider)


def test_factory_unsupported_provider():
    """Verify factory raises LLMProviderNotFoundError for unknown providers."""
    with pytest.raises(LLMProviderNotFoundError) as exc_info:
        get_llm_provider("deepseek_unregistered")
    assert "Unsupported LLM provider 'deepseek_unregistered'" in str(exc_info.value)


def test_factory_custom_registration():
    """Verify that new providers can be registered dynamically."""
    class CustomProvider(LLMProviderInterface):
        @property
        def provider_name(self) -> str:
            return "custom"

        @property
        def model_name(self) -> str:
            return "custom-v1"

        async def generate_response(self, messages, system_prompt="", temperature=0.3):
            yield "custom"

        async def check_health(self):
            return {"status": "ok"}

    register_provider("custom_model", CustomProvider)
    provider = get_llm_provider("custom_model", reuse_cached=False)
    assert isinstance(provider, CustomProvider)
    assert provider.provider_name == "custom"
