"""Registry for full-text fetchers."""

from __future__ import annotations

from typing import Dict, List, Type

from .base import BaseFetcher

_REGISTRY: Dict[str, Type[BaseFetcher]] = {}


def register_fetcher(name: str, fetcher_cls: Type[BaseFetcher]) -> None:
    _REGISTRY[name.lower()] = fetcher_cls


def get_fetcher(name: str, **kwargs) -> BaseFetcher:
    fetcher_cls = _REGISTRY.get(name.lower())
    if not fetcher_cls:
        raise KeyError(f"未注册的 fetcher：{name}")
    return fetcher_cls(**kwargs)


def available_fetchers() -> List[str]:
    return sorted(_REGISTRY.keys())


def describe_fetchers() -> Dict[str, Dict[str, str]]:
    info: Dict[str, Dict[str, str]] = {}
    for name, cls in _REGISTRY.items():
        info[name] = {
            "content_type": getattr(cls, "content_type", "unknown"),
            "output_suffix": getattr(cls, "output_suffix", ""),
        }
    return info
