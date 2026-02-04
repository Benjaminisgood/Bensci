"""
对元数据摘要进行 LLM 筛选，保留能源小分子催化中未解决的基元动力学问题。
"""

from __future__ import annotations

import argparse
import csv
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from bensci import config as project_config
from .extracter_tools import LLMClient, resolve_provider_settings
from .logging_utils import setup_file_logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS1_DIR = getattr(project_config, "ASSETS1_DIR", PROJECT_ROOT / "assets1")
SOURCE_CSV = getattr(
    project_config,
    "METADATA_CSV_PATH",
    ASSETS1_DIR / "elsevier_metadata.csv",
)
TARGET_CSV = getattr(
    project_config,
    "FILTERED_METADATA_CSV_PATH",
    ASSETS1_DIR / "elsevier_metadata_filtered.csv",
)
LOG_PATH = getattr(
    project_config,
    "METADATA_FILTER_LOG_PATH",
    ASSETS1_DIR / "metadata_filter.log",
)

LOGGER = setup_file_logger("bensci.metadata_filter", LOG_PATH)

ENV_PATH = getattr(project_config, "ENV_FILE", PROJECT_ROOT / ".env")
load_dotenv(ENV_PATH)

DEFAULT_PROVIDER = getattr(project_config, "METADATA_FILTER_PROVIDER", None) or "openai"
DEFAULT_MODEL = getattr(project_config, "METADATA_FILTER_MODEL", None) or os.getenv(
    "OPENAI_MODEL", "gpt-4o-mini"
)
DEFAULT_BASE_URL = getattr(project_config, "METADATA_FILTER_BASE_URL", None)
DEFAULT_CHAT_PATH = getattr(project_config, "METADATA_FILTER_CHAT_PATH", None)
DEFAULT_API_KEY_ENV = getattr(project_config, "METADATA_FILTER_API_KEY_ENV", None)
DEFAULT_API_KEY_HEADER = getattr(project_config, "METADATA_FILTER_API_KEY_HEADER", None)
DEFAULT_API_KEY_PREFIX = getattr(project_config, "METADATA_FILTER_API_KEY_PREFIX", None)
DEFAULT_TEMPERATURE = float(getattr(project_config, "METADATA_FILTER_TEMPERATURE", 0.0))
DEFAULT_TIMEOUT = int(getattr(project_config, "METADATA_FILTER_TIMEOUT", 60))
DEFAULT_SLEEP_SECONDS = float(getattr(project_config, "METADATA_FILTER_SLEEP_SECONDS", 1.0))

_PROMPTS = getattr(project_config, "LLM_PROMPTS", {})
_FILTER_PROMPTS: Dict[str, str] = _PROMPTS.get("metadata_filter", {})
METADATA_FILTER_SYSTEM_PROMPT: str = (
    getattr(project_config, "METADATA_FILTER_SYSTEM_PROMPT", None)
    or _FILTER_PROMPTS.get(
        "system_prompt",
        (
            "你是一名催化文献分析助手，负责判断摘要是否满足筛选条件："
            "1) 明确涉及能源小分子催化反应；"
            "2) 指出存在未解决的基元反应动力学/机理问题；"
            "3) 摘要中至少能推断出具体反应体系或反应类型。"
            "请只回答 YES 或 NO。"
        ),
    )
)
METADATA_FILTER_USER_TEMPLATE: str = (
    getattr(project_config, "METADATA_FILTER_USER_PROMPT_TEMPLATE", None)
    or _FILTER_PROMPTS.get(
        "user_prompt_template",
        (
            "判断以下摘要是否满足筛选条件：\n"
            "- 能源小分子催化反应；\n"
            "- 指出未解决的基元反应动力学/机理问题；\n"
            "- 可推断具体反应体系或反应类型。\n"
            "只回答 YES 或 NO。\n"
            "摘要：{abstract}"
        ),
    )
)


def _build_client(
    *,
    provider: str,
    model: str,
    base_url: Optional[str],
    chat_path: Optional[str],
    api_key_env: Optional[str],
    api_key_header: Optional[str],
    api_key_prefix: Optional[str],
    system_prompt: str,
    temperature: float,
    timeout: int,
) -> LLMClient:
    settings = resolve_provider_settings(
        provider,
        base_url=base_url,
        chat_path=chat_path,
        api_key_env=api_key_env,
        api_key_header=api_key_header,
        api_key_prefix=api_key_prefix,
    )
    return LLMClient(
        settings=settings,
        model=model,
        system_prompt=system_prompt,
        temperature=temperature,
        timeout=timeout,
    )


def _filter_with_llm(
    rows: List[dict],
    client: LLMClient,
    sleep_seconds: float,
    user_prompt_template: str,
) -> List[dict]:
    """遍历元数据列表，使用 LLM 判断是否保留。"""
    passed: List[dict] = []

    for idx, row in enumerate(rows, start=1):
        abstract = row.get("abstract", "").strip()
        if not abstract:
            LOGGER.debug("记录 #%d 缺少摘要，默认跳过：%s", idx, row.get("title"))
            continue

        prompt = user_prompt_template.format(abstract=abstract)
        try:
            reply = client.generate(prompt).strip().upper()
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("调用 LLM 失败，记录 #%d 被跳过：%s", idx, exc)
            continue

        LOGGER.debug("LLM 判断 #%d -> %s", idx, reply)
        if reply.startswith("Y"):
            passed.append(row)

        if sleep_seconds:
            time.sleep(sleep_seconds)

    return passed


def filter_metadata(
    *,
    provider: str = DEFAULT_PROVIDER,
    model: str = DEFAULT_MODEL,
    base_url: Optional[str] = DEFAULT_BASE_URL,
    chat_path: Optional[str] = DEFAULT_CHAT_PATH,
    api_key_env: Optional[str] = DEFAULT_API_KEY_ENV,
    api_key_header: Optional[str] = DEFAULT_API_KEY_HEADER,
    api_key_prefix: Optional[str] = DEFAULT_API_KEY_PREFIX,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout: int = DEFAULT_TIMEOUT,
    sleep_seconds: float = DEFAULT_SLEEP_SECONDS,
    system_prompt: Optional[str] = None,
    user_prompt_template: Optional[str] = None,
) -> int:
    """执行初筛并写入新的 CSV，返回通过的条目数。"""
    if not SOURCE_CSV.exists():
        raise FileNotFoundError(f"找不到元数据文件：{SOURCE_CSV}")

    with SOURCE_CSV.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        LOGGER.warning("元数据文件为空：%s", SOURCE_CSV)
        return 0

    resolved_system_prompt = (system_prompt or "").strip() or METADATA_FILTER_SYSTEM_PROMPT
    resolved_user_template = (
        (user_prompt_template or "").strip() or METADATA_FILTER_USER_TEMPLATE
    )

    client = _build_client(
        provider=provider,
        model=model,
        base_url=base_url,
        chat_path=chat_path,
        api_key_env=api_key_env,
        api_key_header=api_key_header,
        api_key_prefix=api_key_prefix,
        system_prompt=resolved_system_prompt,
        temperature=temperature,
        timeout=timeout,
    )

    if not client.is_available:
        LOGGER.warning(
            "未配置 %s，直接复制原始 CSV（未筛选）。",
            client.settings.api_key_env,
        )
        ASSETS1_DIR.mkdir(parents=True, exist_ok=True)
        TARGET_CSV.write_text(SOURCE_CSV.read_text(encoding="utf-8"), encoding="utf-8")
        return len(rows)

    passed = _filter_with_llm(rows, client, sleep_seconds, resolved_user_template)

    ASSETS1_DIR.mkdir(parents=True, exist_ok=True)
    with TARGET_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(passed)

    LOGGER.info("LLM 初筛完成：通过 %d/%d 条记录，结果写入 %s", len(passed), len(rows), TARGET_CSV)
    return len(passed)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LLM 摘要筛选")
    parser.add_argument("--provider", default=DEFAULT_PROVIDER, help="LLM provider 标识")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM 模型名称")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="自定义 API 基础地址")
    parser.add_argument("--chat-path", default=DEFAULT_CHAT_PATH, help="自定义 Chat 路径")
    parser.add_argument("--api-key-env", default=DEFAULT_API_KEY_ENV, help="API Key 环境变量名")
    parser.add_argument("--api-key-header", default=DEFAULT_API_KEY_HEADER, help="API Key Header 名")
    parser.add_argument("--api-key-prefix", default=DEFAULT_API_KEY_PREFIX, help="API Key 前缀")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="temperature")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP 超时秒数")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS, help="请求间隔秒数")
    parser.add_argument("--system-prompt", default=None, help="覆盖 system prompt")
    parser.add_argument(
        "--user-prompt-template",
        default=None,
        help="覆盖 user prompt 模板（可包含 {abstract}）",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    try:
        count = filter_metadata(
            provider=args.provider,
            model=args.model,
            base_url=args.base_url,
            chat_path=args.chat_path,
            api_key_env=args.api_key_env,
            api_key_header=args.api_key_header,
            api_key_prefix=args.api_key_prefix,
            temperature=args.temperature,
            timeout=args.timeout,
            sleep_seconds=args.sleep,
            system_prompt=args.system_prompt,
            user_prompt_template=args.user_prompt_template,
        )
        if count == 0:
            LOGGER.info("没有任何记录通过初筛。")
    except Exception as err:  # noqa: BLE001
        LOGGER.exception("初筛流程发生异常：%s", err)


if __name__ == "__main__":
    LOGGER.info("========== 摘要初筛启动 ==========")
    main()
    LOGGER.info("========== 摘要初筛结束 ==========")
