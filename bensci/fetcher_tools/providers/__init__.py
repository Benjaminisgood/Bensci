"""Built-in fetcher providers."""

from __future__ import annotations

import logging
from importlib import import_module

LOGGER = logging.getLogger(__name__)

PROVIDER_MODULES = ("elsevier", "springer", "acs", "wiley", "rsc", "scihub")
_LOADED_PROVIDERS: list[str] = []

for name in PROVIDER_MODULES:
    try:
        import_module(f".{name}", __name__)
    except Exception as exc:  # pragma: no cover - 仅记录日志并跳过
        LOGGER.warning("全文抓取器 %s 加载失败，已跳过：%s", name, exc)
        continue
    _LOADED_PROVIDERS.append(name)

__all__ = _LOADED_PROVIDERS
