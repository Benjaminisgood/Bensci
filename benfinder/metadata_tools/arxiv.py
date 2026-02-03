from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import List

from benfinder import config as cfg
import requests

from ..logging_utils import setup_file_logger
from .models import MetadataRecord

LOGGER = setup_file_logger("benfinder.metadata_tools.arxiv", getattr(cfg, "METADATA_LOG_PATH", None))

ARXIV_REQUEST_SLEEP_SECONDS = float(getattr(cfg, "ARXIV_REQUEST_SLEEP_SECONDS", 0.2))
ARXIV_MAX_RESULTS = int(getattr(cfg, "ARXIV_MAX_RESULTS", 200))
ARXIV_PAGE_SIZE = int(getattr(cfg, "ARXIV_PAGE_SIZE", 50))


def _ns(tag: str) -> str:
    # arXiv 使用 Atom 命名空间
    return f"{{http://www.w3.org/2005/Atom}}{tag}"


def _text(node: ET.Element, tag: str) -> str:
    element = node.find(_ns(tag))
    if element is not None and element.text:
        return element.text.strip()
    return ""


def search_arxiv(query: str, *, max_results: int = ARXIV_MAX_RESULTS, page_size: int = ARXIV_PAGE_SIZE) -> List[MetadataRecord]:
    records: List[MetadataRecord] = []
    base_url = "http://export.arxiv.org/api/query"

    start = 0
    while len(records) < max_results:
        search_query = query
        if "all:" not in query and ":" not in query.split()[0]:
            search_query = f"all:{query}"
        params = {
            "search_query": search_query,
            "start": start,
            "max_results": min(page_size, 200),
            "sortBy": "relevance",
        }
        resp = requests.get(base_url, params=params, timeout=60)
        if resp.status_code != 200:
            LOGGER.warning("arXiv API 调用失败：%s %s", resp.status_code, resp.text[:200])
            break

        root = ET.fromstring(resp.text)
        entries = root.findall(_ns("entry"))
        if not entries:
            break

        for entry in entries:
            title = _text(entry, "title")
            summary = _text(entry, "summary")
            published = _text(entry, "published")
            cover_date = published[:10] if published else ""
            id_url = _text(entry, "id")
            arxiv_id = ""
            if id_url:
                arxiv_id = id_url.rstrip("/").split("/")[-1]
            doi = f"arxiv:{arxiv_id}" if arxiv_id else ""

            authors = []
            for author in entry.findall(_ns("author")):
                name_el = author.find(_ns("name"))
                if name_el is not None and name_el.text:
                    authors.append(name_el.text.strip())
            authors_str = "; ".join(authors)

            categories = [
                cat.attrib.get("term", "").strip()
                for cat in entry.findall(_ns("category"))
                if isinstance(cat.attrib, dict)
            ]
            keywords = "; ".join(term for term in categories if term)

            records.append(
                MetadataRecord(
                    doi=doi,
                    title=title,
                    publication="arXiv",
                    cover_date=cover_date,
                    url=id_url,
                    abstract=summary,
                    authors=authors_str,
                    keywords=keywords,
                    language="en",
                    source="arxiv",
                )
            )
            if len(records) >= max_results:
                break

        if len(entries) < page_size:
            break
        start += page_size
        if ARXIV_REQUEST_SLEEP_SECONDS:
            time.sleep(ARXIV_REQUEST_SLEEP_SECONDS)

    LOGGER.info("arXiv 返回记录：%d", len(records))
    return records
