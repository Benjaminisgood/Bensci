"""Parser for ACS Publications XML articles."""

from __future__ import annotations

from typing import List, Optional

from bs4 import BeautifulSoup

from ...models import Metadata, Paragraph
from ...parser_base import BaseParser
from ...text_cleaning import clean_text
from ...registry import register_parser


class ACSParser(BaseParser):
    suffixes = (".xml",)
    parser = "lxml"
    content_type = "xml"
    para_tags: List[str] = ["p", "title"]
    table_tags: List[str] = ["table-wrap"]
    figure_tags: List[str] = ["fig"]

    @classmethod
    def supports(cls, path, raw_text: str) -> bool:  # type: ignore[override]
        if "acs-publications" in raw_text.lower() or "acs journals" in raw_text.lower():
            return True
        return super().supports(path, raw_text)

    @classmethod
    def open_file(cls, filepath: str):  # type: ignore[override]
        with open(filepath, "r", encoding="utf-8") as f:
            data = f.read()
        return BeautifulSoup(data, cls.parser)

    @classmethod
    def parsing(cls, file_bs) -> List[Paragraph]:  # type: ignore[override]
        elements: List[Paragraph] = []
        title_para: Optional[Paragraph] = None

        for element in file_bs(cls.all_tags()):
            classification = None
            include_properties = None
            is_heading = False
            if element.name in cls.table_tags:
                para_type = "table"
                clean_txt = ""
            elif element.name in cls.figure_tags:
                para_type = "figure"
                clean_txt = clean_text(element.text)
            elif element.name in cls.para_tags and cls._is_para(element):
                para_type = "text"
                for tag in element(["xref", "named-content", "fig", "table-wrap"]):
                    tag.extract()
                clean_txt = clean_text(element.text)
                if element.name == "title":
                    parent_names = [
                        p.name for p in element.parents if getattr(p, "name", None)
                    ]
                    if not any(
                        name in {"table-wrap", "table", "fig", "fig-group", "table-wrap-foot"}
                        for name in parent_names
                    ):
                        if "article-title" in parent_names or "title-group" in parent_names:
                            heading_level = 1
                        else:
                            depth = sum(1 for name in parent_names if name in {"sec", "section"})
                            heading_level = min(depth + 2, 6) if depth else 2
                        is_heading = True
                        classification = "heading"
                        include_properties = {
                            "heading_level": heading_level,
                            "tag": element.name,
                        }
            else:
                continue

            para = Paragraph(
                idx=len(elements) + 1,
                type=para_type,
                content=str(element),
                clean_text=clean_txt,
                classification=classification,
                include_properties=include_properties,
            )

            if title_para and para_type == "text" and not is_heading:
                title_para.merge(para, merge_idx=False)
                para = title_para
                title_para = None
            else:
                elements.append(para)

            if para_type != "text" or is_heading:
                title_para = None
            if para_type == "text" and len(clean_txt) < 200 and not title_para and not is_heading:
                title_para = para

        return elements

    @classmethod
    def _is_para(cls, element) -> bool:
        try:
            parent_name = element.parent.name
        except AttributeError:
            return False
        if parent_name in {"caption", "table-wrap-foot", "ack", "fn"}:
            return False
        if "content-type" in element.attrs:
            return False
        return True

    @classmethod
    def get_metadata(cls, file_bs) -> Metadata:  # type: ignore[override]
        doi_tag = file_bs.find("article-id", attrs={"pub-id-type": "doi"})
        doi = doi_tag.text.strip() if doi_tag and doi_tag.text else None

        title_tag = file_bs.find("title-group")
        title = clean_text(title_tag.text) if title_tag and title_tag.text else None

        journal_tag = file_bs.find("publisher-name")
        journal = clean_text(journal_tag.text) if journal_tag and journal_tag.text else None

        date = None
        date_tag = file_bs.find(["pub-date", "date"])
        if date_tag:
            year = date_tag.find("year")
            month = date_tag.find("month")
            if year and year.text:
                date = year.text.strip()
                if month and month.text:
                    date = f"{date}.{month.text.zfill(2)}"

        author_elems = file_bs.find_all("contrib")
        authors = []
        for contrib in author_elems:
            name_tag = contrib.find("name")
            if name_tag and name_tag.text:
                authors.append(name_tag.text.strip())

        return Metadata(
            doi=doi,
            title=title,
            journal=journal,
            date=date,
            author_list=authors or None,
        )


register_parser("acs", ACSParser, priority=20)
