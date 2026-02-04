from __future__ import annotations

import importlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from flask import Flask, jsonify, render_template, request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
CONFIG_OVERRIDE_PATH = Path(
    os.getenv("BENSCI_CONFIG_PATH", PROJECT_ROOT / "config.override.json")
)

os.environ.setdefault("BENSCI_CONFIG_PATH", str(CONFIG_OVERRIDE_PATH))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bensci import config as project_config
from bensci.extracter_tools.providers import PROVIDER_PRESETS
from bensci.fetcher_tools import available_fetchers
from bensci.metadata_fetcher import PROVIDER_CLIENTS
from bensci.logging_utils import setup_file_logger

app = Flask(__name__, static_folder="static", template_folder="templates")

PIPELINE_LOG_PATH = getattr(project_config, "PIPELINE_LOG_PATH", None)
_PIPELINE_LOGGER: Optional[logging.Logger] = None


CONFIG_KEYS = [
    "METADATA_DEFAULT_QUERY",
    "METADATA_MAX_RESULTS",
    "METADATA_PROVIDERS",
    "METADATA_CSV_PATH",
    "FILTERED_METADATA_CSV_PATH",
    "ASSETS2_DIR",
    "XML_SOURCE_DIR",
    "BLOCKS_OUTPUT_DIR",
    "LLM_EXTRACTION_OUTPUT_PATH",
    "LLM_EXTRACTION_MODEL",
    "LLM_EXTRACTION_PROVIDER",
    "LLM_EXTRACTION_BASE_URL",
    "LLM_EXTRACTION_CHAT_PATH",
    "LLM_EXTRACTION_API_KEY_ENV",
    "LLM_EXTRACTION_API_KEY_HEADER",
    "LLM_EXTRACTION_API_KEY_PREFIX",
    "LLM_EXTRACTION_OUTPUT_TEMPLATE",
    "LLM_EXTRACTION_BLOCK_LIMIT",
    "LLM_EXTRACTION_CHAR_LIMIT",
    "LLM_EXTRACTION_TEMPERATURE",
    "LLM_EXTRACTION_TIMEOUT",
    "LLM_EXTRACTION_TASK_PROMPT",
    "METADATA_FILTER_PROVIDER",
    "METADATA_FILTER_MODEL",
    "METADATA_FILTER_BASE_URL",
    "METADATA_FILTER_CHAT_PATH",
    "METADATA_FILTER_API_KEY_ENV",
    "METADATA_FILTER_API_KEY_HEADER",
    "METADATA_FILTER_API_KEY_PREFIX",
    "METADATA_FILTER_TEMPERATURE",
    "METADATA_FILTER_TIMEOUT",
    "METADATA_FILTER_SLEEP_SECONDS",
    "METADATA_FILTER_SYSTEM_PROMPT",
    "METADATA_FILTER_USER_PROMPT_TEMPLATE",
    "OCR_ENGINE",
    "OCR_ENGINE_PRIORITY",
    "OCR_LANG",
    "OCR_DPI",
    "OCR_PREPROCESS",
    "OCR_TESSERACT_CONFIG",
    "OCR_EASYOCR_LANGS",
    "OCR_EASYOCR_GPU",
    "OCR_PADDLE_LANG",
    "OCR_PADDLE_USE_ANGLE_CLS",
    "OCR_PADDLE_USE_GPU",
    "TRANSER_OUTPUT_FORMAT",
]

STAGE_CONFIG_KEY = "STAGE_CONFIGS"


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _reload_project_config():
    global project_config
    project_config = importlib.reload(project_config)
    return project_config


def load_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    env: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        env[key] = value.strip()
    return env


def update_env_file(path: Path, updates: Dict[str, Optional[str]]) -> Dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    index: Dict[str, int] = {}

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            index[key] = idx

    for key, value in updates.items():
        if value is None:
            if key in index:
                lines[index[key]] = ""
            continue
        if key in index:
            lines[index[key]] = f"{key}={value}"
        else:
            lines.append(f"{key}={value}")

    final_lines = [line for line in lines if line.strip()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(final_lines) + ("\n" if final_lines else ""), encoding="utf-8")
    return load_env_file(path)


def load_override_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def load_stage_defaults(path: Path) -> Dict[str, Dict[str, Any]]:
    overrides = load_override_config(path)
    raw = overrides.get(STAGE_CONFIG_KEY) if isinstance(overrides, dict) else None
    if not isinstance(raw, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for stage, cfg in raw.items():
        if isinstance(stage, str) and isinstance(cfg, dict):
            normalized[stage] = cfg
    return normalized


def save_override_config(path: Path, overrides: Dict[str, Any]) -> None:
    if not overrides:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(overrides, ensure_ascii=True, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _base_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{PROJECT_ROOT}{os.pathsep}" + env.get("PYTHONPATH", "")
    env["BENSCI_CONFIG_PATH"] = str(CONFIG_OVERRIDE_PATH)
    if extra:
        env.update(extra)
    return env


def _get_pipeline_logger() -> logging.Logger:
    global _PIPELINE_LOGGER
    if _PIPELINE_LOGGER is None:
        _PIPELINE_LOGGER = setup_file_logger("bensci.pipeline", PIPELINE_LOG_PATH)
        _PIPELINE_LOGGER.propagate = False
    return _PIPELINE_LOGGER


def _log_pipeline(message: str, *, source: Optional[str] = None, level: int = logging.INFO) -> None:
    logger = _get_pipeline_logger()
    extra = {"source": source} if source else None
    logger.log(level, message, extra=extra)


def _infer_source(args: list[str]) -> str:
    if "-m" in args:
        idx = args.index("-m")
        if idx + 1 < len(args):
            module = args[idx + 1]
            return f"{module.split('.')[-1]}.py"
    return "unknown"


def _log_subprocess_output(result: subprocess.CompletedProcess, args: list[str], source: Optional[str]) -> None:
    if not PIPELINE_LOG_PATH:
        return
    source_name = source or _infer_source(args)
    extra = {"source": source_name}
    cmd = " ".join(args)
    _log_pipeline(f"COMMAND: {cmd}", source=source_name)
    if result.stdout:
        for line in result.stdout.splitlines():
            if line.strip():
                _get_pipeline_logger().info(line, extra=extra)
    if result.stderr:
        for line in result.stderr.splitlines():
            if line.strip():
                _get_pipeline_logger().error(line, extra=extra)


def run_subprocess(
    args: list[str], *, extra_env: Optional[Dict[str, str]] = None, source: Optional[str] = None
) -> Dict[str, Any]:
    if source:
        merged_env = dict(extra_env or {})
        merged_env["BENSCI_LOG_SOURCE"] = source
        extra_env = merged_env
    result = subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=_base_env(extra_env),
    )
    _log_subprocess_output(result, args, source)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": " ".join(args),
    }


def run_python_snippet(
    code: str, *, extra_env: Optional[Dict[str, str]] = None, source: Optional[str] = None
) -> Dict[str, Any]:
    return run_subprocess([sys.executable, "-c", code], extra_env=extra_env, source=source)


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return None


def _coerce_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        return None


def _merge_stage_params(stage: str, params: Dict[str, Any]) -> Dict[str, Any]:
    defaults = load_stage_defaults(CONFIG_OVERRIDE_PATH).get(stage, {})
    merged: Dict[str, Any] = {}
    if isinstance(defaults, dict):
        merged.update(defaults)
    if isinstance(params, dict):
        merged.update(params)
    return merged


def _run_metadata_stage(params: Dict[str, Any]) -> Dict[str, Any]:
    query = (params.get("query") or "").strip()
    max_results = params.get("max_results")
    providers = params.get("providers") or []
    output_csv = (params.get("output_csv") or "").strip()
    if isinstance(providers, str):
        providers = [p.strip() for p in providers.split(",") if p.strip()]

    max_literal = int(max_results) if str(max_results).isdigit() else 0
    provider_raw = ",".join(providers)

    code = """
import sys
from pathlib import Path
from bensci import config

query = {query}
max_results = int({max_results})
provider_raw = {provider_raw}.strip()
output_csv = {output_csv}

if output_csv:
    path = Path(output_csv)
    config.METADATA_CSV_PATH = path
    config.ASSETS1_DIR = path.parent

from bensci import metadata_fetcher

if output_csv:
    metadata_fetcher.METADATA_CSV_PATH = config.METADATA_CSV_PATH
    metadata_fetcher.ASSETS1_DIR = config.ASSETS1_DIR

if max_results <= 0:
    max_results = int(getattr(config, "METADATA_MAX_RESULTS", 200))

if provider_raw:
    cleaned = tuple(p.strip() for p in provider_raw.replace(";", ",").split(",") if p.strip())
    if cleaned:
        config.METADATA_PROVIDERS = cleaned
        config.METADATA_PROVIDER_PREFERENCE = cleaned

records = metadata_fetcher.fetch_metadata(query=query, max_results=max_results)
if not records:
    print("未检索到任何记录，请检查查询条件或接口状态。")
    sys.exit(1)

metadata_fetcher.write_metadata_csv(records)
print("metadata_saved=", config.METADATA_CSV_PATH)
""".format(
        query=json.dumps(query),
        max_results=max_literal,
        provider_raw=json.dumps(provider_raw),
        output_csv=json.dumps(output_csv),
    )

    return run_python_snippet(code, source="metadata_fetcher.py")


def _run_filter_stage(params: Dict[str, Any]) -> Dict[str, Any]:
    provider = (params.get("provider") or "").strip()
    model = (params.get("model") or "").strip()
    base_url = (params.get("base_url") or "").strip()
    chat_path = (params.get("chat_path") or "").strip()
    api_key_env = (params.get("api_key_env") or "").strip()
    api_key_header = (params.get("api_key_header") or "").strip()
    api_key_prefix = params.get("api_key_prefix")
    if api_key_prefix is not None:
        api_key_prefix = str(api_key_prefix).strip() or None
    temperature = _coerce_float(params.get("temperature"))
    timeout = _coerce_int(params.get("timeout"))
    sleep = _coerce_float(params.get("sleep"))
    system_prompt = (params.get("system_prompt") or "").strip()
    user_prompt_template = (params.get("user_prompt_template") or "").strip()
    input_csv = (params.get("input_csv") or "").strip()
    output_csv = (params.get("output_csv") or "").strip()

    code = """
from pathlib import Path
from bensci import metadata_filter_utils as mf

input_csv = {input_csv}
output_csv = {output_csv}

input_csv = (input_csv or "").strip()
output_csv = (output_csv or "").strip()

if input_csv:
    mf.SOURCE_CSV = Path(input_csv)
if output_csv:
    mf.TARGET_CSV = Path(output_csv)
if output_csv:
    mf.ASSETS1_DIR = Path(output_csv).parent
elif input_csv:
    mf.ASSETS1_DIR = Path(input_csv).parent

provider = {provider}
model = {model}
base_url = {base_url}
chat_path = {chat_path}
api_key_env = {api_key_env}
api_key_header = {api_key_header}
api_key_prefix = {api_key_prefix}
temperature = {temperature}
timeout = {timeout}
sleep_seconds = {sleep_seconds}
system_prompt = {system_prompt}
user_prompt_template = {user_prompt_template}

system_prompt = (system_prompt or "").strip() or None
user_prompt_template = (user_prompt_template or "").strip() or None

provider = (provider or "").strip() or mf.DEFAULT_PROVIDER
model = (model or "").strip() or mf.DEFAULT_MODEL
base_url = (base_url or "").strip() or mf.DEFAULT_BASE_URL
chat_path = (chat_path or "").strip() or mf.DEFAULT_CHAT_PATH
api_key_env = (api_key_env or "").strip() or mf.DEFAULT_API_KEY_ENV
api_key_header = (api_key_header or "").strip() or mf.DEFAULT_API_KEY_HEADER
api_key_prefix = (api_key_prefix or "").strip() or mf.DEFAULT_API_KEY_PREFIX

if temperature is None:
    temperature = mf.DEFAULT_TEMPERATURE
if timeout is None:
    timeout = mf.DEFAULT_TIMEOUT
if sleep_seconds is None:
    sleep_seconds = mf.DEFAULT_SLEEP_SECONDS

count = mf.filter_metadata(
    provider=provider,
    model=model,
    base_url=base_url,
    chat_path=chat_path,
    api_key_env=api_key_env,
    api_key_header=api_key_header,
    api_key_prefix=api_key_prefix,
    temperature=temperature,
    timeout=timeout,
    sleep_seconds=sleep_seconds,
    system_prompt=system_prompt,
    user_prompt_template=user_prompt_template,
)
print("filter_passed=", count)
""".format(
        input_csv=repr(input_csv),
        output_csv=repr(output_csv),
        provider=repr(provider),
        model=repr(model),
        base_url=repr(base_url),
        chat_path=repr(chat_path),
        api_key_env=repr(api_key_env),
        api_key_header=repr(api_key_header),
        api_key_prefix=repr(api_key_prefix),
        temperature=repr(temperature),
        timeout=repr(timeout),
        sleep_seconds=repr(sleep),
        system_prompt=repr(system_prompt),
        user_prompt_template=repr(user_prompt_template),
    )

    return run_python_snippet(code, source="metadata_filter_utils.py")


def _run_download_stage(params: Dict[str, Any]) -> Dict[str, Any]:
    provider = (params.get("provider") or "auto").strip() or "auto"
    doi = (params.get("doi") or "").strip()
    input_csv = (params.get("input_csv") or "").strip()
    output_dir = (params.get("output_dir") or "").strip()

    cmd = [sys.executable, "-m", "bensci.literature_fetcher"]
    if input_csv:
        cmd += ["--input", input_csv]
    if output_dir:
        cmd += ["--output", output_dir]
    if provider:
        cmd += ["--provider", provider]
    if doi:
        cmd += ["--doi", doi]
    return run_subprocess(cmd, source="literature_fetcher.py")


def _run_convert_stage(params: Dict[str, Any]) -> Dict[str, Any]:
    input_path = (params.get("input_path") or "").strip()
    output_dir = (params.get("output_dir") or "").strip()
    parser = (params.get("parser") or "").strip()
    output_format = (params.get("output_format") or "").strip()
    ocr_engine = (params.get("ocr_engine") or "").strip()
    ocr_lang = (params.get("ocr_lang") or "").strip()
    ocr_dpi = params.get("ocr_dpi")
    ocr_preprocess = (params.get("ocr_preprocess") or "").strip()
    ocr_tesseract_config = (params.get("ocr_tesseract_config") or "").strip()
    ocr_easyocr_langs = (params.get("ocr_easyocr_langs") or "").strip()
    ocr_easyocr_gpu = (params.get("ocr_easyocr_gpu") or "").strip()
    ocr_paddle_lang = (params.get("ocr_paddle_lang") or "").strip()
    ocr_paddle_use_angle_cls = (params.get("ocr_paddle_use_angle_cls") or "").strip()
    ocr_paddle_use_gpu = (params.get("ocr_paddle_use_gpu") or "").strip()

    cmd = [sys.executable, "-m", "bensci.literature_transer"]
    if input_path:
        cmd += ["--input", input_path]
    if output_dir:
        cmd += ["--output", output_dir]
    if parser:
        cmd += ["--parser", parser]
    if output_format:
        cmd += ["--output-format", output_format]
    if ocr_engine:
        cmd += ["--ocr-engine", ocr_engine]
    if ocr_lang:
        cmd += ["--ocr-lang", ocr_lang]
    if str(ocr_dpi).isdigit():
        cmd += ["--ocr-dpi", str(ocr_dpi)]
    if ocr_preprocess:
        cmd += ["--ocr-preprocess", ocr_preprocess]
    if ocr_tesseract_config:
        cmd += ["--ocr-tesseract-config", ocr_tesseract_config]
    if ocr_easyocr_langs:
        cmd += ["--ocr-easyocr-langs", ocr_easyocr_langs]
    if ocr_easyocr_gpu in {"true", "false"}:
        cmd += ["--ocr-easyocr-gpu", ocr_easyocr_gpu]
    if ocr_paddle_lang:
        cmd += ["--ocr-paddle-lang", ocr_paddle_lang]
    if ocr_paddle_use_angle_cls in {"true", "false"}:
        cmd += ["--ocr-paddle-use-angle-cls", ocr_paddle_use_angle_cls]
    if ocr_paddle_use_gpu in {"true", "false"}:
        cmd += ["--ocr-paddle-use-gpu", ocr_paddle_use_gpu]
    return run_subprocess(cmd, source="literature_transer.py")


def _run_llm_stage(params: Dict[str, Any]) -> Dict[str, Any]:
    input_path = (params.get("input_path") or "").strip()
    output_path = (params.get("output_path") or "").strip()
    provider = (params.get("provider") or "").strip()
    model = (params.get("model") or "").strip()
    base_url = (params.get("base_url") or "").strip()
    chat_path = (params.get("chat_path") or "").strip()
    api_key_env = (params.get("api_key_env") or "").strip()
    api_key_header = (params.get("api_key_header") or "").strip()
    api_key_prefix = params.get("api_key_prefix")
    block_limit = params.get("block_limit")
    char_limit = params.get("char_limit")
    temperature = params.get("temperature")
    timeout = params.get("timeout")
    task = (params.get("task") or "").strip()
    output_template = (params.get("output_template") or "").strip()
    system_prompt = (params.get("system_prompt") or "").strip()
    user_prompt_template = (params.get("user_prompt_template") or "").strip()
    auto_schema = params.get("auto_schema")
    schema_sample_size = params.get("schema_sample_size")
    schema_max_fields = params.get("schema_max_fields")
    schema_output = (params.get("schema_output") or "").strip()

    cmd = [sys.executable, "-m", "bensci.llm_info_extractor"]
    if input_path:
        cmd += ["--input", input_path]
    if output_path:
        cmd += ["--output", output_path]
    if system_prompt:
        cmd += ["--system-prompt", system_prompt]
    if user_prompt_template:
        cmd += ["--user-prompt-template", user_prompt_template]
    if task:
        cmd += ["--task", task]
    if output_template:
        cmd += ["--output-template", output_template]
    if str(auto_schema).lower() in {"true", "1", "yes", "y"}:
        cmd += ["--auto-schema"]
    if str(schema_sample_size).isdigit():
        cmd += ["--schema-sample-size", str(schema_sample_size)]
    if str(schema_max_fields).isdigit():
        cmd += ["--schema-max-fields", str(schema_max_fields)]
    if schema_output:
        cmd += ["--schema-output", schema_output]
    if model:
        cmd += ["--model", model]
    if provider:
        cmd += ["--provider", provider]
    if base_url:
        cmd += ["--base-url", base_url]
    if chat_path:
        cmd += ["--chat-path", chat_path]
    if api_key_env:
        cmd += ["--api-key-env", api_key_env]
    if api_key_header:
        cmd += ["--api-key-header", api_key_header]
    if api_key_prefix is not None and str(api_key_prefix).strip() != "":
        cmd += ["--api-key-prefix", str(api_key_prefix)]
    if str(block_limit).isdigit():
        cmd += ["--block-limit", str(block_limit)]
    if str(char_limit).isdigit():
        cmd += ["--char-limit", str(char_limit)]
    if temperature is not None and str(temperature).strip() != "":
        cmd += ["--temperature", str(temperature)]
    if str(timeout).isdigit():
        cmd += ["--timeout", str(timeout)]

    return run_subprocess(cmd, source="llm_info_extractor.py")


@dataclass(frozen=True)
class StageSpec:
    key: str
    label: str
    source: str
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]


STAGES = {
    "metadata": StageSpec(
        key="metadata",
        label="元数据聚合",
        source="metadata_fetcher.py",
        handler=_run_metadata_stage,
    ),
    "filter": StageSpec(
        key="filter",
        label="摘要筛选",
        source="metadata_filter_utils.py",
        handler=_run_filter_stage,
    ),
    "download": StageSpec(
        key="download",
        label="下载全文",
        source="literature_fetcher.py",
        handler=_run_download_stage,
    ),
    "convert": StageSpec(
        key="convert",
        label="格式转化统一",
        source="literature_transer.py",
        handler=_run_convert_stage,
    ),
    "llm": StageSpec(
        key="llm",
        label="LLM 抽取建表",
        source="llm_info_extractor.py",
        handler=_run_llm_stage,
    ),
}


def execute_stage(stage: str, params: Dict[str, Any]) -> Dict[str, Any]:
    spec = STAGES.get(stage)
    if not spec:
        return {"ok": False, "error": f"unknown stage: {stage}"}
    merged = _merge_stage_params(stage, params)
    _log_pipeline(f"开始执行 {spec.label}", source=spec.source)
    try:
        result = spec.handler(merged)
    except Exception as exc:  # noqa: BLE001
        _log_pipeline(
            f"执行 {spec.label} 失败: {exc}",
            source=spec.source,
            level=logging.ERROR,
        )
        return {"ok": False, "error": str(exc)}
    _log_pipeline(
        f"完成 {spec.label} -> {'OK' if result.get('ok') else 'FAILED'}",
        source=spec.source,
        level=logging.INFO if result.get("ok") else logging.ERROR,
    )
    return result


def _extract_log_source(line: str) -> Optional[str]:
    parts = line.split(" | ", 3)
    if len(parts) < 3:
        return None
    source = parts[2].strip()
    return source or None


def _read_log_lines(limit: int = 2000) -> list[str]:
    if not PIPELINE_LOG_PATH:
        return []
    path = Path(PIPELINE_LOG_PATH)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    if limit > 0:
        return lines[-limit:]
    return lines


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    cfg = _reload_project_config()
    env_values = load_env_file(ENV_FILE)
    override_values = load_override_config(CONFIG_OVERRIDE_PATH)

    config_payload = {key: _to_jsonable(getattr(cfg, key, None)) for key in CONFIG_KEYS}

    payload = {
        "paths": {
            "project_root": str(PROJECT_ROOT),
            "env_file": str(ENV_FILE),
            "override_file": str(CONFIG_OVERRIDE_PATH),
            "pipeline_log": str(PIPELINE_LOG_PATH) if PIPELINE_LOG_PATH else None,
        },
        "config": config_payload,
        "env": env_values,
        "override": override_values,
        "providers": {
            "metadata": sorted(PROVIDER_CLIENTS.keys()),
            "download": sorted(available_fetchers()),
            "llm": sorted(PROVIDER_PRESETS.keys()),
            "llm_presets": {
                name: {
                    "provider": preset.provider,
                    "base_url": preset.base_url,
                    "chat_path": preset.chat_path,
                    "api_key_env": preset.api_key_env,
                    "api_key_header": preset.api_key_header,
                    "api_key_prefix": preset.api_key_prefix,
                }
                for name, preset in PROVIDER_PRESETS.items()
            },
        },
    }
    return jsonify(payload)


@app.get("/api/logs")
def api_logs():
    source = (request.args.get("source") or "").strip()
    limit_raw = request.args.get("limit")
    limit = int(limit_raw) if str(limit_raw).isdigit() else 2000
    lines = _read_log_lines(limit)
    sources = sorted({s for s in (_extract_log_source(line) for line in lines) if s})
    if source:
        lines = [line for line in lines if _extract_log_source(line) == source]
    return jsonify(
        {
            "ok": True,
            "log_path": str(PIPELINE_LOG_PATH) if PIPELINE_LOG_PATH else None,
            "lines": lines,
            "sources": sources,
        }
    )


@app.post("/api/env")
def api_env():
    data = request.get_json(force=True) or {}
    updates = data.get("values") or {}
    cleaned: Dict[str, Optional[str]] = {}
    for key, value in updates.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if value is None:
            cleaned[key.strip()] = None
        else:
            cleaned[key.strip()] = str(value).strip()
    updated = update_env_file(ENV_FILE, cleaned)
    return jsonify({"ok": True, "env": updated})


@app.post("/api/config")
def api_config():
    data = request.get_json(force=True) or {}
    overrides = data.get("overrides")
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        return jsonify({"ok": False, "error": "overrides must be an object"}), 400
    save_override_config(CONFIG_OVERRIDE_PATH, overrides)
    return jsonify({"ok": True})


@app.post("/api/run")
def api_run_stage():
    data = request.get_json(force=True) or {}
    stage = (data.get("stage") or "").strip()
    params = data.get("params") or {}
    if not stage:
        return jsonify({"ok": False, "error": "stage is required"}), 400
    if not isinstance(params, dict):
        return jsonify({"ok": False, "error": "params must be an object"}), 400
    return jsonify(execute_stage(stage, params))


@app.post("/api/run/metadata")
def api_run_metadata():
    data = request.get_json(force=True) or {}
    return jsonify(execute_stage("metadata", data))


@app.post("/api/run/filter")
def api_run_filter():
    data = request.get_json(force=True) or {}
    return jsonify(execute_stage("filter", data))


@app.post("/api/run/download")
def api_run_download():
    data = request.get_json(force=True) or {}
    return jsonify(execute_stage("download", data))


@app.post("/api/run/convert")
def api_run_convert():
    data = request.get_json(force=True) or {}
    return jsonify(execute_stage("convert", data))


@app.post("/api/run/llm")
def api_run_llm():
    data = request.get_json(force=True) or {}
    return jsonify(execute_stage("llm", data))


if __name__ == "__main__":
    port = int(os.getenv("BENSCI_UI_PORT", "7860"))
    app.run(host="127.0.0.1", port=port, debug=False)
