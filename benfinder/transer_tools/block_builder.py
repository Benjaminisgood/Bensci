"""Utilities to convert parsed paragraphs into document blocks."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from bs4 import BeautifulSoup

from benfinder.config import TRANSER_EMBED_TABLE_FIGURE_BASE64
from .models import DocumentBlock, Paragraph
from .table_processor import normalize_table_structure, parse_table_html_block, table_to_plain_text
from .text_cleaning import clean_text


def build_blocks(
    paragraphs: Sequence[Paragraph],
    *,
    source_path: Optional[Path] = None,
    embed_base64: Optional[bool] = None,
) -> List[DocumentBlock]:
    blocks: List[DocumentBlock] = []
    counters = {"text": 1, "table": 1, "figure": 1}
    if embed_base64 is None:
        embed_base64 = TRANSER_EMBED_TABLE_FIGURE_BASE64
    source_dir = source_path.parent if source_path else None

    for para in paragraphs:
        metadata = _paragraph_metadata(para)
        if para.type == "text":
            text = _normalize_text_content(para)
            if not text:
                continue
            idx = f"T{counters['text']}"
            counters["text"] += 1
            blocks.append(DocumentBlock(idx=idx, type="text", content=text, metadata=metadata))
        elif para.type == "table":
            block = _build_table_block(para, counters["table"], embed_base64=embed_base64)
            if block:
                counters["table"] += 1
                if metadata:
                    block.metadata.update(metadata)
                blocks.append(block)
        elif para.type == "figure":
            block = _build_figure_block(
                para,
                counters["figure"],
                source_dir=source_dir,
                embed_base64=embed_base64,
            )
            if block:
                counters["figure"] += 1
                if metadata:
                    block.metadata.update(metadata)
                blocks.append(block)

    return blocks


def _normalize_text_content(para: Paragraph) -> str:
    candidates = [
        (para.clean_text or "").strip(),
        _clean_html_fragment(para.content),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return ""


def _clean_html_fragment(html: Optional[str]) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)
    return clean_text(text)


def _build_table_block(
    para: Paragraph,
    index: int,
    *,
    embed_base64: bool,
) -> Optional[DocumentBlock]:
    raw_html = para.content or ""
    table_payload = _parse_table_payload(raw_html, embed_base64=embed_base64)

    table_text = ""
    if table_payload:
        table_text = table_to_plain_text(table_payload)

    if not table_text:
        table_text = _normalize_text_content(para) or _clean_html_fragment(raw_html)

    if not table_text:
        return None
    return DocumentBlock(idx=f"TABLE{index}", type="table", content=table_text, table=table_payload)


def _parse_table_payload(raw_html: str, *, embed_base64: bool) -> Optional[Dict[str, Any]]:
    node = parse_table_html_block(raw_html)
    if not node:
        return None

    normalized = normalize_table_structure([(node, {})], embed_base64=embed_base64)
    if not normalized:
        return None

    table_dict = normalized[0]
    return table_dict


def _build_figure_block(
    para: Paragraph,
    index: int,
    *,
    source_dir: Optional[Path],
    embed_base64: bool,
) -> Optional[DocumentBlock]:
    raw_html = para.content or ""
    figure_payload = _parse_figure_payload(
        raw_html,
        source_dir=source_dir,
        embed_base64=embed_base64,
    )

    caption = figure_payload.get("caption") if figure_payload else None
    if not caption:
        caption = _normalize_text_content(para)
    if not caption:
        caption = "Figure"

    label = figure_payload.get("label") if figure_payload else None
    if label and not caption.startswith(label):
        caption = f"{label}: {caption}"

    return DocumentBlock(idx=f"FIG{index}", type="figure", content=caption, figure=figure_payload or None)


def _parse_figure_payload(
    raw_html: str,
    *,
    source_dir: Optional[Path],
    embed_base64: bool,
) -> Dict[str, Any]:
    if not raw_html.strip():
        return {}

    soup = BeautifulSoup(raw_html, "lxml-xml")
    figure = soup.find(["ce:figure", "figure", "fig"])
    if not figure:
        figure = soup.find(
            ["img", "graphic", "ce:graphic", "inline-graphic", "ce:inline-graphic"]
        )
    if not figure:
        return {}

    label_tag = figure.find(["ce:label", "label"])
    label = clean_text(label_tag.get_text(" ", strip=True)) if label_tag else ""

    caption_tag = figure.find(["ce:caption", "caption", "figcaption"])
    caption_html = caption_tag.decode() if caption_tag else ""
    caption_text = clean_text(caption_tag.get_text(" ", strip=True)) if caption_tag else ""

    link_tag = figure.find(["ce:link", "link"])
    reference: Dict[str, Any] = {}
    if link_tag:
        reference = {
            "href": link_tag.get("xlink:href") or link_tag.get("href"),
            "locator": link_tag.get("locator"),
            "role": link_tag.get("xlink:role"),
            "type": link_tag.get("xlink:type"),
        }
        reference = {k: v for k, v in reference.items() if v}

    figure_html = figure.decode()
    image_sources = _extract_image_sources(figure)
    images = _build_image_payloads(
        image_sources,
        source_dir=source_dir,
        embed_base64=embed_base64,
    )
    has_embedded_images = any("base64" in item for item in images)
    payload = {
        "figure_id": figure.get("id"),
        "label": label or None,
        "caption": caption_text or None,
        "caption_html": caption_html or None,
        "reference": reference or None,
        "llm_note": (
            "Image bytes已嵌入，可直接使用 images/base64。"
            if has_embedded_images
            else (
                "Image bytes未嵌入。请使用 reference 或 images/src 定位原始图像。"
                if reference or images
                else "Image bytes未嵌入。"
            )
        ),
    }
    if images:
        payload["images"] = images
    if embed_base64:
        payload["raw_html_base64"] = _encode_base64(figure_html)
    return {k: v for k, v in payload.items() if v}


def _encode_base64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _extract_image_sources(figure: Any) -> List[str]:
    sources: List[str] = []
    tag_names = ["img", "graphic", "ce:graphic", "inline-graphic", "ce:inline-graphic"]
    if getattr(figure, "name", None) in tag_names:
        src = figure.get("src") or figure.get("xlink:href") or figure.get("href")
        if src:
            sources.append(str(src))
    for tag in figure.find_all(tag_names):
        src = tag.get("src") or tag.get("xlink:href") or tag.get("href")
        if src:
            sources.append(str(src))
    # 去重并保持顺序
    return list(dict.fromkeys(sources))


def _build_image_payloads(
    sources: List[str],
    *,
    source_dir: Optional[Path],
    embed_base64: bool,
) -> List[Dict[str, Any]]:
    images: List[Dict[str, Any]] = []
    for src in sources:
        entry: Dict[str, Any] = {"src": src}
        if embed_base64:
            base64_data, mime_type = _resolve_image_base64(src, source_dir)
            if base64_data:
                entry["base64"] = base64_data
            if mime_type:
                entry["mime_type"] = mime_type
        images.append(entry)
    return images


def _resolve_image_base64(src: str, source_dir: Optional[Path]) -> tuple[Optional[str], Optional[str]]:
    if not src:
        return None, None

    cleaned = src.strip()
    if cleaned.startswith("data:"):
        if "base64," in cleaned:
            header, payload = cleaned.split("base64,", 1)
            mime = header[5:].split(";")[0] if header.startswith("data:") else None
            return payload.strip(), mime or None
        return None, None

    if cleaned.startswith(("http://", "https://")):
        return None, None

    if cleaned.startswith("file://"):
        cleaned = cleaned[7:]

    cleaned = cleaned.split("?", 1)[0].split("#", 1)[0]
    image_path = _resolve_local_image_path(cleaned, source_dir)
    if not image_path:
        return None, None

    data = image_path.read_bytes()
    mime_type, _ = mimetypes.guess_type(str(image_path))
    encoded = base64.b64encode(data).decode("ascii")
    return encoded, mime_type


def _resolve_local_image_path(src: str, source_dir: Optional[Path]) -> Optional[Path]:
    if not src:
        return None
    path = Path(src)
    candidates: List[Path] = []

    if path.is_absolute():
        candidates.append(path)
    elif source_dir:
        candidates.append(source_dir / path)
        candidates.append(source_dir / path.name)
        for folder in ("images", "image", "figures", "figure", "graphics", "graphic", "fig", "img"):
            candidates.append(source_dir / folder / path.name)

    if not path.suffix:
        extended: List[Path] = []
        for candidate in candidates:
            if candidate.suffix:
                continue
            for ext in (".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".bmp", ".svg"):
                extended.append(candidate.with_suffix(ext))
        candidates.extend(extended)

    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _paragraph_metadata(para: Paragraph) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {"source_idx": str(para.idx)}
    if para.classification:
        metadata["role"] = str(para.classification)
    if isinstance(para.include_properties, dict):
        if "heading_level" in para.include_properties:
            metadata["heading_level"] = para.include_properties.get("heading_level")
        if "tag" in para.include_properties:
            metadata["tag"] = para.include_properties.get("tag")
    step = para.intermediate_step or {}
    if isinstance(step, dict):
        page = step.get("page")
        if page is not None:
            metadata["page"] = page
    return metadata
