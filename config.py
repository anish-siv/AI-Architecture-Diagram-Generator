"""
Configuration — resolves LLM provider settings from environment variables
and CLI flags with automatic fallback.
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    provider: Optional[str]   # "openai", "anthropic", or None (rules-only)
    model: Optional[str]
    api_key: Optional[str]

    @property
    def ai_enabled(self) -> bool:
        return self.provider is not None and self.api_key is not None


DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
}

_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


def resolve_config(
    cli_provider: Optional[str] = None,
    cli_model: Optional[str] = None,
    no_ai: bool = False,
) -> Config:
    """
    Build a Config by combining CLI flags with environment variables.

    Priority:
    1. --no-ai  → rules-only, ignore everything else
    2. --provider explicitly set → use that provider, fail if key missing
    3. Auto-detect: pick the first provider whose env key is set
    """
    if no_ai:
        return Config(provider=None, model=None, api_key=None)

    if cli_provider:
        provider = cli_provider.lower()
        if provider not in _ENV_KEYS:
            raise ValueError(
                f"Unknown provider '{provider}'. "
                f"Choose from: {', '.join(_ENV_KEYS)}"
            )
        api_key = os.environ.get(_ENV_KEYS[provider])
        if not api_key:
            raise EnvironmentError(
                f"Provider '{provider}' requested but "
                f"{_ENV_KEYS[provider]} is not set."
            )
        model = cli_model or DEFAULT_MODELS[provider]
        return Config(provider=provider, model=model, api_key=api_key)

    # Auto-detect: try each provider in order
    for provider, env_var in _ENV_KEYS.items():
        api_key = os.environ.get(env_var)
        if api_key:
            model = cli_model or DEFAULT_MODELS[provider]
            return Config(provider=provider, model=model, api_key=api_key)

    # No keys found — fall back to rules-only
    return Config(provider=None, model=None, api_key=None)
