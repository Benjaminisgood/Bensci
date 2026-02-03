from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MetadataRecord:
    """
    统一的元数据结构，不同 Provider 的记录在此汇合。

    字段允许为空字符串，便于后续处理时进行合并或补全。
    """

    doi: str = ""
    title: str = ""
    publication: str = ""
    cover_date: str = ""
    url: str = ""
    abstract: str = ""
    authors: str = ""
    source: str = ""
    publisher: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    language: str = ""
    keywords: str = ""
    issn: str = ""

    def to_row(self) -> list[str]:
        """序列化为 CSV 行。"""
        return [
            self.doi or "",
            self.title or "",
            self.publication or "",
            self.cover_date or "",
            self.url or "",
            self.abstract or "",
            self.authors or "",
            self.source or "",
            self.publisher or "",
            self.volume or "",
            self.issue or "",
            self.pages or "",
            self.language or "",
            self.keywords or "",
            self.issn or "",
        ]

    def to_dict(self) -> dict[str, str]:
        return {
            "doi": self.doi or "",
            "title": self.title or "",
            "publication": self.publication or "",
            "cover_date": self.cover_date or "",
            "url": self.url or "",
            "abstract": self.abstract or "",
            "authors": self.authors or "",
            "source": self.source or "",
            "publisher": self.publisher or "",
            "volume": self.volume or "",
            "issue": self.issue or "",
            "pages": self.pages or "",
            "language": self.language or "",
            "keywords": self.keywords or "",
            "issn": self.issn or "",
        }

    def dedup_key(self) -> str:
        """
        用于跨源去重的键：
        - 首选 DOI（小写）
        - 否则用规范化标题 + 年份 作为去重键
        """
        if self.doi:
            return f"doi::{self.doi.strip().lower()}"
        norm_title = (self.title or "").strip().lower()
        year = (self.cover_date or "").strip()[:4]
        return f"title::{norm_title}::year::{year}"


def merge_records(primary: MetadataRecord, other: MetadataRecord) -> MetadataRecord:
    """
    合并两个同一论文的记录，尽量保留更有价值的信息：
    - doi：优先保留非空 DOI
    - abstract：保留更长的摘要
    - 其余字段：尽量保留 primary 中的内容，缺失时使用 other 填补
    """

    def _prefer(base: str, fallback: str) -> str:
        return base or fallback

    doi = primary.doi or other.doi
    title = _prefer(primary.title, other.title)
    publication = _prefer(primary.publication, other.publication)
    cover_date = _prefer(primary.cover_date, other.cover_date)
    url = _prefer(primary.url, other.url)

    abs_primary = primary.abstract or ""
    abs_other = other.abstract or ""
    abstract = abs_primary if len(abs_primary) >= len(abs_other) else abs_other

    authors = _prefer(primary.authors, other.authors)
    source = _prefer(primary.source, other.source)
    publisher = _prefer(primary.publisher, other.publisher)
    volume = _prefer(primary.volume, other.volume)
    issue = _prefer(primary.issue, other.issue)
    pages = _prefer(primary.pages, other.pages)
    language = _prefer(primary.language, other.language)
    keywords = _prefer(primary.keywords, other.keywords)
    issn = _prefer(primary.issn, other.issn)

    return MetadataRecord(
        doi=doi,
        title=title,
        publication=publication,
        cover_date=cover_date,
        url=url,
        abstract=abstract,
        authors=authors,
        source=source,
        publisher=publisher,
        volume=volume,
        issue=issue,
        pages=pages,
        language=language,
        keywords=keywords,
        issn=issn,
    )
