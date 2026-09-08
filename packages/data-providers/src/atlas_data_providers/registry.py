"""Provider selection.

Callers ask for a provider by name and get something that satisfies the
interface, always. If the requested provider is unknown or unconfigured, they
get the null provider rather than an exception — a missing API key must never
take the application down.
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional

from .base import PropertyDataProvider
from .null_provider import NullProvider
from .rentcast import RentCastProvider

logger = logging.getLogger("atlas.providers")

ProviderFactory = Callable[..., PropertyDataProvider]

_REGISTRY: Dict[str, ProviderFactory] = {
    "rentcast": RentCastProvider,
    "none": NullProvider,
    "null": NullProvider,
}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register an additional provider (ATTOM, an MLS feed, county records)."""
    _REGISTRY[name.lower()] = factory


def available_providers() -> List[str]:
    return sorted(set(_REGISTRY) - {"null"})


def get_provider(name: Optional[str] = None, **kwargs) -> PropertyDataProvider:
    """Resolve a provider by name, falling back to the null provider."""
    key = (name or "none").lower()
    factory = _REGISTRY.get(key)
    if factory is None:
        logger.warning("unknown data provider %r; falling back to manual entry", name)
        return NullProvider()

    provider = factory(**kwargs) if kwargs else factory()
    if not provider.is_configured:
        logger.info(
            "data provider %r is not configured; Atlas will use manually entered data",
            key,
        )
        return NullProvider()
    return provider


def describe_providers(rentcast_api_key: Optional[str] = None) -> List[Dict[str, object]]:
    """Status of each known provider, for the settings screen."""
    rentcast = RentCastProvider(api_key=rentcast_api_key)
    return [
        {
            "name": "rentcast",
            "configured": rentcast.is_configured,
            "capabilities": rentcast.capabilities,
            "detail": (
                "Connected. Property details, values, rents and comps can be imported."
                if rentcast.is_configured
                else "No API key configured. Atlas works normally with manually "
                "entered data; set RENTCAST_API_KEY to enable automatic lookups."
            ),
        },
        {
            "name": "attom",
            "configured": False,
            "capabilities": [],
            "detail": "Planned. The provider interface is ready for it.",
        },
    ]
