from __future__ import annotations

"""
运行方法：
    python -m bensci.metadata_fetcher
"""

import csv
import logging
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from typing import Dict, List, Sequence

from bensci import config as cfg
from dotenv import load_dotenv

from .logging_utils import setup_file_logger
from .metadata_tools import (
    MetadataRecord,
    merge_records,
    search_arxiv,
    search_crossref,
    search_elsevier,
    search_openalex,
    search_pubmed,
    search_springer,
)

# --------------------- 常量配置 ---------------------
ENV_FILE = getattr(cfg, "ENV_FILE", ".env")
if ENV_FILE:
    load_dotenv(ENV_FILE)

METADATA_LOG_PATH = getattr(cfg, "METADATA_LOG_PATH", None)
if METADATA_LOG_PATH is not None:
    LOGGER = setup_file_logger("bensci.metadata_fetcher", METADATA_LOG_PATH)
else:
    LOGGER = logging.getLogger("bensci.metadata_fetcher")

ASSETS1_DIR = getattr(cfg, "ASSETS1_DIR", None)
METADATA_CSV_PATH = getattr(cfg, "METADATA_CSV_PATH", None)

# --------------------- 元数据查询配置 ---------------------
METADATA_DEFAULT_QUERY = getattr(cfg, "METADATA_DEFAULT_QUERY", "machine learning")
METADATA_MAX_RESULTS = int(getattr(cfg, "METADATA_MAX_RESULTS", 200))
PROVIDER_QUERIES: Dict[str, str] = {
    key.lower(): value
    for key, value in getattr(cfg, "METADATA_PROVIDER_QUERIES", {}).items()
    if isinstance(key, str) and isinstance(value, str)
}
PROVIDER_MAX_RESULTS: Dict[str, int] = {
    key.lower(): int(value)
    for key, value in getattr(cfg, "METADATA_PROVIDER_MAX_RESULTS", {}).items()
    if isinstance(key, str)
    and isinstance(value, (int, float))
    and int(value) > 0
}

# --------------------- Provider 调用映射 ---------------------
ProviderCallable = Callable[[str, int], List[MetadataRecord]]
PROVIDER_CLIENTS: Dict[str, ProviderCallable] = {
    "elsevier": lambda query, limit: search_elsevier(query, max_results=limit),
    "springer": lambda query, limit: search_springer(query, max_results=limit),
    "crossref": lambda query, limit: search_crossref(query, max_results=limit),
    "openalex": lambda query, limit: search_openalex(query, max_results=limit),
    "arxiv": lambda query, limit: search_arxiv(query, max_results=limit),
    "pubmed": lambda query, limit: search_pubmed(query, max_results=limit),
}


# --------------------- 编排配置（可选） ---------------------
ALL_PROVIDER_KEYS = tuple(PROVIDER_CLIENTS.keys())
_configured_providers = getattr(cfg, "METADATA_PROVIDERS", None)
if _configured_providers is None:
    PROVIDERS = ALL_PROVIDER_KEYS
else:
    PROVIDERS = tuple(_configured_providers)

_configured_preference = getattr(cfg, "METADATA_PROVIDER_PREFERENCE", None)
if _configured_preference is None:
    PROVIDER_PREFERENCE = PROVIDERS
else:
    PROVIDER_PREFERENCE = tuple(_configured_preference)

PROVIDER_SLEEP_SECONDS = float(getattr(cfg, "METADATA_PROVIDER_SLEEP_SECONDS", 0.0))
CSV_COLUMNS: Sequence[str] = tuple(
    getattr(
        cfg,
        "METADATA_CSV_COLUMNS",
        ["doi", "title", "publication", "cover_date", "url", "abstract", "authors"],
    )
)


def _provider_limit(provider: str, fallback: int) -> int:
    value = PROVIDER_MAX_RESULTS.get(provider.lower().strip())
    if value is None or value <= 0:
        return max(1, fallback)
    return int(value)


def _call_provider(provider: str, query: str, max_results: int) -> List[MetadataRecord]:
    provider_key = provider.lower().strip()
    fetcher = PROVIDER_CLIENTS.get(provider_key)
    if fetcher is None:
        LOGGER.warning("未知 Provider：%s，已跳过。", provider)
        return []

    try:
        return list(fetcher(query, max_results))
    except Exception as exc:  # pragma: no cover - 仅记录日志
        LOGGER.warning("Provider %s 调用异常，已跳过：%s", provider_key, exc)
        return []


def _balanced_trim(records: List[MetadataRecord], limit: int) -> List[MetadataRecord]:
    if limit <= 0 or len(records) <= limit:
        return records

    buckets: "OrderedDict[str, deque[MetadataRecord]]" = OrderedDict()
    for record in records:
        provider = (record.source or "unknown").lower()
        buckets.setdefault(provider, deque()).append(record)

    preferred_order: List[str] = []
    seen: set[str] = set()
    for provider in PROVIDER_PREFERENCE:
        key = provider.lower()
        if key in buckets and key not in seen:
            preferred_order.append(key)
            seen.add(key)
    for provider in buckets.keys():
        if provider not in seen:
            preferred_order.append(provider)
            seen.add(provider)

    selection: List[MetadataRecord] = []
    active = preferred_order.copy()
    while len(selection) < limit and buckets:
        if not active:
            active = [prov for prov in preferred_order if buckets.get(prov)]
            if not active:
                break
        provider = active.pop(0)
        bucket = buckets.get(provider)
        if not bucket:
            continue
        selection.append(bucket.popleft())
        if bucket:
            active.append(provider)
        else:
            buckets.pop(provider, None)
    return selection


# --------------------- 去重与合并 ---------------------
def _resolve_provider_query(provider: str, user_query: str | None) -> str:
    base_query = (user_query or "").strip()
    if base_query and base_query != METADATA_DEFAULT_QUERY:
        return base_query
    override = PROVIDER_QUERIES.get(provider.lower())
    if override:
        return override
    return base_query or METADATA_DEFAULT_QUERY


def _prefer(new_provider: str, old_provider: str) -> bool:
    """返回 True 表示 new_provider 的优先级高于 old_provider。"""

    def _idx(name: str) -> int:
        name = (name or "").lower()
        try:
            return PROVIDER_PREFERENCE.index(name)
        except ValueError:
            return len(PROVIDER_PREFERENCE) + 10

    return _idx(new_provider) < _idx(old_provider)


def _merge_across_providers(
    buckets: Dict[str, MetadataRecord],
    sources: Dict[str, str],
    new_records: List[MetadataRecord],
    provider_name: str,
) -> None:
    """
    把某个 Provider 返回的新记录合并进 buckets。
    使用 MetadataRecord.dedup_key() 去重。
    合并策略：
    - 若键未出现：直接写入
    - 若键已存在：按 PROVIDER_PREFERENCE 优先级决定主记录；对同键记录执行 merge_records
    """

    for record in new_records:
        key = record.dedup_key()
        if key not in buckets:
            buckets[key] = record
            sources[key] = provider_name
            continue

        existing = buckets[key]
        existing_source = sources.get(key, "")
        if _prefer(provider_name, existing_source):
            buckets[key] = merge_records(record, existing)
            sources[key] = provider_name
        else:
            buckets[key] = merge_records(existing, record)


# --------------------- 主入口 ---------------------
def fetch_metadata(query: str = METADATA_DEFAULT_QUERY, *, max_results: int = METADATA_MAX_RESULTS) -> List[MetadataRecord]:
    LOGGER.info("开始元数据聚合查询：%s", query)
    requested_cap = max(1, int(max_results))
    provider_caps = {prov: _provider_limit(prov, requested_cap) for prov in PROVIDERS}
    combined_cap = (
        sum(provider_caps.values()) if PROVIDER_MAX_RESULTS else None
    )
    effective_cap = requested_cap
    if combined_cap is not None and combined_cap > requested_cap:
        LOGGER.info(
            "Provider 个别上限合计 %d 超过总上限 %d，已自动扩展至 %d。",
            combined_cap,
            requested_cap,
            combined_cap,
        )
        effective_cap = combined_cap

    buckets: Dict[str, MetadataRecord] = {}
    sources: Dict[str, str] = {}

    for prov in PROVIDERS:
        LOGGER.info("调用数据源：%s", prov)
        effective_query = _resolve_provider_query(prov, query)
        if effective_query != query:
            LOGGER.debug("Provider %s 使用定制查询：%s", prov, effective_query)
        provider_limit = provider_caps.get(prov, requested_cap)
        records = _call_provider(prov, effective_query, provider_limit)
        if not records:
            continue

        for record in records:
            record.source = record.source or prov.lower().strip()
        _merge_across_providers(buckets, sources, records, prov.lower().strip())
        if PROVIDER_SLEEP_SECONDS:
            time.sleep(PROVIDER_SLEEP_SECONDS)

    results = list(buckets.values())
    if len(results) > effective_cap:
        LOGGER.info(
            "聚合结果 %d 条超过总上限 %d，按 Provider 均衡裁剪。",
            len(results),
            effective_cap,
        )
        results = _balanced_trim(results, effective_cap)

    LOGGER.info("聚合后的记录数：%d", len(results))
    return results


def write_metadata_csv(records: List[MetadataRecord]) -> None:
    if ASSETS1_DIR is None or METADATA_CSV_PATH is None:
        raise RuntimeError("缺少 ASSETS1_DIR 或 METADATA_CSV_PATH 配置")

    ASSETS1_DIR.mkdir(parents=True, exist_ok=True)
    with METADATA_CSV_PATH.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(list(CSV_COLUMNS))
        for record in records:
            row_data = record.to_dict()
            writer.writerow([row_data.get(column, "") for column in CSV_COLUMNS])

    LOGGER.info("元数据写入完成：%s", METADATA_CSV_PATH)


def main(query: str = METADATA_DEFAULT_QUERY) -> None:
    if ASSETS1_DIR is None or METADATA_CSV_PATH is None:
        raise RuntimeError("缺少 ASSETS1_DIR 或 METADATA_CSV_PATH 配置")

    ASSETS1_DIR.mkdir(parents=True, exist_ok=True)
    records = fetch_metadata(query)
    if not records:
        LOGGER.warning("未检索到任何记录，请检查查询语句或接口状态。")
        return

    write_metadata_csv(records)
    LOGGER.info("元数据采集流程结束。")


if __name__ == "__main__":
    LOGGER.info("========== 元数据采集启动 ==========")
    try:
        main()
    except Exception as err:  # pragma: no cover - CLI 入口保护
        LOGGER.exception("流程发生异常：%s", err)
        raise
    finally:
        LOGGER.info("========== 元数据采集结束 ==========")
