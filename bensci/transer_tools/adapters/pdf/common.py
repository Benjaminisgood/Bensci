"""Shared utilities for PDF-based adapters."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from ...text_cleaning import clean_text

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s>]+", re.IGNORECASE)
DATE_RE = re.compile(r"(20\d{2}|19\d{2})([-/\.](0?[1-9]|1[0-2])([-/.](0?[1-9]|[12]\d|3[01]))?)?")

_TABLE_PREFIXES = ("table", "tab.", "tab ")
_FIGURE_PREFIXES = ("figure", "fig.", "fig ", "scheme", "schem.", "graphical abstract")


def chunk_text(text: str) -> Iterable[str]:
    """Split free-flow PDF text into paragraphs by empty lines."""

    buffer: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if buffer:
                yield " ".join(buffer)
                buffer.clear()
            continue
        buffer.append(stripped)
    if buffer:
        yield " ".join(buffer)


def classify_paragraph(text: str) -> str:
    """Heuristically classify a paragraph into text/table/figure."""

    lowered = text.lower().lstrip()
    if any(lowered.startswith(prefix) for prefix in _TABLE_PREFIXES):
        return "table"
    if any(lowered.startswith(prefix) for prefix in _FIGURE_PREFIXES):
        return "figure"
    return "text"


def guess_title(first_page_text: str, metadata: Dict[str, str]) -> Optional[str]:
    candidate = metadata.get("title")
    if candidate:
        cleaned = clean_text(candidate)
        if cleaned:
            return cleaned

    for paragraph in chunk_text(first_page_text):
        if len(paragraph) >= 8 and not paragraph.lower().startswith("wileyonlinelibrary.com"):
            return clean_text(paragraph)
    return None


def guess_authors(metadata: Dict[str, str]) -> Optional[List[str]]:
    author_field = metadata.get("author")
    if not author_field:
        return None

    parts = re.split(r"[;,]| and ", author_field)
    authors = [clean_text(part) for part in parts if clean_text(part)]
    return authors or None


def guess_journal(metadata: Dict[str, str]) -> Optional[str]:
    journal = metadata.get("subject") or metadata.get("keywords")
    return clean_text(journal) if journal else None


def guess_date(full_text: str, metadata: Dict[str, str]) -> Optional[str]:
    raw_date = metadata.get("moddate") or metadata.get("creationdate") or metadata.get("date")
    if raw_date:
        parsed = parse_pdf_date(raw_date)
        if parsed:
            return parsed

    match = DATE_RE.search(full_text)
    if match:
        year = match.group(1)
        rest = match.group(2) or ""
        digits = [d for d in re.split(r"[-/\.]", rest) if d]
        if digits:
            month = digits[0].zfill(2)
            day = digits[1].zfill(2) if len(digits) > 1 else "01"
            return f"{year}-{month}-{day}"
        return year
    return None


def parse_pdf_date(value: str) -> Optional[str]:
    # PDF metadata dates often look like: D:20210325120000Z
    cleaned = value.strip().lstrip("D:").rstrip("Z")
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d", "%Y%m"):
        try:
            dt = datetime.strptime(cleaned[: len(fmt)], fmt)
            if fmt == "%Y%m":
                return dt.strftime("%Y-%m")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    if cleaned.isdigit() and len(cleaned) >= 4:
        return cleaned[:4]
    return None


def guess_doi(text: str) -> Optional[str]:
    match = DOI_RE.search(text)
    if match:
        return match.group(0).rstrip(".")
    return None


__all__ = [
    "chunk_text",
    "classify_paragraph",
    "guess_title",
    "guess_authors",
    "guess_journal",
    "guess_date",
    "parse_pdf_date",
    "guess_doi",
    "DATE_RE",
    "DOI_RE",
]
