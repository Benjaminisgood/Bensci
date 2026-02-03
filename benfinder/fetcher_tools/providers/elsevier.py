"""Elsevier full-text XML fetcher."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple
from urllib.parse import quote

import requests

from benfinder.config import FETCHER_DEFAULT_USER_AGENT, FETCHER_HTTP_TIMEOUT, LITERATURE_FETCHER_SLEEP_SECONDS
from ..base import BaseFetcher
from ..registry import register_fetcher
from ..utils import sanitize_filename


class ElsevierFetcher(BaseFetcher):
    name = "elsevier"
    base_url = "https://api.elsevier.com/content/article/doi/{doi}"
    output_suffix = ".xml"
    content_type = "xml"

    def __init__(self, *, api_key: str | None = None, sleep_seconds: float | None = None) -> None:
        super().__init__(sleep_seconds=sleep_seconds or LITERATURE_FETCHER_SLEEP_SECONDS)
        self.api_key = api_key or os.getenv("ELSEVIER_API_KEY")
        if not self.api_key:
            raise RuntimeError("缺少 ELSEVIER_API_KEY，无法下载全文。")

    def fetch(self, doi: str, target_dir: Path) -> Path:  # type: ignore[override]
        return self._fetch_with_client(doi, target_dir, session=None)

    def fetch_many(  # type: ignore[override]
        self,
        dois: Iterable[str],
        target_dir: Path,
    ) -> Iterator[Tuple[str, Optional[Path], Optional[Exception]]]:
        with requests.Session() as session:
            session.headers.update({"User-Agent": FETCHER_DEFAULT_USER_AGENT})
            for doi in dois:
                try:
                    path = self._fetch_with_client(doi, target_dir, session=session)
                except Exception as exc:  # noqa: BLE001
                    yield doi, None, exc
                else:
                    yield doi, path, None

    def _fetch_with_client(
        self,
        doi: str,
        target_dir: Path,
        *,
        session: Optional[requests.Session],
    ) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        url = self.base_url.format(doi=quote(doi, safe=""))
        headers = {"X-ELS-APIKey": self.api_key, "Accept": "application/xml"}
        params = {"view": "FULL"}

        client = session or requests
        resp = client.get(
            url,
            headers=headers,
            params=params,
            timeout=FETCHER_HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"下载失败：doi={doi} | status={resp.status_code}")

        filepath = target_dir / f"{sanitize_filename(doi)}{self.output_suffix}"
        filepath.write_text(resp.text, encoding="utf-8")
        self._sleep()
        return filepath


register_fetcher(ElsevierFetcher.name, ElsevierFetcher)
