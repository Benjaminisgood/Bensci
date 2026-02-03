"""Download publisher content (XML/HTML/PDF) based on metadata or DOI list."""

from __future__ import annotations

import argparse
import csv
import re
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Sequence

from dotenv import load_dotenv

from benfinder.config import (
    ASSETS2_DIR,
    ENV_FILE,
    LITERATURE_FETCHER_LOG_PATH,
    LITERATURE_FETCHER_PROVIDER_ORDER,
    METADATA_CSV_PATH,
)
from .fetcher_tools import BaseFetcher, available_fetchers, describe_fetchers, get_fetcher
from .logging_utils import setup_file_logger

load_dotenv(ENV_FILE)
LOGGER = setup_file_logger("benfinder.literature_fetcher", LITERATURE_FETCHER_LOG_PATH)


def _normalize_dois(doi_input: str | Sequence[str] | None) -> List[str]:
    if doi_input is None:
        return []
    if isinstance(doi_input, str):
        tokens = re.split(r"[,\s]+", doi_input.strip())
        return [token for token in tokens if token]
    normalized: List[str] = []
    for item in doi_input:
        if not item:
            continue
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def _read_metadata_rows(csv_path: Path) -> list[dict[str, str]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"找不到筛选后的 CSV：{csv_path}")

    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


DOI_PREFIX_MAP = {
    "10.1016": "elsevier",
    "10.1007": "springer",
    "10.1021": "acs",
    "10.1039": "rsc",
    "10.1002": "wiley",
}


def guess_provider(doi: str, default: str = "elsevier") -> str:
    prefix = doi.split("/")[0]
    return DOI_PREFIX_MAP.get(prefix, default)


def download_fulltexts(
    *,
    csv_path: Path = METADATA_CSV_PATH,
    output_dir: Path = ASSETS2_DIR,
    provider: str | None = None,
    doi: str | Sequence[str] | None = None,
) -> None:
    provider = provider.lower() if provider else None
    provider_info = describe_fetchers()
    LOGGER.info("可用 fetcher：%s", provider_info)

    fetcher_cache: Dict[str, BaseFetcher] = {}

    def _resolve(name: str) -> BaseFetcher:
        key = name.lower()
        if key not in fetcher_cache:
            fetcher_cache[key] = get_fetcher(key)
        return fetcher_cache[key]

    registered_names = set(provider_info.keys())
    scihub_provider = "scihub" if "scihub" in registered_names else None

    configured_order = [
        name.lower()
        for name in (LITERATURE_FETCHER_PROVIDER_ORDER or [])
        if isinstance(name, str)
    ]
    fallback_order: List[str] = []
    for name in configured_order:
        if name in registered_names and name != "scihub" and name not in fallback_order:
            fallback_order.append(name)
    for name in sorted(registered_names):
        if name == "scihub" or name in fallback_order:
            continue
        fallback_order.append(name)

    if not fallback_order:
        LOGGER.error("没有可用的 publisher fetcher，无法开始下载。")
        return

    LOGGER.info("provider 尝试顺序（不含 Sci-Hub）：%s", " -> ".join(fallback_order))

    normalized_list = _normalize_dois(doi)
    raw_records: List[tuple[str, str]] = []
    if normalized_list:
        LOGGER.info("启用 DOI 下载模式，本次共 %d 篇", len(normalized_list))
        for item in normalized_list:
            provider_name = provider or guess_provider(item)
            raw_records.append((item, provider_name))
    else:
        rows = _read_metadata_rows(csv_path)
        if not rows:
            LOGGER.info("筛选 CSV 为空，未执行下载。")
            return

        for row in rows:
            row_doi = row.get("doi") or row.get("DOI")
            if not row_doi:
                LOGGER.warning("记录缺少 DOI，跳过：%s", row)
                continue

            provider_name = provider or guess_provider(row_doi)
            raw_records.append((row_doi, provider_name))

    deduped_records: List[tuple[str, str | None]] = []
    seen: set[str] = set()
    for doi_value, provider_name in raw_records:
        doi_clean = doi_value.strip()
        if not doi_clean or doi_clean in seen:
            continue
        seen.add(doi_clean)
        deduped_records.append((doi_clean, (provider_name or "").lower() or None))

    if not deduped_records:
        LOGGER.info("没有可下载的 DOI。")
        return

    total = len(deduped_records)
    LOGGER.info("开始下载全文，共 %d 篇，逐个 DOI 重试所有 provider。", total)

    def _candidate_sequence(initial: str | None) -> List[str]:
        sequence: List[str] = []
        if initial and initial in fallback_order:
            sequence.append(initial)
        elif initial and initial not in registered_names:
            LOGGER.warning("未注册 provider=%s，使用默认顺序。", initial)
        for name in fallback_order:
            if name not in sequence:
                sequence.append(name)
        return sequence

    doi_order = [doi_value for doi_value, _ in deduped_records]
    attempt_plan: Dict[str, Deque[str]] = {}
    for doi_value, initial_provider in deduped_records:
        candidates = _candidate_sequence(initial_provider)
        if not candidates:
            LOGGER.warning("DOI=%s 未找到可用 provider，跳过。", doi_value)
            continue
        attempt_plan[doi_value] = deque(candidates)

    if not attempt_plan:
        LOGGER.error("没有可用的 DOI 下载任务，流程结束。")
        return

    successes: Dict[str, Path] = {}

    for provider_name in fallback_order:
        current_batch = [
            doi_value
            for doi_value in doi_order
            if doi_value in attempt_plan
            and doi_value not in successes
            and attempt_plan[doi_value]
            and attempt_plan[doi_value][0] == provider_name
        ]
        if not current_batch:
            continue

        fetcher = _resolve(provider_name)
        LOGGER.info(
            "provider=%s 尝试下载 %d 篇（剩余 %d 篇待完成）",
            provider_name,
            len(current_batch),
            total - len(successes),
        )

        for current_doi, path, error in fetcher.fetch_many(current_batch, output_dir):
            attempt_plan[current_doi].popleft()
            if error is None and path is not None:
                successes[current_doi] = path
                attempt_plan[current_doi].clear()
                LOGGER.info(
                    "下载成功：%s -> %s (provider=%s, content=%s)",
                    current_doi,
                    path.name,
                    provider_name,
                    getattr(fetcher, "content_type", "unknown"),
                )
                continue

            if isinstance(error, NotImplementedError):
                LOGGER.warning(
                    "provider=%s 尚未实现下载逻辑，已跳过 DOI=%s",
                    provider_name,
                    current_doi,
                )
            else:
                LOGGER.error(
                    "下载失败：%s | provider=%s | %s",
                    current_doi,
                    provider_name,
                    error,
                )

    pending_for_scihub = [doi_value for doi_value in doi_order if doi_value not in successes]
    if pending_for_scihub and scihub_provider:
        fetcher = _resolve(scihub_provider)
        LOGGER.info(
            "常规 provider 均失败，使用 Sci-Hub 兜底 %d 篇。",
            len(pending_for_scihub),
        )
        for current_doi, path, error in fetcher.fetch_many(pending_for_scihub, output_dir):
            if error is None and path is not None:
                successes[current_doi] = path
                LOGGER.info(
                    "Sci-Hub 下载成功：%s -> %s",
                    current_doi,
                    path.name,
                )
                continue
            LOGGER.error("Sci-Hub 下载失败：%s | %s", current_doi, error)
        pending_for_scihub = [doi_value for doi_value in doi_order if doi_value not in successes]
    elif pending_for_scihub and not scihub_provider:
        LOGGER.warning(
            "有 %d 篇全文使用常规 provider 下载失败，且未启用 Sci-Hub。", len(pending_for_scihub)
        )

    failed_dois = [doi_value for doi_value in doi_order if doi_value not in successes]
    LOGGER.info(
        "全文下载流程结束：成功 %d，失败 %d。",
        len(successes),
        len(failed_dois),
    )
    if failed_dois:
        sample = ", ".join(failed_dois[:10])
        suffix = "..." if len(failed_dois) > 10 else ""
        LOGGER.error("仍失败的 DOI（部分）：%s%s", sample, suffix)

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="下载期刊全文 (XML/HTML)")
    parser.add_argument(
        "--input",
        default=str(METADATA_CSV_PATH),
        help="包含 DOI 列的 CSV 路径",
    )
    parser.add_argument(
        "--output",
        default=str(ASSETS2_DIR),
        help="XML 输出目录",
    )
    parser.add_argument(
        "--provider",
        default="auto",
        choices=["auto", *available_fetchers()],
        help="下载来源提供商，auto 表示按 DOI 前缀自动推断",
    )
    parser.add_argument(
        "--doi",
        help="指定 DOI（可用逗号/空格分隔多个）直接拉取全文；设置后忽略 CSV 记录",
    )
    args = parser.parse_args(argv)

    csv_path = Path(args.input)
    output_dir = Path(args.output)

    selected_provider = None if args.provider == "auto" else args.provider
    explicit_doi = args.doi.strip() if args.doi else None

    try:
        download_fulltexts(
            csv_path=csv_path,
            output_dir=output_dir,
            provider=selected_provider,
            doi=explicit_doi,
        )
    except Exception as err:  # noqa: BLE001
        LOGGER.exception("下载流程发生异常：%s", err)
        raise


if __name__ == "__main__":
    LOGGER.info("========== 全文下载启动 ==========")
    try:
        main()
    finally:
        LOGGER.info("========== 全文下载结束 ==========")
