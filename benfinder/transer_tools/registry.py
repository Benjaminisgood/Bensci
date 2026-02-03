"""Registry for document parsing adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, Type

from .parser_base import BaseParser

_REGISTRY: Dict[str, Type[BaseParser]] = {}
_DETECTION_ORDER: List[Tuple[int, str]] = []


def register_parser(name: str, parser_cls: Type[BaseParser], *, priority: int = 100) -> None:
    key = name.lower()
    _REGISTRY[key] = parser_cls

    for idx, (_, registered_key) in enumerate(_DETECTION_ORDER):
        if registered_key == key:
            _DETECTION_ORDER[idx] = (priority, key)
            break
    else:
        _DETECTION_ORDER.append((priority, key))

    _DETECTION_ORDER.sort(key=lambda item: item[0])


def get_parser(name: str) -> Type[BaseParser]:
    parser_cls = _REGISTRY.get(name.lower())
    if parser_cls is None:
        raise KeyError(f"未注册的解析器：{name}")
    return parser_cls


def available_parsers() -> List[str]:
    return sorted(_REGISTRY.keys())


def describe_parsers() -> Dict[str, Dict[str, str]]:
    info: Dict[str, Dict[str, str]] = {}
    for name, cls in _REGISTRY.items():
        suffixes = list(cls.suffixes) if getattr(cls, "suffixes", ()) else [cls.suffix]
        priority = next((priority for priority, key in _DETECTION_ORDER if key == name), None)
        info[name] = {
            "content_type": getattr(cls, "content_type", "unknown"),
            "suffixes": ", ".join(suffixes),
            "priority": str(priority) if priority is not None else "",
        }
    return info


def iter_registered_parsers() -> Iterable[Type[BaseParser]]:
    for _, key in _DETECTION_ORDER:
        yield _REGISTRY[key]


def autodetect_parser(path: Path, raw_text: str) -> Optional[Type[BaseParser]]:
    for parser_cls in iter_registered_parsers():
        try:
            if parser_cls.supports(path, raw_text):
                return parser_cls
        except Exception:  # noqa: BLE001
            continue
    return None


def resolve_parser(path: Path, *, name: Optional[str] = None, raw_text: Optional[str] = None) -> Type[BaseParser]:
    if name:
        return get_parser(name)

    if raw_text is None:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")

    parser_cls = autodetect_parser(path, raw_text)
    if parser_cls is None:
        raise ValueError(f"未能为 {path.name} 自动匹配解析器，请使用 --parser 指定。")
    return parser_cls
