"""
base.py — Abstract Base Class & Contracts for LLM Providers.

Defines:
- LLMProviderInterface (alias BaseLLMProvider)
- Custom exceptions for typed error handling across providers
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class LLMError(Exception):
    """Base exception for all LLM errors in Lenny Growth Assistant."""
    pass


class LLMProviderError(LLMError):
    """Generic error originating from an LLM provider."""
    def __init__(self, message: str, provider: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code


class LLMConnectionError(LLMProviderError):
    """Raised when the LLM service is unreachable (e.g. Ollama daemon down, network drop)."""
    pass


class LLMAuthenticationError(LLMProviderError):
    """Raised when credentials/API keys are missing or rejected."""
    pass


class LLMTimeoutError(LLMProviderError):
    """Raised when request times out waiting for inference."""
    pass


class LLMResponseError(LLMProviderError):
    """Raised when provider returns an error payload (e.g. 4xx, 5xx, rate limit)."""
    pass


class LLMProviderNotFoundError(LLMError):
    """Raised when an unrecognized provider name is requested."""
    pass


# ---------------------------------------------------------------------------
# Base Provider Interface
# ---------------------------------------------------------------------------

class LLMProviderInterface(ABC):
    """
    Abstract interface for LLM providers.
    
    Adheres to architecture.md §4:
    - BaseLLMProvider contract with identical streaming semantics
    - Enables single-file addition of new providers without branching in chat.py
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Normalized name of the provider (e.g. 'ollama', 'claude')."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Name of the active model backing this provider."""
        pass

    @abstractmethod
    async def generate_response(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> AsyncGenerator[str, None]:
        """
        Stream generated tokens from the LLM.

        Args:
            messages: List of message dictionaries, each with 'role' ('user'|'assistant')
                      and 'content' (str).
            system_prompt: System-level instruction/grounding context.
            temperature: Sampling temperature (default 0.3 per architecture spec).

        Yields:
            str: Next chunk/token of generated text.
        """
        pass

    @abstractmethod
    async def check_health(self) -> dict:
        """
        Probe provider availability and operational readiness.
        
        Returns:
            dict: Health status containing:
                - status: 'ok' | 'down' | 'degraded'
                - provider: str
                - model: str
                - details: str or dict with diagnostic information
        """
        pass

    async def generate_complete(
        self,
        messages: list[dict],
        system_prompt: str = "",
        temperature: float = 0.3,
    ) -> str:
        """
        Convenience method to accumulate the full streaming response into a single string.
        """
        chunks: list[str] = []
        async for chunk in self.generate_response(messages, system_prompt=system_prompt, temperature=temperature):
            chunks.append(chunk)
        return "".join(chunks)


# Architecture spec contract alias
BaseLLMProvider = LLMProviderInterface
