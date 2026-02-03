"""Fallback fetcher that pulls PDFs via Sci-Hub mirrors."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence, Tuple
from urllib.parse import urljoin

import requests

from benfinder.config import (
    FETCHER_DEFAULT_USER_AGENT,
    FETCHER_HTTP_TIMEOUT,
    LITERATURE_FETCHER_SLEEP_SECONDS,
    SCI_HUB_BASE_URLS,
)
from ..base import BaseFetcher
from ..registry import register_fetcher
from ..utils import sanitize_filename

LOGGER = logging.getLogger(__name__)

PDF_SRC_PATTERNS = (
    re.compile(r'<iframe[^>]+src=["\'](?P<src>[^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<embed[^>]+src=["\'](?P<src>[^"\']+)["\']', re.IGNORECASE),
    re.compile(r'id=["\']pdf["\'][^>]+src=["\'](?P<src>[^"\']+)["\']', re.IGNORECASE),
    re.compile(r'id=["\']pdf["\'][^>]+href=["\'](?P<src>[^"\']+)["\']', re.IGNORECASE),
)


class SciHubFetcher(BaseFetcher):
    name = "scihub"
    output_suffix = ".pdf"
    content_type = "pdf"

    def __init__(self, *, base_urls: Sequence[str] | None = None, sleep_seconds: float | None = None) -> None:
        super().__init__(sleep_seconds=sleep_seconds or LITERATURE_FETCHER_SLEEP_SECONDS)
        urls = list(base_urls or SCI_HUB_BASE_URLS or [])
        self.base_urls = [url.rstrip("/") for url in urls if url]
        if not self.base_urls:
            raise RuntimeError("未配置有效的 Sci-Hub 镜像地址。")

    def fetch(self, doi: str, target_dir: Path) -> Path:  # type: ignore[override]
        last_error: Exception | None = None
        for base_url in self.base_urls:
            try:
                return self._download_from_base(base_url, doi, target_dir)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                LOGGER.warning("Sci-Hub 镜像 %s 下载失败：%s", base_url, exc)
                continue
        raise RuntimeError(f"Sci-Hub 下载失败：doi={doi} | last_error={last_error}")

    def fetch_many(  # type: ignore[override]
        self,
        dois: Iterable[str],
        target_dir: Path,
    ) -> Iterator[Tuple[str, Optional[Path], Optional[Exception]]]:
        for doi in dois:
            try:
                path = self.fetch(doi, target_dir)
            except Exception as exc:  # noqa: BLE001
                yield doi, None, exc
            else:
                yield doi, path, None

    def _download_from_base(self, base_url: str, doi: str, target_dir: Path) -> Path:
        page_url = urljoin(f"{base_url}/", doi)
        headers = {
            "User-Agent": FETCHER_DEFAULT_USER_AGENT,
            "Referer": base_url,
            "Accept": "text/html,application/xhtml+xml",
        }
        response = requests.get(page_url, headers=headers, timeout=FETCHER_HTTP_TIMEOUT, allow_redirects=True)
        if response.status_code != 200:
            raise RuntimeError(f"Sci-Hub 页面访问失败：status={response.status_code} url={page_url}")

        pdf_src = self._extract_pdf_src(response.text)
        if not pdf_src:
            raise RuntimeError("Sci-Hub 页面未找到 PDF 下载链接。")

        pdf_url = urljoin(f"{base_url}/", pdf_src)
        pdf_headers = {
            "User-Agent": FETCHER_DEFAULT_USER_AGENT,
            "Referer": page_url,
            "Accept": "application/pdf",
        }
        pdf_response = requests.get(pdf_url, headers=pdf_headers, timeout=FETCHER_HTTP_TIMEOUT, stream=True)
        if pdf_response.status_code != 200:
            raise RuntimeError(f"Sci-Hub PDF 下载失败：status={pdf_response.status_code} url={pdf_url}")

        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / f"{sanitize_filename(doi)}{self.output_suffix}"
        with filepath.open("wb") as f:
            for chunk in pdf_response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        self._sleep()
        return filepath

    @staticmethod
    def _extract_pdf_src(html: str) -> str | None:
        for pattern in PDF_SRC_PATTERNS:
            match = pattern.search(html)
            if not match:
                continue
            src = match.group("src")
            if not src:
                continue
            src = src.strip()
            if not src:
                continue
            if ".pdf" not in src.lower():
                continue
            return src
        return None


register_fetcher(SciHubFetcher.name, SciHubFetcher)
