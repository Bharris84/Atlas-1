"""AI provider abstraction.

Atlas is not tied to a model or a vendor. Everything above this layer talks to
``AIProvider``, and swapping Anthropic for OpenAI — or for nothing at all — is
a configuration change.

The important member of this module is ``NullProvider``. It is not a stub: it
composes real, useful analysis deterministically from the engine's numbers. It
is what makes "Atlas works with no API key" true rather than aspirational, and
it is what every other provider falls back to when a call fails.
"""

from __future__ import annotations

import abc
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("atlas.ai")


class AIProviderError(RuntimeError):
    """The provider could not produce a completion."""


@dataclass(frozen=True)
class Completion:
    text: str
    provider: str
    model: Optional[str] = None
    # True when the text was composed deterministically rather than generated.
    deterministic: bool = False


class AIProvider(abc.ABC):
    name: str = "abstract"

    @property
    @abc.abstractmethod
    def is_configured(self) -> bool: ...

    @abc.abstractmethod
    def complete(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> Completion: ...


class NullProvider(AIProvider):
    """No language model. Returns nothing, so callers compose deterministically.

    Returning empty text rather than raising keeps the "no key configured" path
    identical to the "call failed" path: both end in the deterministic composer.
    """

    name = "null"

    @property
    def is_configured(self) -> bool:
        return True

    def complete(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> Completion:
        return Completion(text="", provider=self.name, deterministic=True)


class AnthropicProvider(AIProvider):
    name = "anthropic"
    default_model = "claude-sonnet-5"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 60.0,
        client: Any = None,
    ) -> None:
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._model = model or os.getenv("ATLAS_AI_MODEL") or self.default_model
        self._timeout = timeout_seconds
        self._client = client

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def complete(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> Completion:
        if not self.is_configured:
            raise AIProviderError("ANTHROPIC_API_KEY is not configured.")
        client = self._client
        if client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise AIProviderError(
                    "The anthropic package is not installed. Install it, or set "
                    "ATLAS_AI_PROVIDER=null to use deterministic analysis."
                ) from exc
            client = anthropic.Anthropic(api_key=self._api_key, timeout=self._timeout)
        try:
            message = client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                block.text for block in message.content if getattr(block, "type", "") == "text"
            )
        except Exception as exc:
            raise AIProviderError(f"Anthropic request failed: {exc}") from exc
        return Completion(text=text, provider=self.name, model=self._model)


class OpenAIProvider(AIProvider):
    name = "openai"
    default_model = "gpt-4o"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: float = 60.0,
        client: Any = None,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model or os.getenv("ATLAS_AI_MODEL") or self.default_model
        self._timeout = timeout_seconds
        self._client = client

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def complete(
        self,
        system: str,
        prompt: str,
        max_tokens: int = 1500,
        temperature: float = 0.2,
    ) -> Completion:
        if not self.is_configured:
            raise AIProviderError("OPENAI_API_KEY is not configured.")
        client = self._client
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise AIProviderError(
                    "The openai package is not installed. Install it, or set "
                    "ATLAS_AI_PROVIDER=null to use deterministic analysis."
                ) from exc
            client = OpenAI(api_key=self._api_key, timeout=self._timeout)
        try:
            response = client.chat.completions.create(
                model=self._model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            text = response.choices[0].message.content or ""
        except Exception as exc:
            raise AIProviderError(f"OpenAI request failed: {exc}") from exc
        return Completion(text=text, provider=self.name, model=self._model)


_PROVIDERS = {
    "null": NullProvider,
    "none": NullProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
}


def get_ai_provider(name: Optional[str] = None, **kwargs: Any) -> AIProvider:
    """Resolve an AI provider, falling back to deterministic analysis.

    An unknown name or a missing key never raises. Losing narration is an
    acceptable degradation; losing the application is not.
    """
    key = (name or "null").lower()
    factory = _PROVIDERS.get(key)
    if factory is None:
        logger.warning("unknown AI provider %r; using deterministic analysis", name)
        return NullProvider()
    provider = factory(**kwargs) if kwargs else factory()
    if not provider.is_configured:
        logger.info("AI provider %r is not configured; using deterministic analysis", key)
        return NullProvider()
    return provider


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pull a JSON object out of a model response.

    Models wrap JSON in prose and code fences. Returning ``None`` on failure
    lets the caller fall back to deterministic output instead of surfacing a
    parse error to the user.
    """
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("```")[1] if "```" in candidate[3:] else candidate[3:]
        if candidate.startswith("json"):
            candidate = candidate[4:]
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(candidate[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def as_string_list(value: Any, limit: int = 12) -> List[str]:
    """Coerce a model-supplied field into a bounded list of clean strings."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    output: List[str] = []
    for item in value[:limit]:
        if isinstance(item, str) and item.strip():
            output.append(item.strip()[:600])
        elif isinstance(item, dict):
            text = item.get("text") or item.get("detail") or item.get("label")
            if isinstance(text, str) and text.strip():
                output.append(text.strip()[:600])
    return output
