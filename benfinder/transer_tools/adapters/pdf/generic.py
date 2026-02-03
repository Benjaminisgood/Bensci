"""Generic parser for text-based PDF articles."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ...models import Metadata, Paragraph
from ...parser_base import BaseParser
from ...registry import register_parser
from ...text_cleaning import clean_text
from .common import (
    chunk_text,
    classify_paragraph,
    guess_authors,
    guess_date,
    guess_doi,
    guess_journal,
    guess_title,
)
from .ocr import OCRDocument, ocr as run_ocr

LOGGER = logging.getLogger(__name__)

try:
    from PyPDF2 import PdfReader  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    PdfReader = None


@dataclass(slots=True)
class PDFDocument:
    """Thin wrapper for PDF metadata and extracted page texts."""

    path: Path
    pages: List[str]
    raw_metadata: Dict[str, str]

    @property
    def full_text(self) -> str:
        return "\n".join(self.pages)


def _extract_pdf(path: Path) -> PDFDocument:
    if not PdfReader:
        LOGGER.warning("缺少 PyPDF2，尝试直接使用 OCR 管道解析 %s", path.name)
        ocr_doc = _try_ocr(path)
        if ocr_doc:
            return ocr_doc
        raise RuntimeError("无法解析 PDF：缺少 PyPDF2 依赖且 OCR 回退不可用。")

    reader = PdfReader(str(path))
    pages: List[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("读取 PDF 第 %d 页失败：%s", idx, exc)
            text = ""
        pages.append(text)

    info = reader.metadata or {}
    metadata: Dict[str, str] = {}
    for key, value in info.items():
        if not value:
            continue
        metadata[key.lstrip("/").lower()] = str(value)

    document = PDFDocument(path=path, pages=pages, raw_metadata=metadata)
    if _should_fallback_to_ocr(document.pages):
        LOGGER.info("检测到文本密度过低，%s 切换至 OCR 流程", path.name)
        ocr_doc = _try_ocr(path)
        if ocr_doc:
            return ocr_doc
    return document


def _should_fallback_to_ocr(pages: List[str]) -> bool:
    if not pages:
        return True
    lengths = [len((page or "").strip()) for page in pages]
    total_chars = sum(lengths)
    blank_pages = sum(1 for length in lengths if length < 20)
    if len(pages) == 1:
        return lengths[0] < 60
    if total_chars < 200:
        return True
    blank_ratio = blank_pages / len(pages)
    return len(pages) >= 3 and blank_ratio >= 0.65


def _try_ocr(path: Path) -> Optional[PDFDocument]:
    try:
        ocr_doc = run_ocr(path)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("OCR 回退失败 %s：%s", path.name, exc)
        return None
    return _from_ocr_document(ocr_doc)


def _from_ocr_document(document: OCRDocument) -> PDFDocument:
    pages = [page.text for page in document.pages]
    metadata = document.raw_metadata.copy()
    return PDFDocument(path=document.path, pages=pages, raw_metadata=metadata)


class GenericPDFParser(BaseParser):
    """Fallback parser that extracts plain text from arbitrary PDFs."""

    suffixes: Sequence[str] = (".pdf",)
    parser = "pdf"
    content_type = "pdf"
    para_tags: List[str] = []
    table_tags: List[str] = []
    figure_tags: List[str] = []

    @classmethod
    def supports(cls, path, raw_text: str) -> bool:  # type: ignore[override]
        return path.suffix.lower() == ".pdf"

    @classmethod
    def open_file(cls, filepath: str) -> PDFDocument:  # type: ignore[override]
        return _extract_pdf(Path(filepath))

    @classmethod
    def parsing(cls, document: PDFDocument) -> List[Paragraph]:  # type: ignore[override]
        paragraphs: List[Paragraph] = []
        for page_idx, page_text in enumerate(document.pages, start=1):
            for local_idx, raw_para in enumerate(chunk_text(page_text), start=1):
                cleaned = clean_text(raw_para)
                if not cleaned:
                    continue
                paragraphs.append(
                    Paragraph(
                        idx=f"{page_idx}.{local_idx}",
                        type=classify_paragraph(cleaned),
                        content=raw_para,
                        clean_text=cleaned,
                        intermediate_step={"page": page_idx},
                    )
                )
        return paragraphs

    @classmethod
    def get_metadata(cls, document: PDFDocument) -> Metadata:  # type: ignore[override]
        meta = document.raw_metadata
        first_page_text = document.pages[0] if document.pages else ""
        doi = guess_doi(document.full_text) or meta.get("doi")
        title = guess_title(first_page_text, meta) or (
            clean_text(meta.get("title", "")) if meta.get("title") else None
        )
        authors = guess_authors(meta)
        journal = guess_journal(meta)

        return Metadata(
            doi=doi or None,
            title=title or None,
            journal=journal or None,
            date=guess_date(document.full_text, meta),
            author_list=authors,
        )


register_parser("generic_pdf", GenericPDFParser, priority=200)

__all__ = ["GenericPDFParser"]
