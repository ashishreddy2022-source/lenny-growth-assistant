"""
ollama_provider.py — Local Ollama LLM provider implementation.

Uses httpx async client to stream responses from Ollama's /api/chat endpoint.
Handles connection failures, model availability checks, and streaming SSE tokens.
"""

import json
import logging
import os
from typing import AsyncGenerator, Optional

import httpx

from app.services.llm.base import (
    LLMConnectionError,
    LLMProviderInterface,
    LLMResponseError,
    LLMTimeoutError,
)

logger = logging.getLogger("llm.ollama")


class OllamaProvider(LLMProviderInterface):
    """
    Local LLM provider connected to an Ollama daemon.
    
    Default configuration:
    - Base URL: env OLLAMA_BASE_URL or "http://localhost:11434"
    - Model: env OLLAMA_MODEL or "llama3.2:3b"
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        timeout: float = 60.0,
    ):
        self._base_url = (base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self._model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self._timeout = timeout
        self._client = client
        self._owns_client = client is None

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout))
            self._owns_client = True
        return self._client

    async def close(self):
        """Close client connection if owned."""
        if self._owns_client and self._client and not self._client.is_closed:
            await self._client.aclose()

    async def generate_response(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat completion from Ollama /api/chat.
        """
        client = await self._get_client()

        # Build payload with system prompt inserted as first message if provided
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        payload = {
            "model": self._model,
            "messages": formatted_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
            },
        }

        endpoint = f"{self._base_url}/api/chat"

        try:
            async with client.stream("POST", endpoint, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise LLMResponseError(
                        f"Ollama returned HTTP {response.status_code}: {error_text.decode('utf-8', errors='replace')}",
                        provider="ollama",
                        status_code=response.status_code,
                    )

                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning("Failed to parse JSON from Ollama stream: %s (line: %r)", exc, line)
                        continue

                    # Check for error field in stream
                    if "error" in data:
                        raise LLMResponseError(
                            f"Ollama stream error: {data['error']}",
                            provider="ollama",
                        )

                    content = data.get("message", {}).get("content", "")
                    if content:
                        yield content

                    if data.get("done", False):
                        break

        except httpx.ConnectError as exc:
            msg = f"Cannot connect to Ollama at {self._base_url}. Ensure the Ollama daemon is running ('ollama serve')."
            logger.error(msg)
            raise LLMConnectionError(msg, provider="ollama") from exc
        except httpx.TimeoutException as exc:
            msg = f"Request to Ollama at {self._base_url} timed out after {self._timeout}s."
            logger.error(msg)
            raise LLMTimeoutError(msg, provider="ollama") from exc
        except httpx.RequestError as exc:
            msg = f"Ollama network error at {self._base_url}: {str(exc)}"
            logger.error(msg)
            raise LLMConnectionError(msg, provider="ollama") from exc

    async def check_health(self) -> dict:
        """
        Probe Ollama service health and model availability.
        """
        client = await self._get_client()
        endpoint = f"{self._base_url}/api/tags"

        try:
            response = await client.get(endpoint, timeout=3.0)
            if response.status_code != 200:
                return {
                    "status": "down",
                    "provider": "ollama",
                    "model": self._model,
                    "details": f"HTTP {response.status_code} from /api/tags",
                }

            data = response.json()
            models = [m.get("name", "") for m in data.get("models", [])]
            # Match exact model name or prefix (e.g. 'llama3.2:3b' vs 'llama3.2:3b:latest')
            model_found = any(m == self._model or m.startswith(f"{self._model}:") or self._model.startswith(f"{m}:") for m in models)

            if not model_found:
                return {
                    "status": "degraded",
                    "provider": "ollama",
                    "model": self._model,
                    "details": f"Ollama is reachable, but model '{self._model}' is not pulled yet. Run 'ollama pull {self._model}'. Available: {models}",
                }

            return {
                "status": "ok",
                "provider": "ollama",
                "model": self._model,
                "details": f"Ollama running with model '{self._model}' available.",
            }

        except httpx.ConnectError:
            return {
                "status": "down",
                "provider": "ollama",
                "model": self._model,
                "details": f"Unreachable at {self._base_url}. Is Ollama running?",
            }
        except Exception as exc:
            return {
                "status": "down",
                "provider": "ollama",
                "model": self._model,
                "details": f"Health check failed: {str(exc)}",
            }
