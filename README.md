# Bensci 文献挖掘与结构化抽取工具

Bensci 是一个面向催化领域文献的自动化处理流水线，覆盖：
元数据聚合 → 摘要筛选 → 全文下载 → 格式转化统一 → LLM 抽取建表。

本仓库提供：
- 完整的可交互 notebook 手册（`notebooks/`）
- 终端一键运行脚本（`run.sh`）
- 可视化 UI（`ui/`）
- 可覆盖的配置体系（`config.override.json`）

---

## 快速开始

### 1) 创建环境并安装依赖

```bash
conda create -n bensci python=3.11
conda activate bensci
pip install -r requirements.txt
```

如需 OCR（PDF/扫描件解析），再安装：

```bash
pip install -r requirements-ocr.txt
```

系统级依赖（按需）：
- macOS: `brew install tesseract poppler`
- Ubuntu: `sudo apt-get install -y tesseract-ocr poppler-utils`

### 2) 配置 API Key（可选但推荐）

在项目根目录创建 `.env`：

```text
ELSEVIER_API_KEY=your_key
SPRINGER_OPEN_ACCESS_KEY=your_key
SPRINGER_META_API_KEY=your_key
ACS_API_KEY=your_key
OPENAI_API_KEY=your_key
CHAT_ANYWHERE_API_KEY=your_key
```

### 3) 一键运行

```bash
bash run.sh
```

你会看到交互式菜单：
- 1) 打开前端 UI
- 2) 运行单个任务
- 3) 退出项目

---

## 项目目录结构

```text
Bensci/
  bensci/                  # 核心代码
  ui/                      # 可视化界面
  notebooks/               # 交互式手册
  data_resourse/
    assets1/               # 元数据 & 初筛
    assets2/               # 全文下载
    assets3/               # 解析后的结构化块
    assets4/               # LLM 抽取结果
    logs/                  # 日志
  run.sh                   # 一键运行脚本
  requirements.txt
  requirements-ocr.txt
```

---

## 推荐使用路径（手册）

从 `notebooks/00_overview_and_flow.ipynb` 开始，按顺序阅读：
- `00_overview_and_flow.ipynb`
- `01_environment_setup.ipynb`
- `02_config_and_api_keys.ipynb`
- `03_run_modes_cli_ui.ipynb`
- `04_metadata_fetch.ipynb`
- `05_filter_and_download.ipynb`
- `06_convert_transer.ipynb`
- `07_llm_extraction.ipynb`
- `08_troubleshooting.ipynb`

每个 notebook 都包含可直接运行的代码单元（默认 `RUN=False`，需要执行时改为 `True`）。

---

## 流水线概览

1. **元数据聚合**：从 Elsevier / Springer / Crossref / OpenAlex / arXiv / PubMed 获取文献元数据。
2. **摘要筛选**：用 LLM 判断是否满足筛选条件。
3. **全文下载**：根据 DOI 下载 XML/HTML/PDF。
4. **格式转化统一**：解析为 JSON/Markdown block。
5. **LLM 抽取建表**：输出结构化 CSV。

默认输出位置：
- 元数据 CSV：`data_resourse/assets1/elsevier_metadata.csv`
- 筛选后 CSV：`data_resourse/assets1/elsevier_metadata_filtered.csv`
- 下载全文：`data_resourse/assets2/`
- 解析后 JSON/MD：`data_resourse/assets3/`
- LLM 抽取 CSV：`data_resourse/assets4/extracted_tap_kinetics_issues.csv`

---

## 常用命令（CLI）

```bash
# 1) 元数据聚合
python -m bensci.metadata_fetcher

# 2) 摘要筛选
python -m bensci.metadata_filter_utils

# 3) 下载全文
python -m bensci.literature_fetcher

# 4) 格式转化统一
python -m bensci.literature_transer --input data_resourse/assets2 --output data_resourse/assets3 --output-format json

# 5) LLM 抽取建表
python -m bensci.llm_info_extractor
```

---

## 配置覆盖（推荐方式）

不建议直接修改源码中的 `config.py`，可以新建 `config.override.json` 覆盖配置。
示例：

```json
{
  "METADATA_MAX_RESULTS": 50,
  "METADATA_PROVIDERS": ["elsevier", "springer", "openalex"],
  "METADATA_CSV_PATH": "data_resourse/assets1/metadata.csv",
  "FILTERED_METADATA_CSV_PATH": "data_resourse/assets1/metadata_filtered.csv",
  "TRANSER_OUTPUT_FORMAT": "json",
  "LLM_EXTRACTION_PROVIDER": "openai",
  "LLM_EXTRACTION_MODEL": "gpt-5-mini"
}
```

---

## UI 说明

- 启动方式：`bash run.sh` → 选择菜单 `1`
- 默认端口：`7860`
- UI 日志：`data_resourse/logs/bensci_ui.log`

---

## 常见问题（简要）

- **401/403**：检查 `.env` 中 API Key
- **429/Rate Limit**：减少 `METADATA_MAX_RESULTS`，增大 sleep
- **没有筛选结果**：可能 query 太严格或 LLM 判断为 NO
- **解析失败/OCR 报错**：检查系统依赖与 OCR 包

完整排查请看：`notebooks/08_troubleshooting.ipynb`

---

## 许可与引用

如需添加 License 或引用格式，请在此补充。
