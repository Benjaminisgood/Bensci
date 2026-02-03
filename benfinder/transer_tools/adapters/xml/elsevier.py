"""Parser for Elsevier / ScienceDirect XML articles."""

from __future__ import annotations

from typing import List, Optional

from bs4 import BeautifulSoup

from ...models import Metadata, Paragraph
from ...parser_base import BaseParser
from ...text_cleaning import clean_text
from ...registry import register_parser


class ElsevierParser(BaseParser):
    suffixes = (".xml",)
    parser = "lxml-xml"
    content_type = "xml"
    para_tags: List[str] = [
        "ce:para",
        "ce:section-title",
        "ce:simple-para",
    ]
    table_tags: List[str] = ["ce:table"]
    figure_tags: List[str] = ["ce:figure"]
    _para_tag_names = {tag.split(":")[-1].lower() for tag in para_tags}
    _table_tag_names = {tag.split(":")[-1].lower() for tag in table_tags}
    _figure_tag_names = {tag.split(":")[-1].lower() for tag in figure_tags}

    @classmethod
    def supports(cls, path, raw_text: str) -> bool:  # type: ignore[override]
        if "xmlns:ce" in raw_text or "xmlns:dc" in raw_text:
            return True
        return super().supports(path, raw_text)

    @classmethod
    def open_file(cls, filepath: str):  # type: ignore[override]
        with open(filepath, "r", encoding="utf-8") as f:
            data = f.read()
        return BeautifulSoup(data, cls.parser)

    @classmethod
    def parsing(cls, file_bs) -> List[Paragraph]:  # type: ignore[override]
        paragraphs: List[Paragraph] = []
        title_para: Optional[Paragraph] = None

        for element in file_bs(cls.all_tags()):
            tag_name = (element.name or "").lower()
            base_name = tag_name.split(":")[-1]
            classification = None
            include_properties = None
            is_heading = False

            if base_name in cls._table_tag_names:
                para_type = "table"
                clean_txt = ""
            elif base_name in cls._figure_tag_names:
                para_type = "figure"
                clean_txt = clean_text(element.text)
            elif base_name in cls._para_tag_names and cls._is_para(element):
                para_type = "text"
                for tag in element(["ce:cross-refs", "ce:cross-ref"]):
                    tag.extract()
                clean_txt = clean_text(element.text)
                if base_name == "section-title":
                    is_heading = True
                    depth = len(element.find_parents(["ce:section", "section"]))
                    include_properties = {
                        "heading_level": min(depth + 2, 6),
                        "tag": element.name,
                    }
                    classification = "heading"
            else:
                continue

            para = Paragraph(
                idx=len(paragraphs) + 1,
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
                paragraphs.append(para)

            if para_type != "text" or is_heading:
                title_para = None
            if para_type == "text" and len(clean_txt) < 200 and not title_para and not is_heading:
                title_para = para

        return paragraphs

    @classmethod
    def _is_para(cls, element) -> bool:
        try:
            parent_name = (element.parent.name or "").lower()
        except AttributeError:
            return False
        parent_base = parent_name.split(":")[-1]
        ignored = {
            "ce:acknowledgement",
            "ce:acknowledgment",
            "ce:legend",
            "ce:bibliography",
            "ce:keywords",
            "ce:caption",
        }
        ignored_names = {name.split(":")[-1] for name in ignored}
        return parent_base not in ignored_names

    @classmethod
    def get_metadata(cls, file_bs) -> Metadata:  # type: ignore[override]
        doi = cls._find_first_text(file_bs, "dc:identifier")
        doi = doi.replace("doi:", "") if doi else ""

        title = cls._find_first_text(file_bs, "dc:title")
        journal = cls._find_first_text(file_bs, "prism:publicationName") or cls._find_first_text(
            file_bs, "prism:publisher"
        )

        date_text = cls._find_first_text(file_bs, "prism:coverDate")
        if date_text and "-" in date_text:
            date = ".".join(date_text.split("-")[:-1])
        else:
            date = date_text

        author_list = [
            creator.text.strip()
            for creator in file_bs.find_all("dc:creator")
            if creator and creator.text
        ]

        return Metadata(
            doi=doi or None,
            title=title or None,
            journal=journal or None,
            date=date or None,
            author_list=author_list or None,
        )

    @classmethod
    def _find_first_text(cls, file_bs, tag_name: str) -> str:
        tag = file_bs.find(tag_name)
        return tag.text.strip() if tag and tag.text else ""


register_parser("elsevier", ElsevierParser, priority=10)
