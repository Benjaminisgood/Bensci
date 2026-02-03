from __future__ import annotations

import time
from typing import Dict, List

from bensci import config as cfg
import requests

from ..logging_utils import setup_file_logger
from .models import MetadataRecord

LOGGER = setup_file_logger("bensci.metadata_tools.openalex", getattr(cfg, "METADATA_LOG_PATH", None))

OPENALEX_PER_PAGE = int(getattr(cfg, "OPENALEX_PER_PAGE", 25))
OPENALEX_MAX_RESULTS = int(getattr(cfg, "OPENALEX_MAX_RESULTS", 200))
OPENALEX_REQUEST_SLEEP_SECONDS = float(getattr(cfg, "OPENALEX_REQUEST_SLEEP_SECONDS", 0.2))


def _reconstruct_openalex_abstract(inv_idx: Dict[str, List[int]] | None) -> str:
    if not inv_idx:
        return ""

    max_length = max((max(pos_list) for pos_list in inv_idx.values()), default=-1) + 1
    tokens = [""] * max_length
    for word, positions in inv_idx.items():
        for pos in positions:
            if 0 <= pos < max_length:
                tokens[pos] = word
    return " ".join(token for token in tokens if token).strip()


def _join_authors(authorships: List[dict]) -> str:
    names = []
    for authorship in authorships or []:
        name = ((authorship.get("author") or {}).get("display_name") or "").strip()
        if name:
            names.append(name)
    return "; ".join(names)


def search_openalex(query: str, *, max_results: int = OPENALEX_MAX_RESULTS, per_page: int = OPENALEX_PER_PAGE) -> List[MetadataRecord]:
    url = "https://api.openalex.org/works"
    per_page = max(1, min(per_page, 200))
    records: List[MetadataRecord] = []

    page = 1
    while len(records) < max_results:
        params = {
            "search": query,
            "per_page": per_page,
            "page": page,
            "filter": "is_paratext:false",
        }
        try:
            resp = requests.get(url, params=params, timeout=60)
        except requests.RequestException as exc:  # pragma: no cover
            LOGGER.warning("OpenAlex 请求异常：%s", exc)
            break

        if resp.status_code != 200:
            LOGGER.warning("OpenAlex API 调用失败：%s %s", resp.status_code, resp.text[:200])
            break

        data = resp.json()
        results = data.get("results") or []
        if not results:
            break

        for item in results:
            doi = (item.get("doi") or "").replace("https://doi.org/", "").strip()
            title = (item.get("title") or "").strip()
            publication = ((item.get("host_venue") or {}).get("display_name") or "").strip()
            cover_date = (
                (item.get("publication_date") or "") or str(item.get("publication_year") or "")
            ).strip()
            host_venue = item.get("host_venue") or {}
            publisher = (host_venue.get("publisher") or "").strip()
            issn_list = host_venue.get("issn") or []
            if isinstance(issn_list, list):
                issn = "; ".join(str(v).strip() for v in issn_list if str(v).strip())
            else:
                issn = str(issn_list or "").strip()

            biblio = item.get("biblio") or {}
            volume = str(biblio.get("volume") or "").strip()
            issue = str(biblio.get("issue") or "").strip()
            pages = ""
            first_page = str(biblio.get("first_page") or "").strip()
            last_page = str(biblio.get("last_page") or "").strip()
            if first_page and last_page:
                pages = f"{first_page}-{last_page}"
            else:
                pages = first_page or last_page

            primary_loc = item.get("primary_location") or {}
            landing_page = primary_loc.get("landing_page_url")
            source = primary_loc.get("source") or {}
            url_item = landing_page or source.get("host_page_url") or item.get("id") or ""
            if not isinstance(url_item, str):
                url_item = ""

            abstract = _reconstruct_openalex_abstract(item.get("abstract_inverted_index"))
            authors = _join_authors(item.get("authorships") or [])
            language = (item.get("language") or "").strip()
            concepts = item.get("concepts") or []
            keywords = "; ".join(
                concept.get("display_name", "").strip()
                for concept in concepts
                if isinstance(concept, dict) and concept.get("display_name")
            )

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
                    source="openalex",
                )
            )
            if len(records) >= max_results:
                break

        if len(results) < per_page:
            break
        page += 1
        if OPENALEX_REQUEST_SLEEP_SECONDS:
            time.sleep(OPENALEX_REQUEST_SLEEP_SECONDS)

    LOGGER.info("OpenAlex 返回记录：%d", len(records))
    return records
