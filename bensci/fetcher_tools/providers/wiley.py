"""Fetch HTML full text from Wiley Online Library."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

import requests

from bensci.config import (
    FETCHER_DEFAULT_USER_AGENT,
    FETCHER_HTTP_TIMEOUT,
    LITERATURE_FETCHER_SLEEP_SECONDS,
    WILEY_FETCH_URL_TEMPLATE,
)
from ..base import BaseFetcher
from ..registry import register_fetcher
from ..utils import sanitize_filename


class WileyFetcher(BaseFetcher):
    name = "wiley"
    output_suffix = ".html"
    content_type = "html"

    def __init__(self, *, sleep_seconds: float | None = None) -> None:
        super().__init__(sleep_seconds=sleep_seconds or LITERATURE_FETCHER_SLEEP_SECONDS)
        self.url_template = WILEY_FETCH_URL_TEMPLATE

    def fetch(self, doi: str, target_dir: Path) -> Path:  # type: ignore[override]
        target_dir.mkdir(parents=True, exist_ok=True)

        url = self.url_template.format(doi=quote(doi, safe="/"))
        headers = {
            "User-Agent": FETCHER_DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        }

        response = requests.get(url, headers=headers, timeout=FETCHER_HTTP_TIMEOUT, allow_redirects=True)
        if response.status_code != 200:
            raise RuntimeError(f"Wiley 下载失败：status={response.status_code} url={url}")

        filepath = target_dir / f"{sanitize_filename(doi)}{self.output_suffix}"
        filepath.write_text(response.text, encoding=response.encoding or "utf-8")
        self._sleep()
        return filepath


register_fetcher(WileyFetcher.name, WileyFetcher)
