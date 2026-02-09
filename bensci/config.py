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
    "(zirconia OR \"zirconium oxide\" OR ZrO2 OR \"ZrO\\u2082\" OR \"ZrO2-based\") AND "
    "(propane AND (dehydrogenation OR \"direct dehydrogenation\" OR PDH)) AND "
    "(propylene OR propene) "
    ")"
)

# `metadata_fetcher` 的兜底检索词，未传入 query 或单个 provider 未定义专用语句时使用。
METADATA_DEFAULT_QUERY = (
    "catalysis AND (kinetic* OR microkinetic OR \"elementary step\" OR "
    "\"rate-determining\" OR mechanism) AND "
    "(CO OR CO2 OR CH4 OR H2 OR NH3 OR N2 OR \"small molecule\" OR C1)"
)

# 聚合器写出 CSV 之前的上限；调试阶段可以暂时调成 50/100 以减少调用和写盘量。
METADATA_MAX_RESULTS = 1000

# 可为每个 Provider 定义独立的抓取上限（未配置则沿用 METADATA_MAX_RESULTS）。
# 例如：{"elsevier": 80, "springer": 60}
METADATA_PROVIDER_MAX_RESULTS = {"elsevier": 1000, "springer": 1000, "crossref": 1000,"openalex": 1000, "arxiv": 1000, "pubmed": 1000}

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
SCOPUS_MAX_RESULTS = 1000  # 单轮扫描的最大返回量
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
    "https://sci-hub.ru",
    "https://sci-hub.st",
    "https://sci-hub.sg",
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
CROSSREF_MAX_RESULTS = 2000
OPENALEX_PER_PAGE = 50
OPENALEX_MAX_RESULTS = 2000
OPENALEX_REQUEST_SLEEP_SECONDS = 0.2
ARXIV_PAGE_SIZE = 50
ARXIV_MAX_RESULTS = 2000
ARXIV_REQUEST_SLEEP_SECONDS = 0.2
PUBMED_BATCH_SIZE = 100
PUBMED_MAX_RESULTS = 2000
PUBMED_REQUEST_SLEEP_SECONDS = 0.34
SPRINGER_META_PAGE_SIZE = 50
SPRINGER_META_MAX_RESULTS = 2000
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
            "你是一名严谨的催化（丙烷直接脱氢 PDH）信息抽取助手，重点关注氧化锆（ZrO2）相关催化剂。"
            "你的任务是从给定的文献元数据与节选片段中，抽取可核查的结构化信息："
            "（1）催化机理：反应路径与失活路径；（2）催化剂制备方法；（3）活性位归属；"
            "（4）动力学过程解释（RDS、表观活化能、速率表达、微观机理等）；"
            "（5）TAP（Temporal Analysis of Products）可行性与可执行的实验 idea；"
            "（6）表征结果（XRD/BET/显微图像等的“结论性描述”）；"
            "（7）仍未解决的问题；（8）英文摘要原文与中文翻译；"
            "（9）反应性能与条件（转化率/选择性/产率/STY/丙烯生成速率、温度、空速、进料组成等）；"
            "（10）期刊影响因子、通讯作者与机构介绍（仅限元数据/片段中明确给出的内容）。"
            "输出必须严格遵循 JSON 结构与字段顺序。"
            "任何缺失信息一律写 \"未提及\"，切勿编造、推测、补写影响因子或机构介绍。"
            "引用证据时，evidence_snippets 必须是原文逐句摘录（可多句），便于人工复核。"
        ),
        "user_prompt_template": (
            "请阅读以下文献元数据与节选片段，抽取与“ZrO2/氧化锆 催化 丙烷直接脱氢制丙烯（PDH）”相关的结构化信息。"
            "字段说明如下：\n{output_template}\n\n"
            "请输出 JSON 数组，每个元素对应一篇文献（或同一文献中一个清晰的催化体系/催化剂版本）。\n\n"
            "元数据：\n{metadata}\n\n"
            "候选片段（按重要性排序，带 block 编号）：\n{blocks}\n"
        ),
        "output_template": OrderedDict(
            [
                # --- 基本信息 ---
                ("article_title", "文献标题"),
                ("doi", "文献 DOI"),
                ("year", "发表年份（未提及则填未提及）"),
                ("journal", "期刊名称"),
                ("document_type", "文献类型（article/review等，未提及则填未提及）"),

                # --- 摘要（你要求的“英文原文 + 中文翻译”）---
                ("abstract_en", "英文摘要原文（必须原文；若未提供则未提及）"),
                ("abstract_zh", "中文摘要翻译（基于 abstract_en 翻译；若 abstract_en 未提及则此项也写未提及）"),

                # --- 反应体系与条件（尽量结构化）---
                ("reaction_name", "反应名称（如 propane dehydrogenation, PDH）"),
                ("reaction_system", "反应体系描述（丙烷→丙烯；是否含H2、惰性气等）"),
                ("reactants", "反应物/进料组分（逐项列出，如 C3H8, H2, N2, Ar 等）"),
                ("products", "主要产物与副产物（丙烯/氢气/裂解产物/积碳相关等）"),
                ("temperature_C", "温度范围（°C，若多条件可写列表或区间文本）"),
                ("pressure", "压力（如 1 atm / bar；未提及则未提及）"),
                ("space_velocity", "空速（WHSV/GHSV/接触时间等，带单位）"),
                ("feed_composition", "进料配比/浓度（如 C3H8% 或 C3H8:H2:N2）"),
                ("reactor_type", "反应器类型（固定床/微反/流动等；未提及则未提及）"),
                ("time_on_stream", "TOS/运行时长与稳定性测试时长（未提及则未提及）"),

                # --- 催化剂信息：材料、形态、制备 ---
                ("catalyst", "催化剂组成/材料（强调 ZrO2；掺杂/负载金属也要写出）"),
                ("catalyst_form", "形态/载体/结构（纳米/多晶/单斜-四方相/负载体等）"),
                ("preparation_method", "制备方法（溶胶凝胶/沉淀/浸渍/水热/焙烧流程等）"),
                ("pretreatment_activation", "预处理/活化条件（还原/氧化/焙烧/气氛等）"),

                # --- 表征结果（写“结论性信息”，不要编数据）---
                ("characterization_xrd", "XRD 关键信息（相结构、晶相变化、结晶度趋势等）"),
                ("characterization_bet", "BET/孔结构信息（比表面积趋势、孔径分布要点等）"),
                ("characterization_microscopy", "显微图像（SEM/TEM/HAADF等）结论要点"),
                ("characterization_surface_chemistry", "表面化学（XPS/TPD/TPR/DRIFTS等）要点"),
                ("physicochemical_properties_summary", "催化剂物理化学性质总结（从表征归纳，不要编数值）"),

                # --- 活性位与机理（反应 + 失活）---
                ("active_site_assignment", "活性位归属（如 Zr4+-O2- 对/氧空位/酸碱位/界面位等）"),
                ("reaction_mechanism", "催化反应机理要点（逐条写明关键基元步骤或路径）"),
                ("deactivation_mechanism", "失活机理（积碳/烧结/相变/毒化等）"),
                ("regeneration", "再生策略与效果（若文中提及）"),

                # --- 动力学解释 ---
                ("kinetic_model_or_rate_expression", "动力学模型/速率表达式/反应级数（若有）"),
                ("rate_determining_step", "速控步（RDS）或关键限制环节（若文中明确）"),
                ("apparent_activation_energy", "表观活化能 Ea（若文中明确给出，含单位）"),
                ("microkinetic_discussion", "微观动力学/DFT-微观模型讨论要点（若有）"),
                ("kinetic_interpretation_summary", "作者对动力学过程的解释总结（用原文可核查信息组织）"),

                # --- 反应性能（你关心的转化率/选择性/产率/速率等）---
                ("performance_conversion", "转化率（含条件/范围；未提及则未提及）"),
                ("performance_selectivity_propylene", "丙烯选择性（含条件/范围）"),
                ("performance_yield_propylene", "丙烯产率（含条件/范围）"),
                ("performance_sty_or_rate", "STY/TOF/丙烯生成速率/单位质量速率（含单位与条件）"),
                ("performance_stability", "稳定性（随时间变化趋势、失活速率等）"),
                ("performance_comparison_baseline", "与对照催化剂对比结论（若有）"),

                # --- TAP 相关（潜在 idea + 具体可做的实验设计）---
                ("tap_relevance", "为什么适合用 TAP（可分离吸附/表面反应/扩散/瞬态中间体等）"),
                ("suggested_tap_ideas", "TAP 潜在研究 idea（针对机理/失活/活性位）"),
                ("suggested_tap_experiments", "可执行的 TAP 实验设计（脉冲物种、同位素、温度窗口、序列脉冲等）"),
                ("tap_expected_observables", "TAP 预期可观测量与判据（时域信号、滞后、产物分布特征等）"),

                # --- 未解决问题 ---
                ("unresolved_issues", "文献明确指出/可归纳的尚未解决问题（必须有证据支撑；否则未提及）"),
                ("future_work_clues", "作者提出的未来工作线索（若有）"),

                # --- 影响因子、作者与机构（只许从提供文本中取）---
                ("journal_impact_factor", "期刊影响因子（只在元数据/片段明确给出时填写；否则未提及）"),
                ("corresponding_authors", "通讯作者（姓名列表；未提及则未提及）"),
                ("affiliations", "作者机构/单位（未提及则未提及）"),
                ("institution_profile", "相关机构组织介绍（研究领域/重点；仅限原文或元数据明确描述）"),

                # --- 证据与定位 ---
                ("evidence_snippets", "支持性原文摘录（数组；每条尽量完整句子）"),
                ("source_blocks", "证据对应的 block 编号列表（数组，如 [3,7,9]）"),
                ("confidence_score", "0-1 小数：对本条记录整体可靠性的自评（信息越多且证据越直接越高）"),
                ("verification_notes", "人工复核建议（建议回看哪些关键词/图表/补抓哪些段落）"),
            ]
        ),
    },

    # === 可选：元数据层过滤器（先筛出“ZrO2 + PDH + propylene”高度相关）===
    "metadata_filter_zro2_pdh": {
        "system_prompt": (
            "你是文献元数据筛选助手。你的目标是从给定元数据中筛选出："
            "（A）明确涉及 ZrO2/氧化锆（含掺杂/复合/负载形式）；"
            "（B）反应为丙烷直接脱氢（PDH）并以丙烯为主要目标产物；"
            "请只依据元数据字段（标题、摘要、关键词等）判断。"
            "输出 JSON，包含 keep(boolean) 与 reasons(array)。不允许编造。"
        ),
        "user_prompt_template": (
            "请基于以下元数据判断是否保留用于后续抽取：\n{metadata}\n\n"
            "输出 JSON：{"
            "\"keep\": true/false, "
            "\"reasons\": [\"...\", \"...\"]"
            "}"
        ),
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
