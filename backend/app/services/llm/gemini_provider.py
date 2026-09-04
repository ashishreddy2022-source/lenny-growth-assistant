"""
gemini_provider.py — Google Gemini LLM provider (free tier).

Uses google-generativeai SDK to stream completions via Gemini 1.5 Flash.
Free tier: 15 requests/min, 1500 requests/day (no billing required).
Get your key at: https://aistudio.google.com/app/apikey
"""

import logging
import os
from typing import AsyncGenerator, Optional

from app.services.llm.base import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMProviderInterface,
    LLMResponseError,
    LLMTimeoutError,
)

logger = logging.getLogger("llm.gemini")


class GeminiProvider(LLMProviderInterface):
    """
    Google Gemini cloud LLM provider.

    Default configuration:
    - API Key: env GEMINI_API_KEY (also accepts GOOGLE_API_KEY)
    - Model: env GEMINI_MODEL or "gemini-1.5-flash"  (free tier)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        timeout: float = 60.0,
    ):
        self._api_key = (
            api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        self._model = model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        self._max_tokens = max_tokens
        self._timeout = timeout

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self):
        """Lazy-initialize the Gemini client."""
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise LLMConnectionError(
                "google-generativeai package is not installed. Run: pip install google-generativeai",
                provider="gemini",
            ) from exc

        if not self._api_key:
            raise LLMAuthenticationError(
                "GEMINI_API_KEY is not configured. "
                "Get a free key at https://aistudio.google.com/app/apikey "
                "and set it as GEMINI_API_KEY on Render.",
                provider="gemini",
            )

        genai.configure(api_key=self._api_key)
        return genai.GenerativeModel(
            model_name=self._model,
            generation_config={
                "max_output_tokens": self._max_tokens,
                "temperature": 0.3,
            },
        )

    async def generate_response(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> AsyncGenerator[str, None]:
        """
        Stream completion from Gemini.

        Gemini uses a 'contents' list with 'user'/'model' roles.
        System prompt is prepended as the first user turn.
        """
        try:
            import google.generativeai as genai
            from google.api_core.exceptions import (
                GoogleAPICallError,
                InvalidArgument,
                PermissionDenied,
                ResourceExhausted,
                ServiceUnavailable,
            )
        except ImportError as exc:
            raise LLMConnectionError(
                "google-generativeai package is not installed.",
                provider="gemini",
            ) from exc

        model = self._get_client()

        # Build Gemini contents list (role: 'user' | 'model')
        contents = []

        # Inject system prompt as a leading user message if provided
        if system_prompt:
            contents.append({"role": "user", "parts": [system_prompt]})
            contents.append({"role": "model", "parts": ["Understood. I will follow these instructions."]})

        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            # Gemini uses 'model' instead of 'assistant'
            gemini_role = "model" if role == "assistant" else "user"
            if content:
                contents.append({"role": gemini_role, "parts": [content]})

        if not contents:
            raise LLMResponseError("Cannot send empty messages to Gemini", provider="gemini")

        try:
            # Override temperature per-call
            model._generation_config["temperature"] = temperature  # type: ignore[index]

            response = await model.generate_content_async(
                contents,
                stream=True,
            )

            async for chunk in response:
                if chunk.text:
                    yield chunk.text

        except PermissionDenied as exc:
            msg = f"Gemini authentication failed: {exc}. Check your GEMINI_API_KEY."
            logger.error(msg)
            raise LLMAuthenticationError(msg, provider="gemini", status_code=403) from exc
        except ResourceExhausted as exc:
            msg = f"Gemini rate limit exceeded (free tier: 15 req/min): {exc}."
            logger.error(msg)
            raise LLMResponseError(msg, provider="gemini", status_code=429) from exc
        except InvalidArgument as exc:
            msg = f"Gemini invalid request: {exc}."
            logger.error(msg)
            raise LLMResponseError(msg, provider="gemini", status_code=400) from exc
        except ServiceUnavailable as exc:
            msg = f"Gemini service unavailable: {exc}."
            logger.error(msg)
            raise LLMConnectionError(msg, provider="gemini") from exc
        except GoogleAPICallError as exc:
            msg = f"Gemini API error: {exc}."
            logger.error(msg)
            raise LLMResponseError(msg, provider="gemini") from exc
        except Exception as exc:
            msg = f"Unexpected Gemini error: {exc}."
            logger.error(msg, exc_info=True)
            raise LLMResponseError(msg, provider="gemini") from exc

    async def check_health(self) -> dict:
        """Probe Gemini provider configuration."""
        if not self._api_key:
            return {
                "status": "down",
                "provider": "gemini",
                "model": self._model,
                "details": (
                    "GEMINI_API_KEY is not set. "
                    "Get a free key at https://aistudio.google.com/app/apikey"
                ),
            }

        return {
            "status": "ok",
            "provider": "gemini",
            "model": self._model,
            "details": "Gemini API key is configured (free tier: 15 req/min).",
        }
