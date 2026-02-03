"""Parser for Wiley Online Library HTML articles."""

from __future__ import annotations

import logging
from typing import Dict, List

from bs4 import BeautifulSoup

from ...models import Metadata, Paragraph
from ...parser_base import BaseParser
from ...text_cleaning import clean_text
from ...registry import register_parser

LOGGER = logging.getLogger(__name__)


class WileyHTMLParser(BaseParser):
    suffixes = (".html", ".htm")
    parser = "lxml"
    content_type = "html"
    heading_tags: List[str] = ["h1", "h2", "h3", "h4", "h5", "h6"]
    para_tags: List[str] = ["p"] + heading_tags
    table_tags: List[str] = ["table"]
    figure_tags: List[str] = ["figure", "img"]

    @classmethod
    def supports(cls, path, raw_text: str) -> bool:  # type: ignore[override]
        if path.suffix.lower() not in cls.suffixes:
            return False
        lowered = raw_text.lower()
        return "wiley" in lowered or "onlinelibrary.wiley" in lowered

    @classmethod
    def open_file(cls, filepath: str):  # type: ignore[override]
        with open(filepath, "r", encoding="utf-8") as f:
            data = f.read()
        return BeautifulSoup(data, cls.parser)

    @classmethod
    def parsing(cls, file_bs) -> List[Paragraph]:  # type: ignore[override]
        paragraphs: List[Paragraph] = []
        for idx, element in enumerate(file_bs.find_all(cls.para_tags + cls.table_tags + cls.figure_tags), start=1):
            name = element.name or ""
            classification = None
            include_properties = None
            if name in cls.table_tags:
                para_type = "table"
                clean_txt = ""
            elif name in cls.figure_tags:
                para_type = "figure"
                clean_txt = clean_text(element.get_text())
            elif name in cls.heading_tags:
                text = clean_text(element.get_text())
                if not text:
                    continue
                para_type = "text"
                clean_txt = text
                classification = "heading"
                include_properties = {"heading_level": int(name[1]), "tag": name}
            elif name in cls.para_tags:
                text = clean_text(element.get_text())
                if not text:
                    continue
                para_type = "text"
                clean_txt = text
            else:
                continue

            paragraphs.append(
                Paragraph(
                    idx=idx,
                    type=para_type,
                    content=str(element),
                    clean_text=clean_txt,
                    classification=classification,
                    include_properties=include_properties,
                )
            )

        if not any(para.type == "text" and (para.clean_text or "").strip() for para in paragraphs):
            LOGGER.warning(
                "Wiley HTML 解析器未能提取正文文本，原始文件可能需要重新抓取。"
            )

        return paragraphs

    @classmethod
    def get_metadata(cls, file_bs) -> Metadata:  # type: ignore[override]
        meta_map: Dict[str, str] = {}
        for meta in file_bs.find_all("meta"):
            name = meta.get("name") or meta.get("property")
            content = meta.get("content")
            if name and content:
                meta_map[name.lower()] = content.strip()

        doi = meta_map.get("citation_doi") or meta_map.get("dc.identifier")
        title = meta_map.get("citation_title") or (file_bs.title.string.strip() if file_bs.title else None)
        journal = meta_map.get("citation_journal_title") or meta_map.get("dc.source")
        date = meta_map.get("citation_publication_date") or meta_map.get("dc.date")

        authors = [
            value
            for key, value in meta_map.items()
            if key.startswith("citation_author") and value
        ]

        return Metadata(
            doi=doi,
            title=title,
            journal=journal,
            date=date,
            author_list=authors or None,
        )


register_parser("wiley_html", WileyHTMLParser, priority=60)
