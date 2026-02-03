from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import List

from bensci import config as cfg
import requests

from ..logging_utils import setup_file_logger
from .models import MetadataRecord

LOGGER = setup_file_logger("bensci.metadata_tools.pubmed", getattr(cfg, "METADATA_LOG_PATH", None))

PUBMED_MAX_RESULTS = int(getattr(cfg, "PUBMED_MAX_RESULTS", 200))
PUBMED_BATCH_SIZE = int(getattr(cfg, "PUBMED_BATCH_SIZE", 100))
PUBMED_REQUEST_SLEEP_SECONDS = float(getattr(cfg, "PUBMED_REQUEST_SLEEP_SECONDS", 0.34))  # NCBI 3/s


def _esearch(term: str, retmax: int) -> List[str]:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": term,
        "retmax": retmax,
        "retmode": "json",
    }
    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        LOGGER.warning("PubMed esearch 失败：%s %s", resp.status_code, resp.text[:200])
        return []
    data = resp.json()
    return (((data or {}).get("esearchresult") or {}).get("idlist") or [])


def _parse_pubmed_article(article_set: ET.Element) -> MetadataRecord:
    medline = article_set.find("./MedlineCitation")
    if medline is None:
        return MetadataRecord()

    article = medline.find("./Article")
    pmid = medline.findtext("./PMID", default="").strip()
    if article is None:
        return MetadataRecord(doi=f"pmid:{pmid}" if pmid else "")

    journal = article.findtext("./Journal/Title", default="").strip()
    title = article.findtext("./ArticleTitle", default="").strip()
    publisher = article.findtext("./Journal/PublisherName", default="").strip()
    volume = article.findtext("./Journal/JournalIssue/Volume", default="").strip()
    issue = article.findtext("./Journal/JournalIssue/Issue", default="").strip()
    pages = article.findtext("./Pagination/MedlinePgn", default="").strip()
    language = article.findtext("./Language", default="").strip()

    abstract = ""
    abstract_node = article.find("./Abstract")
    if abstract_node is not None:
        parts = []
        for text_node in abstract_node.findall("AbstractText"):
            part = (text_node.text or "").strip()
            if part:
                parts.append(part)
        abstract = "\n".join(parts).strip()

    cover_date = ""
    date_el = article.find("./ArticleDate")
    if date_el is not None:
        year = date_el.findtext("Year", default="").strip()
        month = date_el.findtext("Month", default="").strip()
        day = date_el.findtext("Day", default="").strip()
        cover_date = "-".join([piece for piece in (year, month, day) if piece])
    if not cover_date:
        pub_date = article.find("./Journal/JournalIssue/PubDate")
        if pub_date is not None:
            year = pub_date.findtext("Year", default="").strip()
            month = pub_date.findtext("Month", default="").strip()
            day = pub_date.findtext("Day", default="").strip()
            cover_date = "-".join([piece for piece in (year, month, day) if piece])

    doi = ""
    for eloc in article.findall("./ELocationID"):
        if eloc.get("EIdType", "").lower() == "doi" and eloc.text:
            doi = eloc.text.strip()
            break
    if not doi and pmid:
        doi = f"pmid:{pmid}"

    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

    authors = []
    for author in article.findall("./AuthorList/Author"):
        last = author.findtext("LastName", default="").strip()
        fore = author.findtext("ForeName", default="").strip()
        coll = author.findtext("CollectiveName", default="").strip()
        if last or fore:
            name = " ".join(piece for piece in (fore, last) if piece)
            authors.append(name)
        elif coll:
            authors.append(coll)
    authors_str = "; ".join(authors)

    keywords_terms = []
    for keyword in article.findall("./KeywordList/Keyword"):
        text = (keyword.text or "").strip()
        if text:
            keywords_terms.append(text)
    mesh_terms = []
    mesh_list = medline.find("./MeshHeadingList")
    if mesh_list is not None:
        for mesh in mesh_list.findall("./MeshHeading"):
            descriptor = mesh.findtext("./DescriptorName", default="").strip()
            qualifier = mesh.findtext("./QualifierName", default="").strip()
            if descriptor:
                if qualifier:
                    mesh_terms.append(f"{descriptor} ({qualifier})")
                else:
                    mesh_terms.append(descriptor)

    keywords = "; ".join(keywords_terms + mesh_terms)

    issn = article.findtext("./Journal/ISSN", default="").strip()

    return MetadataRecord(
        doi=doi,
        title=title,
        publication=journal,
        cover_date=cover_date,
        url=url,
        abstract=abstract,
        authors=authors_str,
        publisher=publisher,
        volume=volume,
        issue=issue,
        pages=pages,
        language=language,
        keywords=keywords,
        issn=issn,
        source="pubmed",
    )


def _efetch(pmids: List[str]) -> List[MetadataRecord]:
    if not pmids:
        return []

    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}
    resp = requests.get(url, params=params, timeout=60)
    if resp.status_code != 200:
        LOGGER.warning("PubMed efetch 失败：%s %s", resp.status_code, resp.text[:200])
        return []

    root = ET.fromstring(resp.text)
    records: List[MetadataRecord] = []
    for article_set in root.findall("./PubmedArticle"):
        records.append(_parse_pubmed_article(article_set))
    return records


def search_pubmed(term: str, *, max_results: int = PUBMED_MAX_RESULTS, batch_size: int = PUBMED_BATCH_SIZE) -> List[MetadataRecord]:
    ids = _esearch(term, retmax=max_results)
    records: List[MetadataRecord] = []
    for idx in range(0, len(ids), batch_size):
        chunk = ids[idx : idx + batch_size]
        records.extend(_efetch(chunk))
        if PUBMED_REQUEST_SLEEP_SECONDS:
            time.sleep(PUBMED_REQUEST_SLEEP_SECONDS)

    LOGGER.info("PubMed 返回记录：%d", len(records))
    return records
