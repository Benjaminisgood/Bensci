from __future__ import annotations

import os
import time
from typing import Dict, List
from urllib.parse import quote

from benfinder import config as cfg
import requests
from dotenv import load_dotenv

from ..logging_utils import setup_file_logger
from .models import MetadataRecord

LOGGER = setup_file_logger("benfinder.metadata_tools.elsevier", getattr(cfg, "METADATA_LOG_PATH", None))

# 加载 .env（与旧逻辑保持一致）
ENV_FILE = getattr(cfg, "ENV_FILE", ".env")
if ENV_FILE:
    load_dotenv(ENV_FILE)

ELSEVIER_API_KEY = os.getenv("ELSEVIER_API_KEY")
if not ELSEVIER_API_KEY:
    hint = (
        f"需要在环境变量或 {ENV_FILE} 中设置 ELSEVIER_API_KEY 才能调用接口。\n"
        "示例：ELSEVIER_API_KEY=你的key"
    )
    # 仅记录警告，不在模块 import 时抛出；由调用处按需决定是否启用 Elsevier 源。
    LOGGER.warning(hint)

SCOPUS_PAGE_SIZE = int(getattr(cfg, "SCOPUS_PAGE_SIZE", 25))
SCOPUS_MAX_RESULTS = int(getattr(cfg, "SCOPUS_MAX_RESULTS", 200))
SCOPUS_REQUEST_SLEEP_SECONDS = float(getattr(cfg, "SCOPUS_REQUEST_SLEEP_SECONDS", 0.5))
ABSTRACT_SLEEP_SECONDS = float(getattr(cfg, "ABSTRACT_SLEEP_SECONDS", 0.2))
SCOPUS_ALLOWED_PUBLISHER_KEYWORDS = [
    kw.lower()
    for kw in getattr(cfg, "SCOPUS_ALLOWED_PUBLISHER_KEYWORDS", ["elsevier", "sciencedirect"])
]


def _scopus_search(query: str, *, start: int = 0, count: int = SCOPUS_PAGE_SIZE) -> Dict:
    url = "https://api.elsevier.com/content/search/scopus"
    headers = {"X-ELS-APIKey": ELSEVIER_API_KEY, "Accept": "application/json"}
    params = {
        "query": query,
        "count": min(count, SCOPUS_PAGE_SIZE),
        "start": start,
        "view": "COMPLETE",
    }
    resp = requests.get(url, headers=headers, params=params, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Scopus Search API 调用失败：status={resp.status_code} | body={resp.text}")
    return resp.json()


def _fetch_abstract_via_abstract_api(doi: str) -> str:
    url = f"https://api.elsevier.com/content/abstract/doi/{quote(doi, safe='')}"
    headers = {"X-ELS-APIKey": ELSEVIER_API_KEY, "Accept": "application/json"}
    params = {"view": "FULL"}
    resp = requests.get(url, headers=headers, params=params, timeout=60)
    if resp.status_code != 200:
        LOGGER.debug("Abstract API 未返回摘要：%s | status=%s", doi, resp.status_code)
        return ""
    try:
        abstract = (
            resp.json()["abstracts-retrieval-response"]["coredata"]
            .get("dc:description", "")
            .strip()
        )
    except Exception as exc:  # pragma: no cover - 容错日志
        LOGGER.debug("解析摘要响应失败：%s | %s", doi, exc)
        abstract = ""
    if abstract and ABSTRACT_SLEEP_SECONDS:
        time.sleep(ABSTRACT_SLEEP_SECONDS)
    return abstract


def _normalize_entry(entry: Dict) -> MetadataRecord:
    doi = entry.get("prism:doi") or ""
    title = (entry.get("dc:title") or "").strip()
    publication = (entry.get("prism:publicationName") or "").strip()
    cover_date = (entry.get("prism:coverDate") or "").strip()
    url = (entry.get("prism:url") or "").strip()
    abstract = (entry.get("dc:description") or "").strip()
    publisher = (entry.get("dc:publisher") or "").strip()
    volume = (entry.get("prism:volume") or "").strip()
    issue = (
        entry.get("prism:issueIdentifier")
        or entry.get("prism:issueNumber")
        or entry.get("prism:issueid")
        or ""
    )
    issue = issue.strip() if isinstance(issue, str) else str(issue).strip()

    starting_page = (entry.get("prism:startingPage") or "").strip()
    ending_page = (entry.get("prism:endingPage") or "").strip()
    page_range = entry.get("prism:pageRange")
    if page_range:
        pages = str(page_range).strip()
    elif starting_page and ending_page:
        pages = f"{starting_page}-{ending_page}"
    else:
        pages = starting_page or ending_page

    language = (entry.get("prism:language") or entry.get("dc:language") or "").strip()

    keywords_data = entry.get("authkeywords") or entry.get("dc:subject") or ""
    if isinstance(keywords_data, dict):
        keyword_list = keywords_data.get("author-keyword") or keywords_data.get("subject")
        if isinstance(keyword_list, list):
            keywords = "; ".join(str(item).strip() for item in keyword_list if str(item).strip())
        else:
            keywords = str(keyword_list or "").strip()
    elif isinstance(keywords_data, list):
        keywords = "; ".join(str(item).strip() for item in keywords_data if str(item).strip())
    else:
        keywords = str(keywords_data or "").strip()

    issn = (entry.get("prism:issn") or entry.get("prism:eIssn") or "").strip()

    authors = entry.get("dc:creator")
    if isinstance(authors, list):
        authors = "; ".join(str(a).strip() for a in authors if str(a).strip())
    elif authors is None:
        authors = ""
    else:
        authors = str(authors).strip()

    if not abstract and doi and ELSEVIER_API_KEY:
        LOGGER.debug("记录缺少摘要，尝试补足：%s", doi)
        abstract = _fetch_abstract_via_abstract_api(doi)

    return MetadataRecord(
        doi=doi,
        title=title,
        publication=publication,
        cover_date=cover_date,
        url=url,
        abstract=abstract,
        authors=authors,
        publisher=publisher,
        volume=volume,
        issue=issue,
        pages=pages,
        language=language,
        keywords=keywords,
        issn=issn,
        source="elsevier",
    )


def _is_allowed_entry(entry: Dict) -> bool:
    candidates: List[str] = []
    for key in ("prism:publisher", "dc:publisher", "prism:publicationName"):
        value = entry.get(key)
        if value:
            candidates.append(str(value))

    for link_node in entry.get("link", []):
        if isinstance(link_node, dict):
            href = link_node.get("@href")
            if href:
                candidates.append(str(href))

    prism_url = entry.get("prism:url")
    if prism_url:
        candidates.append(str(prism_url))

    for text in candidates:
        lowered = text.lower()
        if any(keyword in lowered for keyword in SCOPUS_ALLOWED_PUBLISHER_KEYWORDS):
            return True
    return False


def search_elsevier(
    query: str,
    *,
    max_results: int = SCOPUS_MAX_RESULTS,
    page_size: int = SCOPUS_PAGE_SIZE,
) -> List[MetadataRecord]:
    """
    使用 Scopus Search API，返回 Elsevier/ScienceDirect 体系的记录。
    """
    if not ELSEVIER_API_KEY:
        LOGGER.warning("未配置 ELSEVIER_API_KEY，跳过 Elsevier 源。")
        return []

    page_size = max(1, min(page_size, SCOPUS_PAGE_SIZE))
    max_results = max(page_size, max_results)

    LOGGER.info("调用 Scopus：%s | page_size=%d | max_results=%d", query, page_size, max_results)

    start = 0
    records: List[MetadataRecord] = []
    seen_doi: set[str] = set()

    while start < max_results:
        result = _scopus_search(query, start=start, count=page_size)
        search_results = result.get("search-results", {}) if isinstance(result, dict) else {}
        entries = search_results.get("entry", [])
        if not entries:
            break

        for entry in entries:
            if not _is_allowed_entry(entry):
                continue
            record = _normalize_entry(entry)
            key = record.doi.strip().lower() if record.doi else ""
            if key and key in seen_doi:
                continue
            records.append(record)
            if key:
                seen_doi.add(key)
            if len(records) >= max_results:
                break

        if len(records) >= max_results:
            break

        start += page_size
        if len(entries) < page_size:
            break
        if SCOPUS_REQUEST_SLEEP_SECONDS:
            time.sleep(SCOPUS_REQUEST_SLEEP_SECONDS)

    LOGGER.info("Elsevier 返回记录：%d", len(records))
    return records
