"""Springer/Nature full-text fetcher using the OpenAccess JATS API."""

from __future__ import annotations

import os
from pathlib import Path

import requests

from bensci.config import (
    FETCHER_DEFAULT_USER_AGENT,
    FETCHER_HTTP_TIMEOUT,
    LITERATURE_FETCHER_SLEEP_SECONDS,
    SPRINGER_OPEN_ACCESS_API_BASE,
    SPRINGER_OPEN_ACCESS_KEY_ENV,
)
from ..base import BaseFetcher
from ..registry import register_fetcher
from ..utils import sanitize_filename


class SpringerFetcher(BaseFetcher):
    name = "springer"
    output_suffix = ".xml"
    content_type = "xml"

    def __init__(self, *, api_key: str | None = None, sleep_seconds: float | None = None) -> None:
        super().__init__(sleep_seconds=sleep_seconds or LITERATURE_FETCHER_SLEEP_SECONDS)
        env_name = SPRINGER_OPEN_ACCESS_KEY_ENV
        key_from_env = os.getenv(env_name) if env_name else None
        self.api_key = api_key or key_from_env
        if not self.api_key:
            raise RuntimeError(
                f"缺少 Springer Open Access API key，请在环境变量 {env_name} 中配置。"
            )

    def fetch(self, doi: str, target_dir: Path) -> Path:  # type: ignore[override]
        target_dir.mkdir(parents=True, exist_ok=True)

        params = {"q": f"doi:{doi}", "api_key": self.api_key}
        headers = {
            "User-Agent": FETCHER_DEFAULT_USER_AGENT,
            "Accept": "application/json",
        }

        response = requests.get(
            SPRINGER_OPEN_ACCESS_API_BASE,
            params=params,
            headers=headers,
            timeout=FETCHER_HTTP_TIMEOUT,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Springer API 调用失败：status={response.status_code} body={response.text[:200]}"
            )

        data = response.json()
        records = data.get("records") or []
        if not records:
            raise RuntimeError(f"Springer API 未返回记录：doi={doi}")

        download_url: str | None = None
        for record in records:
            for entry in record.get("url", []):
                format_value = (entry.get("format") or "").lower()
                if "xml" in format_value or "jats" in format_value:
                    download_url = entry.get("value")
                    break
            if download_url:
                break

        if not download_url:
            raise RuntimeError(f"Springer API 未提供 XML 下载链接：doi={doi}")

        xml_headers = {
            "User-Agent": FETCHER_DEFAULT_USER_AGENT,
            "Accept": "application/xml",
        }
        xml_response = requests.get(download_url, headers=xml_headers, timeout=FETCHER_HTTP_TIMEOUT)
        if xml_response.status_code != 200:
            raise RuntimeError(
                f"Springer XML 下载失败：status={xml_response.status_code} body={xml_response.text[:200]}"
            )

        filepath = target_dir / f"{sanitize_filename(doi)}{self.output_suffix}"
        filepath.write_text(xml_response.text, encoding="utf-8")
        self._sleep()
        return filepath


register_fetcher(SpringerFetcher.name, SpringerFetcher)
