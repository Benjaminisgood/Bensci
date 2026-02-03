"""Fetcher toolkit to download full-text assets from multiple providers."""

from __future__ import annotations

from .base import BaseFetcher
from .registry import available_fetchers, describe_fetchers, get_fetcher, register_fetcher

# Ensure built-in providers are registered.
from .providers import __all__ as _PROVIDERS  # noqa: F401

__all__ = [
    "BaseFetcher",
    "available_fetchers",
    "describe_fetchers",
    "get_fetcher",
    "register_fetcher",
]
