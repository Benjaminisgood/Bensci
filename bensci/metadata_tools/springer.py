from __future__ import annotations

import os
import time
from typing import Dict, List

from bensci import config as cfg
import requests

from ..logging_utils import setup_file_logger
from .models import MetadataRecord

LOGGER = setup_file_logger("bensci.metadata_tools.springer", getattr(cfg, "METADATA_LOG_PATH", None))

SPRINGER_META_API_BASE = getattr(cfg, "SPRINGER_META_API_BASE", "https://api.springernature.com/meta/v2/json")
SPRINGER_META_API_KEY_ENV = getattr(cfg, "SPRINGER_META_API_KEY_ENV", "SPRINGER_META_API_KEY")
SPRINGER_META_PAGE_SIZE = int(getattr(cfg, "SPRINGER_META_PAGE_SIZE", 20))
SPRINGER_META_MAX_RESULTS = int(getattr(cfg, "SPRINGER_META_MAX_RESULTS", 200))
SPRINGER_META_REQUEST_SLEEP_SECONDS = float(getattr(cfg, "SPRINGER_META_REQUEST_SLEEP_SECONDS", 0.2))

SPRINGER_META_API_KEY = os.getenv(SPRINGER_META_API_KEY_ENV) or getattr(cfg, "SPRINGER_META_API_KEY", None)
if not SPRINGER_META_API_KEY:
    LOGGER.warning("未配置 Springer Meta API key（环境变量 %s），将跳过 Springer 元数据源。", SPRINGER_META_API_KEY_ENV)


def _extract_url(record: Dict) -> str:
    entries = record.get("url")
    if isinstance(entries, list):
        html_link = next(
            (
                entry.get("value")
                for entry in entries
                if isinstance(entry, dict)
                and (entry.get("format") or "").lower() in {"html", "text/html", "html5"}
                and entry.get("value")
            ),
            None,
        )
        if html_link:
            return str(html_link)
        for entry in entries:
            if isinstance(entry, dict) and entry.get("value"):
                return str(entry["value"])
    elif isinstance(entries, str):
        return entries
    return ""


def _extract_authors(record: Dict) -> str:
    creators = record.get("creator")
    if isinstance(creators, list):
        names = [str(item).strip() for item in creators if str(item).strip()]
        return "; ".join(names)
    if isinstance(creators, str):
        return creators.strip()
    return ""


def _normalize_record(record: Dict) -> MetadataRecord:
    doi = str(record.get("doi", "")).strip()
    title = str(record.get("title", "")).strip()
    publication = str(record.get("publicationName", "") or record.get("publication", "")).strip()
    date = str(record.get("publicationDate", "") or record.get("onlineDate", "") or record.get("printPublicationDate", "")).strip()
    url = _extract_url(record)
    abstract = str(record.get("abstractText", "") or record.get("abstract", "")).strip()
    authors = _extract_authors(record)
    publisher = str(record.get("publisher", "") or record.get("publishingCompany", "")).strip()
    volume = str(record.get("volume", "")).strip()
    issue = str(record.get("number", "") or record.get("issue", "")).strip()
    starting_page = str(record.get("startingPage", "")).strip()
    ending_page = str(record.get("endingPage", "")).strip()
    pages = f"{starting_page}-{ending_page}" if starting_page and ending_page else (starting_page or ending_page)
    language = str(record.get("language", "")).strip()
    keywords_field = record.get("subject") or record.get("keyword") or ""
    if isinstance(keywords_field, list):
        keywords = "; ".join(str(item).strip() for item in keywords_field if str(item).strip())
    else:
        keywords = str(keywords_field or "").strip()
    issn_field = record.get("issn") or record.get("eIssn") or ""
    if isinstance(issn_field, list):
        issn = "; ".join(str(item).strip() for item in issn_field if str(item).strip())
    else:
        issn = str(issn_field or "").strip()

    return MetadataRecord(
        doi=doi,
        title=title,
        publication=publication,
        cover_date=date,
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
        source="springer",
    )


def search_springer(query: str, *, max_results: int = SPRINGER_META_MAX_RESULTS, page_size: int = SPRINGER_META_PAGE_SIZE) -> List[MetadataRecord]:
    if not SPRINGER_META_API_KEY:
        LOGGER.warning("Springer Meta API key 未配置，直接返回空结果。")
        return []

    page_size = max(1, min(page_size, 100))
    max_results = max(page_size, max_results)

    records: List[MetadataRecord] = []
    start = 1  # Springer Meta API 的 s 参数从 1 开始计数

    while len(records) < max_results:
        params = {
            "q": query,
            "api_key": SPRINGER_META_API_KEY,
            "p": page_size,
            "s": start,
        }
        response = requests.get(SPRINGER_META_API_BASE, params=params, timeout=60)
        if response.status_code != 200:
            LOGGER.warning("Springer Meta API 调用失败：%s %s", response.status_code, response.text[:200])
            break

        data = response.json()
        raw_records = data.get("records") or []
        if not raw_records:
            break

        for raw in raw_records:
            metadata = _normalize_record(raw if isinstance(raw, dict) else {})
            records.append(metadata)
            if len(records) >= max_results:
                break

        if len(raw_records) < page_size:
            break
        start += page_size
        if SPRINGER_META_REQUEST_SLEEP_SECONDS:
            time.sleep(SPRINGER_META_REQUEST_SLEEP_SECONDS)

    LOGGER.info("Springer Meta 返回记录：%d", len(records))
    return records
