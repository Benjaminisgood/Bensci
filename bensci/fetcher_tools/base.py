"""Abstract base classes for literature fetchers."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable, Iterator, Optional, Tuple


class BaseFetcher(ABC):
    name: str = "base"
    output_suffix: str = ".xml"
    content_type: str = "xml"

    def __init__(self, *, sleep_seconds: float = 0.0) -> None:
        self.sleep_seconds = sleep_seconds

    @abstractmethod
    def fetch(self, doi: str, target_dir: Path) -> Path:
        """Download the article identified by DOI into target_dir."""

    def fetch_many(
        self,
        dois: Iterable[str],
        target_dir: Path,
    ) -> Iterator[Tuple[str, Optional[Path], Optional[Exception]]]:
        """
        Download multiple DOIs sequentially.

        Returns an iterator of (doi, path, error). Only the first non-None between
        path/error will be populated for each DOI.
        """

        for doi in dois:
            try:
                path = self.fetch(doi, target_dir)
            except Exception as exc:  # noqa: BLE001
                yield doi, None, exc
            else:
                yield doi, path, None

    def _sleep(self) -> None:
        if self.sleep_seconds > 0:
            time.sleep(self.sleep_seconds)
