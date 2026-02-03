from __future__ import annotations

import argparse
import csv
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from dotenv import load_dotenv

from bensci import config as project_config
from bensci.config import BLOCKS_OUTPUT_DIR, ENV_FILE, KEYWORD_ALL_TERMS
from .extracter_tools import (
    LLMClient,
    render_semistructured_blocks,
    render_semistructured_metadata,
    resolve_provider_settings,
    select_relevant_blocks,
)
from .extracter_tools.providers import PROVIDER_PRESETS
from .logging_utils import setup_file_logger

# ---------------------------------------------------------------------------
# 默认配置 —— 可在 config.py 中覆盖对应常量
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATE = OrderedDict(
    [
        ("article_title", "文献标题"),
        ("doi", "文献 DOI"),
        (
            "reaction_system",
            "具体反应或反应体系（如 CO 氧化、CO2 加氢、甲烷活化等）",
        ),
        ("reactants", "反应物（列出关键小分子或中间体）"),
        ("products", "产物（列出主要产物）"),
        ("catalyst", "催化剂组成/材料"),
        ("catalyst_form", "催化剂形态/载体/结构（如纳米颗粒、单原子、负载体）"),
        ("active_site_or_mechanism", "活性位或机理要点（如未明确可写未提及）"),
        ("conditions", "重要条件（温度、压力、气氛、进料比例等）"),
        (
            "unresolved_elementary_kinetics_issue",
            "文献明确指出的未解决基元反应动力学问题或机理空缺",
        ),
        (
            "tap_relevance",
            "为什么适合用 TAP 研究（例如可分离吸附/反应步骤）",
        ),
        (
            "suggested_tap_experiments",
            "可执行的 TAP 实验设计要点（脉冲物种、同位素、温度窗口等）",
        ),
        (
            "evidence_snippet",
            "直接摘自原文的支持性语句，保留原句便于人工审核",
        ),
        (
            "source_blocks",
            "原 JSON 中的块编号列表，用于快速定位上下文",
        ),
        (
            "confidence_score",
            "0-1 之间的小数，表示模型对该行数据可靠性的自评",
        ),
        (
            "verification_notes",
            "人工复核建议或额外线索（如需查阅的关键词/参考文献）",
        ),
    ]
)

_PROMPTS = getattr(project_config, "LLM_PROMPTS", {})
_EXTRACTION_PROMPTS = _PROMPTS.get("extraction", {})

DEFAULT_OUTPUT_TEMPLATE: Mapping[str, str] = getattr(
    project_config,
    "LLM_EXTRACTION_OUTPUT_TEMPLATE",
    None,
) or _EXTRACTION_PROMPTS.get("output_template", _DEFAULT_TEMPLATE)
DEFAULT_SYSTEM_PROMPT: str = getattr(
    project_config,
    "LLM_EXTRACTION_SYSTEM_PROMPT",
    None,
) or _EXTRACTION_PROMPTS.get(
    "system_prompt",
    (
        "你是一名严谨的催化动力学信息抽取助手，专注于能源小分子反应。"
        "请识别文献中指出的未解决基元反应动力学问题，并判断是否适合用 "
        "TAP（Temporal Analysis of Products）来研究。"
        "输出必须严格遵循 JSON 结构，字段顺序应符合给定模板。"
        "任何缺失信息请标记为 \"未提及\"，切勿编造数据。"
    ),
)
DEFAULT_USER_PROMPT_TEMPLATE: str = getattr(
    project_config,
    "LLM_EXTRACTION_USER_PROMPT_TEMPLATE",
    None,
) or _EXTRACTION_PROMPTS.get(
    "user_prompt_template",
    (
        "请阅读以下文献元数据与节选片段，提取与能源小分子催化动力学相关的"
        "结构化信息，字段说明如下：\n{output_template}\n\n"
        "请输出 JSON 数组，每个元素对应一条记录。\n"
        "元数据：\n{metadata}\n\n"
        "候选片段 (按重要性排序)：\n{blocks}\n"
    ),
)

AUTO_SCHEMA_SYSTEM_PROMPT: str = getattr(
    project_config,
    "LLM_AUTO_SCHEMA_SYSTEM_PROMPT",
    None,
) or (
    "你是一名严谨的学术信息抽取助手，擅长把论文内容结构化为可对比的表格。"
    "请严格根据给定的字段模板(output_template)与任务要求(task)抽取信息。"
    "输出必须是合法 JSON，字段名必须与模板一致。"
    "任何缺失信息请填写“未提及”，切勿编造。"
    "如果论文与任务无关，输出空数组 []。"
)

AUTO_SCHEMA_USER_PROMPT_TEMPLATE: str = getattr(
    project_config,
    "LLM_AUTO_SCHEMA_USER_PROMPT_TEMPLATE",
    None,
) or (
    "请阅读以下文献元数据与节选片段，并按字段模板输出结构化结果。\n"
    "字段模板如下：\n{output_template}\n\n"
    "输出要求：\n"
    "- 输出必须是 JSON 数组，每个元素对应一条记录；\n"
    "- 字段名必须与模板一致；缺失填“未提及”；\n"
    "- 关键结论/数据必须给 evidence_snippet（尽量原句）与 source_blocks（块编号列表）；\n"
    "- 不要编造或推测。\n\n"
    "任务要求：\n{task}\n\n"
    "元数据：\n{metadata}\n\n"
    "候选片段（按重要性排序）：\n{blocks}\n"
)
DEFAULT_TASK_PROMPT: str = getattr(
    project_config,
    "LLM_EXTRACTION_TASK_PROMPT",
    "",
)
DEFAULT_PROVIDER: Optional[str] = getattr(
    project_config,
    "LLM_EXTRACTION_PROVIDER",
    None,
)
AVAILABLE_PROVIDERS: Sequence[str] = tuple(sorted(PROVIDER_PRESETS.keys()))
DEFAULT_MODEL: Optional[str] = getattr(project_config, "LLM_EXTRACTION_MODEL", None)
DEFAULT_OUTPUT_PATH = Path(
    getattr(
        project_config,
        "LLM_EXTRACTION_OUTPUT_PATH",
        BLOCKS_OUTPUT_DIR / "llm_extractions.csv",
    )
)
DEFAULT_BLOCK_LIMIT: int = int(
    getattr(project_config, "LLM_EXTRACTION_BLOCK_LIMIT", 28)
)
DEFAULT_TEMPERATURE: float = float(
    getattr(project_config, "LLM_EXTRACTION_TEMPERATURE", 0.1)
)
DEFAULT_LOG_PATH = Path(
    getattr(
        project_config,
        "LLM_EXTRACTION_LOG_PATH",
        BLOCKS_OUTPUT_DIR / "llm_info_extractor.log",
    )
)
DEFAULT_BASE_URL_OVERRIDE: Optional[str] = getattr(
    project_config,
    "LLM_EXTRACTION_BASE_URL",
    None,
)
DEFAULT_CHAT_PATH_OVERRIDE: Optional[str] = getattr(
    project_config,
    "LLM_EXTRACTION_CHAT_PATH",
    None,
)
DEFAULT_API_KEY_ENV_OVERRIDE: Optional[str] = getattr(
    project_config,
    "LLM_EXTRACTION_API_KEY_ENV",
    None,
)
DEFAULT_API_KEY_HEADER_OVERRIDE: Optional[str] = getattr(
    project_config,
    "LLM_EXTRACTION_API_KEY_HEADER",
    None,
)
DEFAULT_API_KEY_PREFIX_OVERRIDE: Optional[str] = getattr(
    project_config,
    "LLM_EXTRACTION_API_KEY_PREFIX",
    None,
)
DEFAULT_TIMEOUT: int = int(
    getattr(project_config, "LLM_EXTRACTION_TIMEOUT", 120)
)

_SCHEMA_PROMPTS = _PROMPTS.get("schema_discovery", {})
DEFAULT_SCHEMA_SYSTEM_PROMPT: str = getattr(
    project_config,
    "LLM_SCHEMA_DISCOVERY_SYSTEM_PROMPT",
    None,
) or _SCHEMA_PROMPTS.get(
    "system_prompt",
    (
        "你是一名严谨的“论文制表 Schema 设计助手”。你的任务是在不知道领域先验的情况下，"
        "仅根据多篇论文的元数据与片段，归纳出它们反复出现、最能代表该研究体系的关键信息维度，"
        "并把这些维度设计成表格列（字段）。"
        "字段命名必须是 snake_case（英文小写+下划线），避免过长，且尽量稳定可复用。"
        "请优先选择跨多篇论文都可能出现的字段，而不是只在个别论文里出现的细枝末节。"
        "输出必须是严格 JSON，且不要输出任何多余解释。"
    ),
)
DEFAULT_SCHEMA_USER_PROMPT_TEMPLATE: str = getattr(
    project_config,
    "LLM_SCHEMA_DISCOVERY_USER_PROMPT_TEMPLATE",
    None,
) or _SCHEMA_PROMPTS.get(
    "user_prompt_template",
    (
        "你将看到来自同一研究主题/体系的多篇论文片段。请完成两件事：\n"
        "1) 设计一个通用表头 schema：输出 output_template（JSON 对象），键是字段名(field)，值是该字段要填什么(中文说明)。\n"
        "   - 必须包含：article_title, doi\n"
        "   - 字段数量建议 10-18 个（不要超过 {max_fields} 个）\n"
        "   - 字段需覆盖：研究对象/体系、方法、关键条件、关键结果/指标、机理/解释、对比/结论、局限/未解问题等（按领域自动调整）\n"
        "2) 输出一段 task（自然语言），用于后续抽取时指导模型按该 schema 填充，并强调“未提及则写未提及、不要编造、给证据片段与块编号”。\n\n"
        "输出 JSON 结构必须为：\n"
        "{\n"
        "  \"task\": \"...\",\n"
        "  \"output_template\": {\"field\": \"desc\", ...}\n"
        "}\n\n"
        "论文样本：\n{samples}\n"
    ),
)



# ---------------------------------------------------------------------------
# 初始化环境 & 日志
# ---------------------------------------------------------------------------

load_dotenv(ENV_FILE)
LOGGER = setup_file_logger("bensci.llm_info_extractor", DEFAULT_LOG_PATH)
LOGGER.propagate = False


# ---------------------------------------------------------------------------
# 数据结构定义
# ---------------------------------------------------------------------------

@dataclass
class ExtractionRow:
    article_title: str = ""
    doi: str = ""
    reaction_system: str = ""
    reactants: str = ""
    products: str = ""
    catalyst: str = ""
    catalyst_form: str = ""
    active_site_or_mechanism: str = ""
    conditions: str = ""
    unresolved_elementary_kinetics_issue: str = ""
    tap_relevance: str = ""
    suggested_tap_experiments: str = ""
    evidence_snippet: str = ""
    source_blocks: List[str] = field(default_factory=list)
    confidence_score: Optional[float] = None
    verification_notes: str = ""
    extra_fields: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractionRow":
        source_blocks = data.get("source_blocks")
        if isinstance(source_blocks, str):
            source_blocks = [
                s.strip() for s in source_blocks.split(",") if s and s.strip()
            ]
        elif isinstance(source_blocks, list):
            cleaned_blocks: List[str] = []
            for item in source_blocks:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    cleaned_blocks.append(text)
            source_blocks = cleaned_blocks
        elif not isinstance(source_blocks, list):
            source_blocks = []

        confidence_val = data.get("confidence_score")
        if isinstance(confidence_val, str):
            try:
                confidence_val = float(confidence_val)
            except ValueError:
                confidence_val = None
        elif isinstance(confidence_val, (int, float)):
            confidence_val = float(confidence_val)
        else:
            confidence_val = None

        known_keys = {
            "article_title",
            "doi",
            "reaction_system",
            "reactants",
            "products",
            "catalyst",
            "catalyst_form",
            "active_site_or_mechanism",
            "conditions",
            "unresolved_elementary_kinetics_issue",
            "tap_relevance",
            "suggested_tap_experiments",
            "evidence_snippet",
            "source_blocks",
            "confidence_score",
            "verification_notes",
        }
        extras = {}
        for key, value in data.items():
            if key in known_keys:
                continue
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                extras[key] = "; ".join(str(v).strip() for v in value if str(v).strip())
            else:
                extras[key] = str(value).strip()

        return cls(
            article_title=str(data.get("article_title", "")),
            doi=str(data.get("doi", "")),
            reaction_system=str(data.get("reaction_system", "")),
            reactants=str(data.get("reactants", "")),
            products=str(data.get("products", "")),
            catalyst=str(data.get("catalyst", "")),
            catalyst_form=str(data.get("catalyst_form", "")),
            active_site_or_mechanism=str(data.get("active_site_or_mechanism", "")),
            conditions=str(data.get("conditions", "")),
            unresolved_elementary_kinetics_issue=str(
                data.get("unresolved_elementary_kinetics_issue", "")
            ),
            tap_relevance=str(data.get("tap_relevance", "")),
            suggested_tap_experiments=str(data.get("suggested_tap_experiments", "")),
            evidence_snippet=str(data.get("evidence_snippet", "")),
            source_blocks=source_blocks,
            confidence_score=confidence_val,
            verification_notes=str(data.get("verification_notes", "")),
            extra_fields=extras,
        )

    def to_csv_dict(self, columns: Sequence[str]) -> Dict[str, str]:
        mapping = {
            "article_title": self.article_title,
            "doi": self.doi,
            "reaction_system": self.reaction_system,
            "reactants": self.reactants,
            "products": self.products,
            "catalyst": self.catalyst,
            "catalyst_form": self.catalyst_form,
            "active_site_or_mechanism": self._clean_multiline(
                self.active_site_or_mechanism
            ),
            "conditions": self._clean_multiline(self.conditions),
            "unresolved_elementary_kinetics_issue": self._clean_multiline(
                self.unresolved_elementary_kinetics_issue
            ),
            "tap_relevance": self._clean_multiline(self.tap_relevance),
            "suggested_tap_experiments": self._clean_multiline(
                self.suggested_tap_experiments
            ),
            "evidence_snippet": self._clean_multiline(self.evidence_snippet),
            "source_blocks": self._render_source_blocks(),
            "confidence_score": (
                f"{self.confidence_score:.2f}" if self.confidence_score is not None else ""
            ),
            "verification_notes": self._clean_multiline(self.verification_notes),
        }
        row = {}
        for key in columns:
            if key in mapping:
                row[key] = mapping.get(key, "")
            else:
                row[key] = self.extra_fields.get(key, "")
        return row

    @staticmethod
    def _clean_multiline(text: str) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return " ".join(lines)

    def _render_source_blocks(self) -> str:
        parts: List[str] = []
        for block in self.source_blocks:
            if block is None:
                continue
            text = str(block).strip()
            if text:
                parts.append(text)
        return ";".join(parts)


# ---------------------------------------------------------------------------
# Agent 框架
# ---------------------------------------------------------------------------

class BaseAgent:
    name: str = "agent"

    def process(self, rows: List[ExtractionRow]) -> List[ExtractionRow]:
        raise NotImplementedError


class KeywordConfidenceAgent(BaseAgent):
    name = "keyword_confidence"

    def __init__(self) -> None:
        self._keyword_set = {kw.lower() for kw in KEYWORD_ALL_TERMS}

    def process(self, rows: List[ExtractionRow]) -> List[ExtractionRow]:
        for row in rows:
            snippet_lower = row.evidence_snippet.lower()
            keyword_hits = sum(1 for kw in self._keyword_set if kw in snippet_lower)
            if row.confidence_score is None:
                base = 0.45 if row.evidence_snippet else 0.25
                base += 0.1 if row.unresolved_elementary_kinetics_issue else 0.0
                base += 0.05 if row.reaction_system else 0.0
                base += 0.05 if row.catalyst else 0.0
                base += min(keyword_hits * 0.05, 0.2)
                base += 0.1 if row.source_blocks else 0.0
                row.confidence_score = round(min(base, 0.95), 2)
            if not row.verification_notes:
                if row.source_blocks:
                    row.verification_notes = (
                        "核查原文块：" + ", ".join(row.source_blocks)
                    )
                else:
                    row.verification_notes = "建议对照原文上下文确认数据准确性"
        return rows


class ReactionGroupingAgent(BaseAgent):
    name = "reaction_grouping"

    def process(self, rows: List[ExtractionRow]) -> List[ExtractionRow]:
        return sorted(
            rows,
            key=lambda r: (
                r.reaction_system.lower() if r.reaction_system else "",
                r.catalyst.lower() if r.catalyst else "",
                r.doi,
                r.reactants,
            ),
        )

# ---------------------------------------------------------------------------
# 配置与辅助函数
# ---------------------------------------------------------------------------

def _parse_output_template(raw: str) -> Mapping[str, str]:
    if not raw:
        return OrderedDict(DEFAULT_OUTPUT_TEMPLATE)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"输出模板不是合法 JSON：{exc}") from exc

    if isinstance(data, dict):
        return OrderedDict((str(k), str(v)) for k, v in data.items())
    if isinstance(data, list):
        items: List[tuple[str, str]] = []
        for entry in data:
            if isinstance(entry, dict) and "field" in entry and "desc" in entry:
                items.append((str(entry["field"]), str(entry["desc"])))
            elif (
                isinstance(entry, (list, tuple))
                and len(entry) == 2
            ):
                items.append((str(entry[0]), str(entry[1])))
            else:
                raise ValueError("输出模板数组元素格式不支持。")
        return OrderedDict(items)
    raise ValueError("输出模板需为 JSON 对象或数组。")

@dataclass
class LLMExtractionConfig:
    input_path: Path
    output_path: Path
    model: str = DEFAULT_MODEL
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    user_prompt_template: str = DEFAULT_USER_PROMPT_TEMPLATE
    output_template: Mapping[str, str] = field(
        default_factory=lambda: OrderedDict(DEFAULT_OUTPUT_TEMPLATE)
    )
    task_prompt: str = DEFAULT_TASK_PROMPT
    block_limit: int = DEFAULT_BLOCK_LIMIT
    temperature: float = DEFAULT_TEMPERATURE
    provider: str = DEFAULT_PROVIDER or ""
    base_url_override: Optional[str] = DEFAULT_BASE_URL_OVERRIDE
    chat_path_override: Optional[str] = DEFAULT_CHAT_PATH_OVERRIDE
    api_key_env_override: Optional[str] = DEFAULT_API_KEY_ENV_OVERRIDE
    api_key_header_override: Optional[str] = DEFAULT_API_KEY_HEADER_OVERRIDE
    api_key_prefix_override: Optional[str] = DEFAULT_API_KEY_PREFIX_OVERRIDE
    timeout: int = DEFAULT_TIMEOUT
    auto_schema: bool = False
    schema_sample_size: int = 6
    schema_max_fields: int = 18
    schema_output_path: Optional[Path] = None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "LLMExtractionConfig":
        input_path = Path(args.input).resolve()
        output_path = Path(args.output).resolve()
        model = args.model or DEFAULT_MODEL
        block_limit = args.block_limit or DEFAULT_BLOCK_LIMIT
        temperature = args.temperature if args.temperature is not None else DEFAULT_TEMPERATURE
        system_prompt = args.system_prompt or DEFAULT_SYSTEM_PROMPT
        user_prompt_template = args.user_prompt_template or DEFAULT_USER_PROMPT_TEMPLATE
        task_prompt = args.task or DEFAULT_TASK_PROMPT
        output_template = (
            _parse_output_template(args.output_template)
            if args.output_template
            else OrderedDict(DEFAULT_OUTPUT_TEMPLATE)
        )
        provider = args.provider or DEFAULT_PROVIDER
        if not provider:
            available = ", ".join(AVAILABLE_PROVIDERS)
            raise ValueError(
                "未指定 LLM 厂家。请在 config.LLM_EXTRACTION_PROVIDER 设置，"
                "或在命令行通过 --provider 传入。预设可选值："
                f"{available or '（请在 providers.py 中添加预设）'}"
            )
        if not model:
            raise ValueError(
                "未指定 LLM 模型。请在 config.LLM_EXTRACTION_MODEL 设置，"
                "或在命令行通过 --model 传入。"
            )
        base_url = args.base_url if args.base_url is not None else DEFAULT_BASE_URL_OVERRIDE
        chat_path = args.chat_path if args.chat_path is not None else DEFAULT_CHAT_PATH_OVERRIDE
        api_key_env = (
            args.api_key_env if args.api_key_env is not None else DEFAULT_API_KEY_ENV_OVERRIDE
        )
        api_key_header = (
            args.api_key_header if args.api_key_header is not None else DEFAULT_API_KEY_HEADER_OVERRIDE
        )
        api_key_prefix = (
            args.api_key_prefix if args.api_key_prefix is not None else DEFAULT_API_KEY_PREFIX_OVERRIDE
        )
        timeout = args.timeout if args.timeout is not None else DEFAULT_TIMEOUT
        auto_schema = bool(getattr(args, "auto_schema", False))
        schema_sample_size = int(getattr(args, "schema_sample_size", 6) or 6)
        schema_max_fields = int(getattr(args, "schema_max_fields", 18) or 18)
        schema_output_path = (
            Path(args.schema_output).resolve()
            if getattr(args, "schema_output", None)
            else None
        )
        return cls(
            input_path=input_path,
            output_path=output_path,
            model=model,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt_template,
            output_template=output_template,
            task_prompt=task_prompt,
            block_limit=block_limit,
            temperature=temperature,
            provider=provider,
            base_url_override=base_url,
            chat_path_override=chat_path,
            api_key_env_override=api_key_env,
            api_key_header_override=api_key_header,
            api_key_prefix_override=api_key_prefix,
            timeout=timeout,
            auto_schema=auto_schema,
            schema_sample_size=schema_sample_size,
            schema_max_fields=schema_max_fields,
            schema_output_path=schema_output_path,
        )

    def render_template_doc(self) -> str:
        return "\n".join(
            f"- {field}: {desc}" for field, desc in self.output_template.items()
        )

    def build_provider_settings(self) -> ProviderSettings:
        return resolve_provider_settings(
            self.provider,
            base_url=self.base_url_override,
            chat_path=self.chat_path_override,
            api_key_env=self.api_key_env_override,
            api_key_header=self.api_key_header_override,
            api_key_prefix=self.api_key_prefix_override,
        )


# ---------------------------------------------------------------------------
# 核心流水线
# ---------------------------------------------------------------------------

class LLMExtractionPipeline:
    def __init__(self, config: LLMExtractionConfig, agents: Optional[List[BaseAgent]] = None) -> None:
        self.config = config
        provider_settings = config.build_provider_settings()
        self.client = LLMClient(
            settings=provider_settings,
            model=config.model,
            system_prompt=config.system_prompt,
            temperature=config.temperature,
            timeout=config.timeout,
        )
        self.agents = agents or [KeywordConfidenceAgent(), ReactionGroupingAgent()]
        self._key_terms = tuple(KEYWORD_ALL_TERMS)

    def run(self) -> List[ExtractionRow]:
        if not self.client.is_available:
            raise RuntimeError(
                "未检测到 %s 环境变量，无法运行 %s LLM 抽取。"
                % (self.client.settings.api_key_env, self.client.settings.provider)
            )

        input_paths = list(self._iter_input_paths(self.config.input_path))
        if not input_paths:
            LOGGER.warning("未找到任何输入文件：%s", self.config.input_path)
            return []

        if self.config.auto_schema:
            try:
                self._apply_auto_schema(input_paths)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("自动生成表头失败，将回退到手动/默认模板：%s", exc)

        results: List[ExtractionRow] = []
        template_doc = self.config.render_template_doc()

        for json_path in input_paths:
            try:
                dataset = self._load_input_dataset(json_path)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("读取输入失败：%s | %s", json_path, exc)
                continue

            metadata = dataset.get("metadata", {})
            prompt = self._build_user_prompt(metadata, dataset.get("blocks", []), template_doc)
            try:
                completion = self.client.generate(prompt)
                rows = self._parse_rows(completion, metadata)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("LLM 提取失败：%s | %s", json_path.name, exc)
                continue

            LOGGER.info("%s -> 解析到 %d 条记录", json_path.name, len(rows))
            results.extend(rows)

        for agent in self.agents:
            try:
                results = agent.process(results)
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("Agent %s 处理失败：%s", agent.name, exc)

        if results:
            self._write_csv(results, self.config.output_path)
            LOGGER.info("已写入最终结果，共 %d 条：%s", len(results), self.config.output_path)
        else:
            LOGGER.warning("未生成任何抽取结果，未写入文件。")

        return results

    def _apply_auto_schema(self, input_paths: Sequence[Path]) -> None:
        sample_paths = list(input_paths[: max(1, self.config.schema_sample_size)])
        samples = []
        for path in sample_paths:
            try:
                dataset = self._load_input_dataset(path)
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Schema 样本读取失败，跳过：%s | %s", path.name, exc)
                continue
            metadata = dataset.get("metadata", {}) or {}
            blocks = dataset.get("blocks", []) or []
            selected = self._select_blocks_for_schema(blocks, limit=10)
            samples.append(
                {
                    "source_file": path.name,
                    "metadata": render_semistructured_metadata(metadata),
                    "blocks": render_semistructured_blocks(selected, snippet_length=260),
                }
            )
        if not samples:
            raise RuntimeError("没有可用于 schema 生成的样本输入。")

        prompt = DEFAULT_SCHEMA_USER_PROMPT_TEMPLATE.format(
            samples=json.dumps(samples, ensure_ascii=False, indent=2),
            max_fields=max(8, self.config.schema_max_fields),
        )
        schema_client = LLMClient(
            settings=self.client.settings,
            model=self.client.model,
            system_prompt=DEFAULT_SCHEMA_SYSTEM_PROMPT,
            temperature=min(self.client.temperature, 0.2),
            timeout=self.client.timeout,
        )
        completion = schema_client.generate(prompt)
        payload = self._coerce_json(completion)
        task, template = self._parse_schema_payload(payload)

        self.config.output_template = template
        if task and not self.config.task_prompt:
            self.config.task_prompt = task
        if self.config.system_prompt == DEFAULT_SYSTEM_PROMPT:
            self.config.system_prompt = AUTO_SCHEMA_SYSTEM_PROMPT
            self.client.system_prompt = AUTO_SCHEMA_SYSTEM_PROMPT
        if self.config.user_prompt_template == DEFAULT_USER_PROMPT_TEMPLATE:
            self.config.user_prompt_template = AUTO_SCHEMA_USER_PROMPT_TEMPLATE

        output_path = self.config.schema_output_path
        if output_path is None:
            output_path = self.config.output_path.with_suffix(".schema.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "task": self.config.task_prompt,
                    "output_template": template,
                    "sample_files": [p.name for p in sample_paths],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        LOGGER.info("已自动生成表头 schema：%s", output_path)

    @staticmethod
    def _select_blocks_for_schema(
        blocks: Sequence[Dict[str, Any]],
        *,
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not blocks:
            return []

        scored: List[Tuple[int, int, Dict[str, Any]]] = []
        fallback: List[Tuple[int, Dict[str, Any]]] = []
        for idx, block in enumerate(blocks):
            block_dict = dict(block)
            text = str(block_dict.get("content", "") or "")
            lowered = text.lower()
            meta = block_dict.get("metadata") or {}
            score = 0
            block_type = str(block_dict.get("type") or "")
            if block_type == "table":
                score += 5
            elif block_type == "figure":
                score += 3
            if isinstance(meta, dict):
                role = str(meta.get("role") or "").lower()
                heading_level = meta.get("heading_level")
                if role in {"heading", "title", "section_title"}:
                    score += 2
                if isinstance(heading_level, int) and heading_level <= 3:
                    score += 2
            if any(token in lowered for token in ("abstract", "introduction", "methods", "experimental", "results", "discussion", "conclusion")):
                score += 1
            if any(ch.isdigit() for ch in text):
                score += 1
            if any(unit in text for unit in ("%", "±", "°", "K", "bar", "Pa", "MPa", "mA", "V")):
                score += 1
            if score:
                scored.append((score, idx, block_dict))
            else:
                fallback.append((idx, block_dict))

        ranked = [b for _, _, b in sorted(scored, key=lambda item: (-item[0], item[1]))]
        if len(ranked) < limit:
            need = limit - len(ranked)
            ranked.extend(b for _, b in sorted(fallback, key=lambda item: item[0])[:need])
        return ranked[:limit]

    def _parse_schema_payload(self, payload: Any) -> Tuple[str, "OrderedDict[str, str]"]:
        task = ""
        template_raw: Any = None

        if isinstance(payload, dict):
            if "output_template" in payload:
                template_raw = payload.get("output_template")
                task = str(payload.get("task") or "").strip()
            else:
                template_raw = payload
        if template_raw is None:
            raise ValueError("Schema 生成输出中未找到 output_template。")

        template = self._coerce_template_mapping(template_raw)
        template = self._ensure_required_schema_fields(template)
        max_fields = max(4, int(self.config.schema_max_fields))
        if len(template) > max_fields:
            template = OrderedDict(list(template.items())[:max_fields])
        return task, template

    @staticmethod
    def _coerce_template_mapping(raw: Any) -> "OrderedDict[str, str]":
        if isinstance(raw, str):
            raw = raw.strip()
            if raw:
                try:
                    raw = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Schema output_template 不是合法 JSON：{exc}") from exc

        if isinstance(raw, dict):
            items = [(str(k).strip(), str(v).strip()) for k, v in raw.items() if str(k).strip()]
            return OrderedDict(items)

        if isinstance(raw, list):
            items: List[tuple[str, str]] = []
            for entry in raw:
                if isinstance(entry, dict) and "field" in entry and "desc" in entry:
                    items.append((str(entry["field"]).strip(), str(entry["desc"]).strip()))
                elif isinstance(entry, (list, tuple)) and len(entry) == 2:
                    items.append((str(entry[0]).strip(), str(entry[1]).strip()))
            return OrderedDict((k, v) for k, v in items if k)

        raise ValueError("Schema output_template 需为对象或数组。")

    @staticmethod
    def _ensure_required_schema_fields(template: "OrderedDict[str, str]") -> "OrderedDict[str, str]":
        required = OrderedDict(
            [
                ("article_title", "文献标题"),
                ("doi", "文献 DOI"),
            ]
        )
        merged: "OrderedDict[str, str]" = OrderedDict()
        for key, desc in required.items():
            merged[key] = desc
        for key, desc in template.items():
            if key in merged:
                continue
            merged[key] = desc
        return merged

    def _build_user_prompt(
        self,
        metadata: Dict[str, Any],
        blocks: Sequence[Dict[str, Any]],
        template_doc: str,
    ) -> str:
        selected_blocks = select_relevant_blocks(
            blocks,
            limit=self.config.block_limit,
            key_terms=self._key_terms,
        )
        metadata_text = render_semistructured_metadata(metadata)
        blocks_text = render_semistructured_blocks(selected_blocks)
        template = self.config.user_prompt_template
        format_args = {
            "metadata": metadata_text,
            "blocks": blocks_text,
            "output_template": template_doc,
        }
        if "{task}" in template:
            format_args["task"] = self.config.task_prompt
        prompt = template.format(**format_args)
        if "{task}" not in template and self.config.task_prompt:
            prompt = f"{prompt}\n\n任务要求:\n{self.config.task_prompt}"
        return prompt

    def _parse_rows(
        self,
        completion_text: str,
        metadata: Mapping[str, Any],
    ) -> List[ExtractionRow]:
        data = self._coerce_json(completion_text)
        if isinstance(data, dict):
            candidates = data.get("rows") or data.get("records") or data.get("data")
            if candidates is None:
                candidates = [data]
        elif isinstance(data, list):
            candidates = data
        else:
            raise ValueError(f"无法解析 LLM 输出：{type(data)}")

        rows: List[ExtractionRow] = []
        for raw in candidates:
            if not isinstance(raw, dict):
                LOGGER.debug("跳过非字典结果：%s", raw)
                continue
            raw.setdefault("article_title", metadata.get("title", ""))
            raw.setdefault("doi", metadata.get("doi", ""))
            row = ExtractionRow.from_dict(raw)
            rows.append(row)
        return rows

    def _coerce_json(self, text: str) -> Any:
        stripped = text.strip()
        for candidate in [stripped, self._extract_bracket_payload(stripped)]:
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except (TypeError, json.JSONDecodeError):
                continue
        raise ValueError("LLM 输出不是合法 JSON：\n" + stripped)

    @staticmethod
    def _extract_bracket_payload(text: str) -> Optional[str]:
        for opener, closer in (("[", "]"), ("{", "}")):
            start = text.find(opener)
            end = text.rfind(closer)
            if start != -1 and end != -1 and end > start:
                return text[start : end + 1]
        return None

    def _load_json(self, path: Path) -> Dict[str, Any]:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _load_input_dataset(self, path: Path) -> Dict[str, Any]:
        suffix = path.suffix.lower()
        if suffix == ".json":
            return self._load_json(path)
        if suffix in {".md", ".markdown", ".txt"}:
            return self._parse_markdown(path)
        if suffix in {".pdf", ".xml", ".html", ".htm"}:
            return self._parse_with_transer(path)
        raise ValueError(f"不支持的输入格式：{path}")

    def _parse_markdown(self, path: Path) -> Dict[str, Any]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        metadata: Dict[str, Any] = {}
        body = text

        if text.lstrip().startswith("---"):
            parts = text.split("\n")
            if len(parts) > 2:
                end_idx = None
                for idx in range(1, len(parts)):
                    if parts[idx].strip() == "---":
                        end_idx = idx
                        break
                if end_idx is not None:
                    front = parts[1:end_idx]
                    body = "\n".join(parts[end_idx + 1 :])
                    for line in front:
                        if ":" not in line:
                            continue
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        val = value.strip()
                        if not key:
                            continue
                        metadata[key] = val

        title = None
        lines = body.splitlines()
        blocks: List[Dict[str, Any]] = []
        buffer: List[str] = []
        idx = 1

        def _flush_buffer() -> None:
            nonlocal idx
            if not buffer:
                return
            content = "\n".join(buffer).strip()
            buffer.clear()
            if not content:
                return
            blocks.append({"idx": f"T{idx}", "type": "text", "content": content})
            idx += 1

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                _flush_buffer()
                heading = stripped.lstrip("#").strip()
                if heading:
                    if title is None:
                        title = heading
                    blocks.append({"idx": f"T{idx}", "type": "text", "content": heading})
                    idx += 1
                continue
            if stripped == "":
                _flush_buffer()
            else:
                buffer.append(line)

        _flush_buffer()
        if not title:
            title = metadata.get("title") or path.stem

        authors = metadata.get("authors") or metadata.get("author")
        author_list = None
        if authors:
            if isinstance(authors, str):
                author_list = [a.strip() for a in authors.replace(";", ",").split(",") if a.strip()]
            elif isinstance(authors, list):
                author_list = [str(a).strip() for a in authors if str(a).strip()]

        meta_payload = {
            "title": title,
            "doi": metadata.get("doi") or "",
            "journal": metadata.get("journal") or "",
            "date": metadata.get("date") or "",
            "author_list": author_list,
        }
        return {"metadata": meta_payload, "blocks": blocks}

    def _parse_with_transer(self, path: Path) -> Dict[str, Any]:
        from bensci.literature_transer import parse_document

        document = parse_document(path)
        return document.to_dict()

    def _write_csv(self, rows: Sequence[ExtractionRow], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        columns = list(self.config.output_template.keys())
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            for idx, row in enumerate(rows, start=1):
                try:
                    writer.writerow(row.to_csv_dict(columns))
                except Exception as exc:  # noqa: BLE001
                    raise RuntimeError(
                        f"写入 CSV 失败：第 {idx} 行（DOI={row.doi or '未知'}）无法序列化"
                    ) from exc

    @staticmethod
    def _iter_input_paths(path: Path) -> Iterable[Path]:
        allowed = {".json", ".md", ".markdown", ".txt", ".pdf", ".xml", ".html", ".htm"}
        if path.is_file() and path.suffix.lower() in allowed:
            yield path
        elif path.is_dir():
            for file in sorted(path.iterdir()):
                if file.is_file() and file.suffix.lower() in allowed:
                    yield file


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="根据增强后的 JSON 让 LLM 生成 TAP 动力学问题表格"
    )
    parser.add_argument(
        "--input",
        default=str(BLOCKS_OUTPUT_DIR),
        help="输入 JSON 或目录，默认使用增强后的块化目录",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_PATH),
        help="输出 CSV 路径，默认写入增强目录",
    )
    parser.add_argument(
        "--system-prompt",
        default=None,
        help="覆盖 system prompt",
    )
    parser.add_argument(
        "--user-prompt-template",
        default=None,
        help="覆盖 user prompt 模板（可包含 {metadata}/{blocks}/{output_template}/{task}）",
    )
    parser.add_argument(
        "--task",
        default=None,
        help="追加的任务说明（自然语言）",
    )
    parser.add_argument(
        "--output-template",
        default=None,
        help="JSON 输出模板（对象或数组）",
    )
    parser.add_argument(
        "--auto-schema",
        action="store_true",
        help="在未提供任务/模板时，先自动从多篇论文样本归纳表头 schema，再按 schema 抽取",
    )
    parser.add_argument(
        "--schema-sample-size",
        type=int,
        default=6,
        help="自动生成 schema 时抽样的论文数量",
    )
    parser.add_argument(
        "--schema-max-fields",
        type=int,
        default=18,
        help="自动生成 schema 的最大字段数（包含 article_title/doi）",
    )
    parser.add_argument(
        "--schema-output",
        default=None,
        help="自动生成的 schema 输出路径（默认写到 output.csv 同目录，扩展名 .schema.json）",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="调用的 LLM 模型名称，默认读取 config.LLM_EXTRACTION_MODEL",
    )
    parser.add_argument(
        "--provider",
        default=DEFAULT_PROVIDER,
        help="LLM 厂家标识（例如 openai、dashscope、deepseek）",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="自定义 API 基础地址，若不填写则使用预设或 config 中的值",
    )
    parser.add_argument(
        "--chat-path",
        default=None,
        help="自定义 Chat Completions 路径，默认 /chat/completions",
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help="自定义 API Key 所在的环境变量名",
    )
    parser.add_argument(
        "--api-key-header",
        default=None,
        help="自定义 HTTP 头部用于发送 Key 的字段名，默认 Authorization",
    )
    parser.add_argument(
        "--api-key-prefix",
        default=None,
        help="自定义 Key 前缀（例如 Bearer ），留空表示不加前缀",
    )
    parser.add_argument(
        "--block-limit",
        type=int,
        default=DEFAULT_BLOCK_LIMIT,
        help="传给 LLM 的片段数量上限",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="LLM temperature 参数",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="HTTP 请求超时时间（秒）",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = LLMExtractionConfig.from_args(args)

    logging.basicConfig(level=logging.INFO)
    try:
        pipeline = LLMExtractionPipeline(config=config)
        pipeline.run()
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("LLM 信息抽取流程异常：%s", exc)
        raise


if __name__ == "__main__":  # pragma: no cover
    main()
