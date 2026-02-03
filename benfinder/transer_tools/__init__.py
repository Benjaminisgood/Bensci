"""Document transformation toolkit with pluggable adapters."""

from __future__ import annotations

from .block_builder import build_blocks
from .models import StructuredDocument, DocumentBlock, Metadata, Paragraph
from .parser_base import BaseParser
from .registry import (
    available_parsers,
    describe_parsers,
    register_parser,
    resolve_parser,
)

# Ensure built-in adapters are registered on import
from .adapters import __all__ as _ADAPTERS  # noqa: F401

__all__ = [
    "BaseParser",
    "build_blocks",
    "StructuredDocument",
    "DocumentBlock",
    "Metadata",
    "Paragraph",
    "available_parsers",
    "describe_parsers",
    "register_parser",
    "resolve_parser",
]
