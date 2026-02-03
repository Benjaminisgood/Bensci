"""Parser for Royal Society of Chemistry HTML articles."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

from ...models import Metadata, Paragraph
from ...parser_base import BaseParser
from ...text_cleaning import clean_text
from ...registry import register_parser


class RSCParser(BaseParser):
    suffixes = (".html", ".htm")
    parser = "lxml"
    content_type = "html"
    heading_tags: List[str] = ["h1", "h2", "h3", "h4", "h5", "h6"]
    para_tags: List[str] = ["p", "span"] + heading_tags
    table_tags: List[str] = ["table"]
    figure_tags: List[str] = ["img", "div"]

    @classmethod
    def supports(cls, path, raw_text: str) -> bool:  # type: ignore[override]
        if path.suffix.lower() not in cls.suffixes:
            return False
        lowered = raw_text.lower()
        return "rsc.org" in lowered or "royal society of chemistry" in lowered

    @classmethod
    def open_file(cls, filepath: str):  # type: ignore[override]
        with open(filepath, "r", encoding="utf-8") as f:
            data = f.read()
        return BeautifulSoup(data, cls.parser)

    @classmethod
    def parsing(cls, file_bs) -> List[Paragraph]:  # type: ignore[override]
        paragraphs: List[Paragraph] = []
        title_para = None

        for element in file_bs.find_all(cls.all_tags()):
            name = element.name or ""
            classification = None
            include_properties = None
            if name in cls.table_tags:
                success, table_element = cls._normalize_table(element)
                if not success or table_element is None:
                    continue
                para_type = "table"
                clean_txt = ""
                content_html = str(table_element)
            elif name in cls.figure_tags:
                if name == "div" and cls._has_class(element, "image_table"):
                    para_type = "figure"
                    clean_txt = clean_text(element.get_text())
                    content_html = str(element)
                else:
                    continue
            elif name in cls.heading_tags:
                text = clean_text(element.get_text())
                if not text:
                    continue
                para_type = "text"
                clean_txt = text
                content_html = str(element)
                classification = "heading"
                include_properties = {"heading_level": int(name[1]), "tag": name}
            elif name in cls.para_tags and cls._is_para(element):
                for tag in element.find_all("a"):
                    tag.extract()
                for tag in element.find_all("span", attrs={"class": "sup_ref"}):
                    tag.extract()
                text = clean_text(element.get_text())
                if not text:
                    continue
                para_type = "text"
                clean_txt = text
                content_html = str(element)
            else:
                continue

            para = Paragraph(
                idx=len(paragraphs) + 1,
                type=para_type,
                content=content_html,
                clean_text=clean_txt,
                classification=classification,
                include_properties=include_properties,
            )

            if title_para and para_type == "text" and classification != "heading":
                title_para.merge(para, merge_idx=False)
                para = title_para
                title_para = None
            else:
                paragraphs.append(para)

            if para_type != "text" or classification == "heading":
                title_para = None
            if para_type == "text" and len(clean_txt) < 200 and not title_para and classification != "heading":
                title_para = para

        return paragraphs

    @classmethod
    def _normalize_table(cls, element: Tag) -> Tuple[bool, Optional[Tag]]:
        if "class" not in element.attrs:
            return False, None

        caption = None
        up = element.find_previous("div")
        for _ in range(3):
            if not up:
                break
            if cls._has_class(up, "table_caption"):
                caption = up
                break
            up = up.find_previous("div")

        if caption is not None:
            element.insert(0, caption)

        return True, element

    @classmethod
    def _is_para(cls, element) -> bool:
        try:
            parent_name = element.parent.name
        except AttributeError:
            return False

        if parent_name in {"caption", "table", "fig", "figure"}:
            return False

        classes = element.get("class", [])
        for attr in ["sup_ref", "bold", "ref", "sub_ref", "italic", "small_caps"]:
            if attr in classes:
                return False

        element_id = " ".join(element.get("id", [])) if isinstance(element.get("id"), list) else element.get("id")
        if element_id and not re.search(r"(^|\s)fn", element_id):
            return False

        if cls._has_class(element, "btnContainer") or cls._has_class(element, "header_text"):
            return False

        return True

    @staticmethod
    def _has_class(element, name: str) -> bool:
        classes = element.get("class", [])
        if isinstance(classes, str):
            classes = [classes]
        return any(name in cls for cls in classes)

    @classmethod
    def get_metadata(cls, file_bs) -> Metadata:  # type: ignore[override]
        doi = title = journal = date = None
        authors: List[str] = []

        for meta in file_bs.find_all("meta"):
            name = meta.get("name")
            if not name:
                continue

            content = meta.get("content")
            if not content:
                continue

            lower = name.lower()
            if lower == "citation_doi" or lower == "dc.identifier":
                doi = content
            elif lower in {"citation_title", "dc.title"}:
                title = content
            elif lower == "citation_journal_title":
                journal = content
            elif lower in {"citation_publication_date", "dc.date"}:
                date = content
            elif lower == "citation_author" or lower == "dc.creator":
                authors.append(content)

        return Metadata(
            doi=doi,
            title=title,
            journal=journal,
            date=date,
            author_list=authors or None,
        )


register_parser("rsc_html", RSCParser, priority=70)
