"""集中管理项目的路径、API 以及模型配置。"""

from __future__ import annotations
from collections import OrderedDict
from pathlib import Path

# ---------- 基础路径 ----------
# 所有相对路径都基于项目根目录，以便脚本在任意启动目录下都能找到资源。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# 用于集中存储 API Key 及其他敏感配置；load_dotenv 会读取此文件。
ENV_FILE = PROJECT_ROOT / ".env"

# ---------- 目录 ----------
# 三方接口的原始/中间结果会分阶段写入 assets 目录，方便 Debug 与归档。
ASSETS1_DIR = PROJECT_ROOT / "data_resourse" / "assets1"  # 元数据 CSV、初筛结果
ASSETS2_DIR = PROJECT_ROOT / "data_resourse" / "assets2"  # 全文下载（XML/HTML/PDF）
ASSETS3_DIR = PROJECT_ROOT / "data_resourse" / "assets3"  # 文献解析后的结构化块
ASSETS4_DIR = PROJECT_ROOT / "data_resourse" / "assets4"  # LLM 抽取后的最终结果
LOGS_DIR = PROJECT_ROOT / "data_resourse" / "logs"  # 统一日志目录
PIPELINE_LOG_PATH = LOGS_DIR / "pipeline.log"  # 全流程统一日志文件

# ---------- 元数据检索配置 ----------
# 默认 Scopus 检索语句；必要时可复制到 CLI 参数中微调。
SCOPUS_DEFAULT_QUERY = (
    "TITLE-ABS-KEY ( "
    "catalys* AND (kinetic* OR microkinetic OR \"elementary step\" OR "
    "\"rate-determining\" OR mechanism) AND "
    "(CO OR CO2 OR CH4 OR H2 OR NH3 OR N2 OR \"small molecule\" OR \"C1\") "
    ")"
)

# `metadata_fetcher` 的兜底检索词，未传入 query 或单个 provider 未定义专用语句时使用。
METADATA_DEFAULT_QUERY = (
    "catalysis AND (kinetic* OR microkinetic OR \"elementary step\" OR "
    "\"rate-determining\" OR mechanism) AND "
    "(CO OR CO2 OR CH4 OR H2 OR NH3 OR N2 OR \"small molecule\" OR C1)"
)

# 聚合器写出 CSV 之前的上限；调试阶段可以暂时调成 50/100 以减少调用和写盘量。
METADATA_MAX_RESULTS = 120

# 可为每个 Provider 定义独立的抓取上限（未配置则沿用 METADATA_MAX_RESULTS）。
# 例如：{"elsevier": 80, "springer": 60}
METADATA_PROVIDER_MAX_RESULTS = {"elsevier": 20, "springer": 20, "crossref": 20,"openalex": 20, "arxiv": 20, "pubmed": 20}

# 每个 provider 可指定单独的查询语句（例如关键词语法不同），未定义则回退到 METADATA_DEFAULT_QUERY。
METADATA_PROVIDER_QUERIES = {
    "elsevier": SCOPUS_DEFAULT_QUERY,
    "springer": METADATA_DEFAULT_QUERY,
    "crossref": METADATA_DEFAULT_QUERY,
    "openalex": (
        '"catalysis" AND ("elementary step" OR "rate-determining" OR '
        'microkinetic OR kinetics) AND (CO OR CO2 OR CH4 OR H2 OR NH3 OR N2)'
    ),
    "arxiv": (
        '(ti:catalys* OR abs:catalys*) AND '
        '(abs:"elementary step" OR abs:microkinetic OR abs:kinetic*) AND '
        '(abs:CO OR abs:CO2 OR abs:CH4 OR abs:H2 OR abs:NH3 OR abs:N2)'
    ),
    "pubmed": (
        '(catalysis OR catalytic) AND (kinetic* OR "elementary step" OR '
        '"rate-determining") AND (CO OR CO2 OR CH4 OR H2 OR NH3 OR N2)'
    ),
}

# 导出的列顺序，保持与下游解析/人工检索工具一致；可加减字段但需同步消费者。
METADATA_CSV_COLUMNS = [
    "doi",
    "title",
    "publication",
    "cover_date",
    "url",
    "abstract",
    "authors",
    "source",
    "publisher",
    "volume",
    "issue",
    "pages",
    "language",
    "keywords",
    "issn",
]

# Elsevier/Scopus 请求分页、节流配置；缩小 MAX_RESULTS 可减少接口调用做冒烟测试。
SCOPUS_PAGE_SIZE = 20  # 单次请求的记录数
SCOPUS_MAX_RESULTS = 200  # 单轮扫描的最大返回量
SCOPUS_REQUEST_SLEEP_SECONDS = 0  # 请求间隔（秒）
ABSTRACT_SLEEP_SECONDS = 1  # 抓取摘要时的额外延时
SCOPUS_ALLOWED_PUBLISHER_KEYWORDS = ["elsevier", "science direct", "sciencedirect"]  # 允许的出版商关键词

# 聚合器输出文件与日志的位置；如需多项目并存，可改到自定义目录。
METADATA_CSV_PATH = ASSETS1_DIR / "elsevier_metadata.csv"
FILTERED_METADATA_CSV_PATH = ASSETS1_DIR / "elsevier_metadata_filtered.csv"
METADATA_LOG_PATH = PIPELINE_LOG_PATH
METADATA_FILTER_LOG_PATH = PIPELINE_LOG_PATH

# ---------- 全文下载配置 ----------
LITERATURE_FETCHER_LOG_PATH = PIPELINE_LOG_PATH  # 记录每篇 DOI 的下载信息
LITERATURE_FETCHER_SLEEP_SECONDS = 2   # 各 provider 请求间的最小间隔（秒），避免触发速率限制
FETCHER_DEFAULT_USER_AGENT = "bensci-fetcher/1.0"  # 统一的 UA 字符串，便于识别请求来源
FETCHER_HTTP_TIMEOUT = 60  # 单次 HTTP 请求超时（秒）
# 下载全文时的 provider 尝试顺序（不含 Sci-Hub）；按稳定性由高到低排列即可。
LITERATURE_FETCHER_PROVIDER_ORDER = ["elsevier", "springer", "acs", "wiley", "rsc"]
ACS_API_KEY_ENV = "ACS_API_KEY"  # ACS 可选 API Key 环境变量名

# Springer API 相关配置；若使用其他 key/域名，请在本地覆盖
SPRINGER_OPEN_ACCESS_API_BASE = "https://api.springernature.com/openaccess/jats"
SPRINGER_OPEN_ACCESS_KEY_ENV = "SPRINGER_OPEN_ACCESS_KEY"
SPRINGER_META_API_BASE = "https://api.springernature.com/meta/v2/json"
SPRINGER_META_API_KEY_ENV = "SPRINGER_META_API_KEY"
SPRINGER_API_BASE = SPRINGER_OPEN_ACCESS_API_BASE

# 各出版社全文接口模板；默认直接走 DOI 域名。
ACS_FETCH_URL_TEMPLATE = "https://doi.org/{doi}"
WILEY_FETCH_URL_TEMPLATE = "https://doi.org/{doi}"
RSC_FETCH_URL_TEMPLATE = "https://doi.org/{doi}"
# Sci-Hub 兜底镜像；按顺序逐个尝试，可根据可达性增删。
SCI_HUB_BASE_URLS = [
    "https://sci-hub.se",
    "https://sci-hub.ru",
    "https://sci-hub.st",
]

# 可选：显式指定 metadata_fetcher 的调用顺序；留空时遍历全部可用 provider。
METADATA_PROVIDERS = None
# 示例：将 Provider 限制为 Springer + PubMed
# METADATA_PROVIDERS = ["springer", "pubmed"]
# 自定义去重优先级；越靠前权重越高，未提供时与调用顺序一致。
METADATA_PROVIDER_PREFERENCE = ["elsevier", "springer", "pubmed", "crossref", "openalex", "arxiv"]
# Provider 之间的节流间隔（秒）；出现 API 429 时可临时调大。
METADATA_PROVIDER_SLEEP_SECONDS = 0.0
# 以下参数用于约束各外部 Provider 的分页、条数与节流策略；必要时单独调小做冒烟测试。
CROSSREF_REQUEST_SLEEP_SECONDS = 0.2
CROSSREF_ROWS = 50
CROSSREF_MAX_RESULTS = 200
OPENALEX_PER_PAGE = 50
OPENALEX_MAX_RESULTS = 200
OPENALEX_REQUEST_SLEEP_SECONDS = 0.2
ARXIV_PAGE_SIZE = 50
ARXIV_MAX_RESULTS = 200
ARXIV_REQUEST_SLEEP_SECONDS = 0.2
PUBMED_BATCH_SIZE = 100
PUBMED_MAX_RESULTS = 200
PUBMED_REQUEST_SLEEP_SECONDS = 0.34
SPRINGER_META_PAGE_SIZE = 50
SPRINGER_META_MAX_RESULTS = 200
SPRINGER_META_REQUEST_SLEEP_SECONDS = 0.2

# ---------- 文献解析配置 ----------
# 文献解析器默认从 ASSETS2 读取原始 XML/HTML，并把结构化块写入 ASSETS3。
XML_SOURCE_DIR = ASSETS2_DIR
BLOCKS_OUTPUT_DIR = ASSETS3_DIR
# 控制是否在 JSON 中保留图表 HTML/Base64 及可解析的图片 Base64，关闭可显著减小体积。
TRANSER_EMBED_TABLE_FIGURE_BASE64 = True
TRANSER_OUTPUT_FORMAT = "json"

# ---------- LLM 抽取日志 ----------
LLM_EXTRACTION_LOG_PATH = PIPELINE_LOG_PATH

# ---------- PDF OCR 配置 ----------
# OCR_ENGINE: auto/tesseract/paddle/pypdf2
OCR_ENGINE = "auto"
# auto 模式的尝试顺序
OCR_ENGINE_PRIORITY = ["paddle", "easyocr", "rapidocr", "tesseract", "pypdf2"]
OCR_LANG = "eng"
OCR_DPI = 300
# 预处理选项：none/grayscale/binarize/sharpen
OCR_PREPROCESS = "none"
# Tesseract 额外参数（可选）
OCR_TESSERACT_CONFIG = ""
# EasyOCR 相关选项
OCR_EASYOCR_LANGS = ["en"]
OCR_EASYOCR_GPU = False
# PaddleOCR 相关选项
OCR_PADDLE_LANG = "en"
OCR_PADDLE_USE_ANGLE_CLS = True
OCR_PADDLE_USE_GPU = False

# ---------- LLM 信息抽取输出路径 ----------
# LLM 抽取后的最终数据集（CSV）；供下游数据分析或建模使用。
LLM_EXTRACTION_OUTPUT_PATH = ASSETS4_DIR / "extracted_tap_kinetics_issues.csv"

# ---------- LLM 摘要筛选配置 ----------
# 支持多家 LLM，默认沿用 OpenAI 兼容接口
METADATA_FILTER_PROVIDER = "openai"
METADATA_FILTER_MODEL = "gpt-5-mini"
METADATA_FILTER_BASE_URL = None
METADATA_FILTER_CHAT_PATH = None
METADATA_FILTER_API_KEY_ENV = None
METADATA_FILTER_API_KEY_HEADER = None
METADATA_FILTER_API_KEY_PREFIX = None
METADATA_FILTER_TEMPERATURE = 0.0
METADATA_FILTER_TIMEOUT = 60
METADATA_FILTER_SLEEP_SECONDS = 1.0

# ---------- LLM 摘要筛选提示词 ----------
METADATA_FILTER_SYSTEM_PROMPT = (
    "你是一名催化文献分析助手，负责判断摘要是否满足筛选条件："
    "1) 明确涉及能源小分子催化反应；"
    "2) 指出存在未解决的基元反应动力学/机理问题；"
    "3) 摘要中至少能推断出具体反应体系或反应类型。"
    "请只回答 YES 或 NO。"
)
METADATA_FILTER_USER_PROMPT_TEMPLATE = (
    "判断以下摘要是否满足筛选条件：\n"
    "- 能源小分子催化反应；\n"
    "- 指出未解决的基元反应动力学/机理问题；\n"
    "- 可推断具体反应体系或反应类型。\n"
    "只回答 YES 或 NO。\n"
    "摘要：{abstract}"
)

# ---------- 关键词配置 ----------
# KEYWORD_GROUPS 决定元数据筛查/抽取阶段要重点关注的术语及其语义角色。
# 每个分组的元数据含义：
#   - keywords: 该语义类别下的候选词表
#   - roles: 额外标签，供下游组件区分用途
#   - required: True 时该分组必须命中至少一个关键词才能判定有效
KEYWORD_GROUPS = OrderedDict(
    [
        (
            "catalysis",
            {
                "keywords": [
                    "catalysis",
                    "catalytic",
                    "heterogeneous catalysis",
                    "homogeneous catalysis",
                    "electrocatalysis",
                    "photocatalysis",
                    "thermal catalysis",
                    "catalyst",
                    "active site",
                    "surface reaction",
                    "adsorption",
                    "desorption",
                    "surface intermediate",
                ],
                "roles": ["domain"],
            },
        ),
        (
            "small_molecules",
            {
                "keywords": [
                    "CO",
                    "CO2",
                    "CH4",
                    "H2",
                    "H2O",
                    "NH3",
                    "N2",
                    "NO",
                    "NOx",
                    "N2O",
                    "O2",
                    "C1",
                    "syngas",
                    "water-gas shift",
                    "methanation",
                    "CO oxidation",
                    "CO2 reduction",
                    "ammonia synthesis",
                    "methane activation",
                ],
                "roles": ["reactant"],
            },
        ),
        (
            "kinetics_issue",
            {
                "keywords": [
                    "elementary step",
                    "elementary reaction",
                    "microkinetic",
                    "kinetic model",
                    "rate-determining",
                    "rate limiting",
                    "activation barrier",
                    "reaction mechanism",
                    "pathway",
                    "intermediate",
                    "coverage",
                    "unresolved",
                    "not understood",
                    "poorly understood",
                    "open question",
                    "knowledge gap",
                    "controversy",
                    "unknown",
                ],
                "roles": ["issue"],
                "required": True,
            },
        ),
        (
            "tap_method",
            {
                "keywords": [
                    "temporal analysis of products",
                    "TAP",
                    "pulse-response",
                    "transient kinetic",
                    "transient response",
                    "isotopic transient",
                    "SSITKA",
                    "pump-probe",
                    "molecular beam",
                ],
                "roles": ["method"],
            },
        ),
        (
            "reaction_terms",
            {
                "keywords": [
                    "oxidation",
                    "reduction",
                    "hydrogenation",
                    "dehydrogenation",
                    "reforming",
                    "splitting",
                    "synthesis",
                    "conversion",
                ],
                "roles": ["reaction"],
            },
        ),
    ]
)

# 辅助常量：用于快速获取分组顺序、必需分组列表及全部关键词集合。
KEYWORD_GROUP_ORDER = list(KEYWORD_GROUPS.keys())
KEYWORD_REQUIRED_GROUPS = [
    name for name, cfg in KEYWORD_GROUPS.items() if cfg.get("required")
]
KEYWORD_ALL_TERMS = [
    term for cfg in KEYWORD_GROUPS.values() for term in cfg.get("keywords", [])
]

# ---------- 模型供应商配置 ----------
# 在 bensci/extracter_tools/providers.py 注册的 Provider key；可通过 CLI 参数覆盖。
# （示例：openai、chatanywhere、deepseek、dashscope 等。）
LLM_EXTRACTION_PROVIDER = "chatanywhere"
LLM_EXTRACTION_MODEL = "gpt-5.1"            # 默认模型名称；CLI 未传入时使用
LLM_EXTRACTION_BASE_URL = "https://api.chatanywhere.tech/v1"  # 接口根地址
LLM_EXTRACTION_CHAT_PATH = "/chat/completions"  # 聊天/补全端点
LLM_EXTRACTION_API_KEY_ENV = "CHAT_ANYWHERE_API_KEY"  # 存放 API Key 的环境变量名

LLM_EXTRACTION_API_KEY_HEADER = None        # 自定义 Header 名；None 表示使用 Authorization
LLM_EXTRACTION_API_KEY_PREFIX = None        # Header 前缀；None 表示默认 Bearer
LLM_EXTRACTION_BLOCK_LIMIT = None           # 抽取时最多使用的块数（None 表示不限制）
LLM_EXTRACTION_CHAR_LIMIT = None            # 抽取时候选片段文本字符上限（None 表示不限制）
LLM_EXTRACTION_TIMEOUT = 120  # LLM 请求整体超时时间（秒）
LLM_EXTRACTION_TASK_PROMPT = ""  # 追加的任务说明（自然语言）

# ---------- LLM 提示词预设 ----------
LLM_PROMPTS = {
    "extraction": {
        "system_prompt": (
            "你是一名严谨的催化动力学信息抽取助手，专注于能源小分子反应。"
            "请识别文献中指出的未解决基元反应动力学问题，并判断是否适合用 "
            "TAP（Temporal Analysis of Products）来研究。"
            "输出必须严格遵循 JSON 结构，字段顺序应符合给定模板。"
            "任何缺失信息请标记为 \"未提及\"，切勿编造数据。"
        ),
        "user_prompt_template": (
            "请阅读以下文献元数据与节选片段，提取与能源小分子催化动力学相关的"
            "结构化信息，字段说明如下：\n{output_template}\n\n"
            "请输出 JSON 数组，每个元素对应一条记录。\n"
            "元数据：\n{metadata}\n\n"
            "候选片段 (按重要性排序)：\n{blocks}\n"
        ),
        "output_template": OrderedDict(
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
        ),
    },
    "metadata_filter": {
        "system_prompt": METADATA_FILTER_SYSTEM_PROMPT,
        "user_prompt_template": METADATA_FILTER_USER_PROMPT_TEMPLATE,
    },
}

# ---------- 可选：覆盖配置（JSON 文件） ----------
# 允许通过 config.override.json 或环境变量 BENSCI_CONFIG_PATH 提供覆盖值，
# 以便在不修改源码的情况下定制项目配置。
import json
import os

CONFIG_OVERRIDE_PATH = Path(
    os.getenv("BENSCI_CONFIG_PATH", PROJECT_ROOT / "config.override.json")
)


def _coerce_override_value(name: str, value):
    current = globals().get(name)
    if isinstance(current, Path):
        return Path(value)
    if isinstance(current, tuple) and isinstance(value, list):
        return tuple(value)
    if isinstance(current, set) and isinstance(value, list):
        return set(value)
    return value


def _apply_overrides() -> None:
    path = Path(CONFIG_OVERRIDE_PATH) if CONFIG_OVERRIDE_PATH else None
    if not path or not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(data, dict):
        return

    for key, value in data.items():
        if value is None:
            continue
        try:
            globals()[key] = _coerce_override_value(key, value)
        except Exception:
            globals()[key] = value

    if "KEYWORD_GROUPS" in data:
        globals()["KEYWORD_GROUP_ORDER"] = list(KEYWORD_GROUPS.keys())
        globals()["KEYWORD_REQUIRED_GROUPS"] = [
            name for name, cfg in KEYWORD_GROUPS.items() if cfg.get("required")
        ]
        globals()["KEYWORD_ALL_TERMS"] = [
            term for cfg in KEYWORD_GROUPS.values() for term in cfg.get("keywords", [])
        ]


_apply_overrides()
