"""
factory.py — Dynamic LLM provider factory with fallback routing.

Implements architecture.md §4 model selection hierarchy:
  1. Request parameter / header (X-LLM-Provider)
  2. DEFAULT_LLM_PROVIDER env variable
  3. Hardcoded fallback ("gemini")

Provides registry for easy extension (e.g. adding openai_provider.py later).
Caches provider instances to share HTTP connection pools.
"""

import logging
import os
from typing import Optional, Type

from app.services.llm.base import (
    LLMProviderInterface,
    LLMProviderNotFoundError,
)
from app.services.llm.claude_provider import ClaudeProvider
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.ollama_provider import OllamaProvider

logger = logging.getLogger("llm.factory")

# Registry of provider implementations
PROVIDER_REGISTRY: dict[str, Type[LLMProviderInterface]] = {
    "ollama": OllamaProvider,
    "local": OllamaProvider,
    "claude": ClaudeProvider,
    "anthropic": ClaudeProvider,
    "gemini": GeminiProvider,
    "google": GeminiProvider,
}

# Cached singleton instances per provider key
_PROVIDER_INSTANCES: dict[str, LLMProviderInterface] = {}


def register_provider(name: str, provider_cls: Type[LLMProviderInterface]) -> None:
    """
    Register a custom or new provider implementation (e.g. OpenAI).
    """
    normalized_name = name.strip().lower()
    PROVIDER_REGISTRY[normalized_name] = provider_cls
    logger.info("Registered LLM provider: '%s' -> %s", normalized_name, provider_cls.__name__)


def resolve_provider_name(requested_name: Optional[str] = None) -> str:
    """
    Resolve which provider to use based on the architecture selection order:
    1. Requested name (from header X-LLM-Provider or API payload)
    2. DEFAULT_LLM_PROVIDER env var
    3. Fallback: 'ollama'
    """
    if requested_name and requested_name.strip():
        name = requested_name.strip().lower()
    else:
        env_default = os.getenv("DEFAULT_LLM_PROVIDER", "").strip().lower()
        name = env_default if env_default else "gemini"
    return name


def get_llm_provider(
    provider_name: Optional[str] = None,
    reuse_cached: bool = True,
    **kwargs,
) -> LLMProviderInterface:
    """
    Get an instance of the resolved LLM provider.

    Args:
        provider_name: Explicit provider name ('ollama', 'claude', etc.).
                       If None, resolves from env or default.
        reuse_cached: If True, reuses existing cached instance for connection pooling.
                      Set to False in tests or when overriding parameters.
        **kwargs: Optional constructor arguments passed to the provider class.

    Returns:
        LLMProviderInterface: Ready-to-use provider instance.

    Raises:
        LLMProviderNotFoundError: If provider name cannot be resolved to a registered class.
    """
    resolved_name = resolve_provider_name(provider_name)

    provider_cls = PROVIDER_REGISTRY.get(resolved_name)
    if provider_cls is None:
        supported = sorted(list(set(PROVIDER_REGISTRY.keys())))
        raise LLMProviderNotFoundError(
            f"Unsupported LLM provider '{resolved_name}'. Supported providers: {supported}"
        )

    cache_key = f"{resolved_name}_{sorted(kwargs.items())}" if kwargs else resolved_name

    if reuse_cached and cache_key in _PROVIDER_INSTANCES:
        return _PROVIDER_INSTANCES[cache_key]

    instance = provider_cls(**kwargs)
    if reuse_cached and not kwargs:
        _PROVIDER_INSTANCES[cache_key] = instance

    logger.debug("Instantiated LLM provider '%s' (%s)", resolved_name, provider_cls.__name__)
    return instance


def reset_provider_registry() -> None:
    """Clear cached instances (useful for test tearDown)."""
    _PROVIDER_INSTANCES.clear()
