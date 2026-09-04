"""
claude_provider.py — Anthropic Claude cloud LLM provider implementation.

Uses the official Anthropic Python SDK (AsyncAnthropic) to stream completions.
Enforces API constraints (top-level system prompt, user/assistant role validation)
and translates vendor exceptions into unified LLM exceptions.
"""

import logging
import os
from typing import AsyncGenerator, Optional

from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    RateLimitError,
)

from app.services.llm.base import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderInterface,
    LLMResponseError,
    LLMTimeoutError,
)

logger = logging.getLogger("llm.claude")


class ClaudeProvider(LLMProviderInterface):
    """
    Cloud LLM provider connected to Anthropic Claude.
    
    Default configuration:
    - API Key: env ANTHROPIC_API_KEY
    - Model: env CLAUDE_MODEL or "claude-3-5-sonnet-20241022"
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        client: Optional[AsyncAnthropic] = None,
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ):
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._model = model or os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._client = client
        self._owns_client = client is None

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self) -> AsyncAnthropic:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise LLMAuthenticationError(
                "ANTHROPIC_API_KEY is not configured. Please supply an API key or switch provider to 'ollama'.",
                provider="claude",
            )
        self._client = AsyncAnthropic(
            api_key=self._api_key,
            timeout=self._timeout,
        )
        return self._client

    async def close(self):
        """Close client connection if owned."""
        if self._owns_client and self._client:
            await self._client.close()

    async def generate_response(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> AsyncGenerator[str, None]:
        """
        Stream completion from Claude messages API.
        
        Anthropic API constraints:
        - 'system' must be top-level keyword argument, NOT a role in messages
        - message roles must be 'user' or 'assistant'
        """
        client = self._get_client()

        # Clean messages: remove any misplaced system messages and ensure required keys
        formatted_messages = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                # Append to system prompt rather than leaving in message list
                system_prompt = f"{system_prompt}\n\n{m.get('content', '')}".strip()
            elif role in ("user", "assistant"):
                formatted_messages.append({
                    "role": role,
                    "content": m.get("content", ""),
                })
            else:
                logger.warning("Ignoring message with unsupported role: %s", role)

        if not formatted_messages:
            raise LLMResponseError("Cannot send empty message list to Claude", provider="claude")

        try:
            kwargs = {
                "model": self._model,
                "max_tokens": self._max_tokens,
                "temperature": temperature,
                "messages": formatted_messages,
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            async with client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text

        except AuthenticationError as exc:
            msg = f"Anthropic authentication failed: {str(exc)}. Check your ANTHROPIC_API_KEY."
            logger.error(msg)
            raise LLMAuthenticationError(msg, provider="claude", status_code=401) from exc
        except RateLimitError as exc:
            msg = f"Anthropic rate limit exceeded: {str(exc)}."
            logger.error(msg)
            raise LLMResponseError(msg, provider="claude", status_code=429) from exc
        except APITimeoutError as exc:
            msg = f"Anthropic request timed out after {self._timeout}s: {str(exc)}."
            logger.error(msg)
            raise LLMTimeoutError(msg, provider="claude") from exc
        except APIConnectionError as exc:
            msg = f"Failed to connect to Anthropic API: {str(exc)}."
            logger.error(msg)
            raise LLMConnectionError(msg, provider="claude") from exc
        except APIStatusError as exc:
            msg = f"Anthropic API returned status {exc.status_code}: {exc.message}."
            logger.error(msg)
            raise LLMResponseError(msg, provider="claude", status_code=exc.status_code) from exc

    async def check_health(self) -> dict:
        """
        Probe Claude provider configuration.
        """
        if not self._api_key:
            return {
                "status": "down",
                "provider": "claude",
                "model": self._model,
                "details": "ANTHROPIC_API_KEY is not set.",
            }

        return {
            "status": "ok",
            "provider": "claude",
            "model": self._model,
            "details": "Anthropic API key is configured.",
        }
