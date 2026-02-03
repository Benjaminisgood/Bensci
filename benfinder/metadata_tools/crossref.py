from __future__ import annotations

import re
import time
from typing import List

from benfinder import config as cfg
import requests

from ..logging_utils import setup_file_logger
from .models import MetadataRecord

LOGGER = setup_file_logger("benfinder.metadata_tools.crossref", getattr(cfg, "METADATA_LOG_PATH", None))

CROSSREF_REQUEST_SLEEP_SECONDS = float(getattr(cfg, "CROSSREF_REQUEST_SLEEP_SECONDS", 0.2))
CROSSREF_ROWS = int(getattr(cfg, "CROSSREF_ROWS", 50))
CROSSREF_MAX_RESULTS = int(getattr(cfg, "CROSSREF_MAX_RESULTS", 200))


def _pick_date(item: dict) -> str:
    # 尝试 published-print / published-online / created / issued
    for key in ("published-print", "published-online", "created", "issued"):
        date_obj = item.get(key) or {}
        parts = date_obj.get("date-parts") or []
        if parts and isinstance(parts, list) and parts[0]:
            return "-".join(str(x) for x in parts[0])
    return ""


def _join_authors(item: dict) -> str:
    authors = item.get("author") or []
    names = []
    for author in authors:
        given = (author.get("given") or "").strip()
        family = (author.get("family") or "").strip()
        name = " ".join([part for part in (given, family) if part])
        if not name:
            name = (author.get("name") or "").strip()
        if name:
            names.append(name)
    return "; ".join(names)


def _clean_abstract(abstract: str) -> str:
    if not abstract:
        return ""
    if abstract.startswith("<"):
        return re.sub(r"<[^>]+>", "", abstract).strip()
    return abstract.strip()


def search_crossref(query: str, *, max_results: int = CROSSREF_MAX_RESULTS, rows: int = CROSSREF_ROWS) -> List[MetadataRecord]:
    url = "https://api.crossref.org/works"
    params = {"query": query, "rows": min(rows, 100)}
    records: List[MetadataRecord] = []

    try:
        resp = requests.get(url, params=params, timeout=60)
    except requests.RequestException as exc:  # pragma: no cover - 网络异常
        LOGGER.warning("Crossref 请求异常：%s", exc)
        return records

    if resp.status_code != 200:
        LOGGER.warning("Crossref API 调用失败：%s %s", resp.status_code, resp.text[:200])
        return records

    data = resp.json()
    items = ((data or {}).get("message") or {}).get("items") or []
    for item in items:
        doi = (item.get("DOI") or "").strip()
        title_list = item.get("title") or []
        title = (title_list[0] if title_list else "").strip()
        publication_list = item.get("container-title") or []
        publication = (publication_list[0] if publication_list else "").strip()
        cover_date = _pick_date(item)
        url_item = (item.get("URL") or "").strip()
        abstract = _clean_abstract(item.get("abstract") or "")
        authors = _join_authors(item)
        publisher = (item.get("publisher") or "").strip()
        volume = (item.get("volume") or "").strip()
        issue = (item.get("issue") or "").strip()
        pages = (item.get("page") or "").strip()
        language = (item.get("language") or "").strip()
        keywords_list = item.get("subject") or []
        if isinstance(keywords_list, list):
            keywords = "; ".join(str(k).strip() for k in keywords_list if str(k).strip())
        else:
            keywords = str(keywords_list or "").strip()
        issn_list = item.get("ISSN") or []
        if isinstance(issn_list, list):
            issn = "; ".join(str(i).strip() for i in issn_list if str(i).strip())
        else:
            issn = str(issn_list or "").strip()

        records.append(
            MetadataRecord(
                doi=doi,
                title=title,
                publication=publication,
                cover_date=cover_date,
                url=url_item,
                abstract=abstract,
                authors=authors,
                publisher=publisher,
                volume=volume,
                issue=issue,
                pages=pages,
                language=language,
                keywords=keywords,
                issn=issn,
                source="crossref",
            )
        )

        if len(records) >= max_results:
            break

    if CROSSREF_REQUEST_SLEEP_SECONDS:
        time.sleep(CROSSREF_REQUEST_SLEEP_SECONDS)

    LOGGER.info("Crossref 返回记录：%d", len(records))
    return records
