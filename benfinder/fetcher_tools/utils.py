"""Common helper functions for fetchers."""

from __future__ import annotations


def sanitize_filename(text: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in text)
    return safe.strip("_") or "article"
