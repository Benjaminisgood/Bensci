from __future__ import annotations

import importlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

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


@app.post("/api/run/metadata")
def api_run_metadata():
    data = request.get_json(force=True) or {}
    query = (data.get("query") or "").strip()
    max_results = data.get("max_results")
    providers = data.get("providers") or []
    if isinstance(providers, str):
        providers = [p.strip() for p in providers.split(",") if p.strip()]

    max_literal = int(max_results) if str(max_results).isdigit() else 0
    provider_raw = ",".join(providers)

    code = """
import sys
from bensci import config
from bensci import metadata_fetcher

query = {query}
max_results = int({max_results})
provider_raw = {provider_raw}.strip()
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
    )

    source = "metadata_fetcher.py"
    _log_pipeline("开始执行 元数据聚合", source=source)
    result = run_python_snippet(code, source=source)
    _log_pipeline(
        f"完成 元数据聚合 -> {'OK' if result['ok'] else 'FAILED'}",
        source=source,
        level=logging.INFO if result["ok"] else logging.ERROR,
    )
    return jsonify(result)


@app.post("/api/run/filter")
def api_run_filter():
    data = request.get_json(force=True) or {}
    provider = (data.get("provider") or "").strip()
    model = (data.get("model") or "").strip()
    base_url = (data.get("base_url") or "").strip()
    chat_path = (data.get("chat_path") or "").strip()
    api_key_env = (data.get("api_key_env") or "").strip()
    api_key_header = (data.get("api_key_header") or "").strip()
    api_key_prefix = data.get("api_key_prefix")
    temperature = data.get("temperature")
    timeout = data.get("timeout")
    sleep = data.get("sleep")

    cmd = [sys.executable, "-m", "bensci.metadata_filter_utils"]
    if provider:
        cmd += ["--provider", provider]
    if model:
        cmd += ["--model", model]
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
    if temperature is not None and str(temperature).strip() != "":
        cmd += ["--temperature", str(temperature)]
    if str(timeout).isdigit():
        cmd += ["--timeout", str(timeout)]
    if sleep is not None and str(sleep).strip() != "":
        cmd += ["--sleep", str(sleep)]

    source = "metadata_filter_utils.py"
    _log_pipeline("开始执行 摘要筛选", source=source)
    result = run_subprocess(cmd, source=source)
    _log_pipeline(
        f"完成 摘要筛选 -> {'OK' if result['ok'] else 'FAILED'}",
        source=source,
        level=logging.INFO if result["ok"] else logging.ERROR,
    )
    return jsonify(result)


@app.post("/api/run/download")
def api_run_download():
    data = request.get_json(force=True) or {}
    provider = (data.get("provider") or "auto").strip() or "auto"
    doi = (data.get("doi") or "").strip()
    input_csv = (data.get("input_csv") or "").strip()
    output_dir = (data.get("output_dir") or "").strip()

    cmd = [sys.executable, "-m", "bensci.literature_fetcher"]
    if input_csv:
        cmd += ["--input", input_csv]
    if output_dir:
        cmd += ["--output", output_dir]
    if provider:
        cmd += ["--provider", provider]
    if doi:
        cmd += ["--doi", doi]
    source = "literature_fetcher.py"
    _log_pipeline("开始执行 下载全文", source=source)
    result = run_subprocess(cmd, source=source)
    _log_pipeline(
        f"完成 下载全文 -> {'OK' if result['ok'] else 'FAILED'}",
        source=source,
        level=logging.INFO if result["ok"] else logging.ERROR,
    )
    return jsonify(result)


@app.post("/api/run/convert")
def api_run_convert():
    data = request.get_json(force=True) or {}
    input_path = (data.get("input_path") or "").strip()
    output_dir = (data.get("output_dir") or "").strip()
    parser = (data.get("parser") or "").strip()
    output_format = (data.get("output_format") or "").strip()
    ocr_engine = (data.get("ocr_engine") or "").strip()
    ocr_lang = (data.get("ocr_lang") or "").strip()
    ocr_dpi = data.get("ocr_dpi")
    ocr_preprocess = (data.get("ocr_preprocess") or "").strip()
    ocr_tesseract_config = (data.get("ocr_tesseract_config") or "").strip()
    ocr_easyocr_langs = (data.get("ocr_easyocr_langs") or "").strip()
    ocr_easyocr_gpu = (data.get("ocr_easyocr_gpu") or "").strip()
    ocr_paddle_lang = (data.get("ocr_paddle_lang") or "").strip()
    ocr_paddle_use_angle_cls = (data.get("ocr_paddle_use_angle_cls") or "").strip()
    ocr_paddle_use_gpu = (data.get("ocr_paddle_use_gpu") or "").strip()

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
    source = "literature_transer.py"
    _log_pipeline("开始执行 转换 JSON", source=source)
    result = run_subprocess(cmd, source=source)
    _log_pipeline(
        f"完成 转换 JSON -> {'OK' if result['ok'] else 'FAILED'}",
        source=source,
        level=logging.INFO if result["ok"] else logging.ERROR,
    )
    return jsonify(result)


@app.post("/api/run/llm")
def api_run_llm():
    data = request.get_json(force=True) or {}
    input_path = (data.get("input_path") or "").strip()
    output_path = (data.get("output_path") or "").strip()
    provider = (data.get("provider") or "").strip()
    model = (data.get("model") or "").strip()
    base_url = (data.get("base_url") or "").strip()
    chat_path = (data.get("chat_path") or "").strip()
    api_key_env = (data.get("api_key_env") or "").strip()
    api_key_header = (data.get("api_key_header") or "").strip()
    api_key_prefix = data.get("api_key_prefix")
    block_limit = data.get("block_limit")
    temperature = data.get("temperature")
    timeout = data.get("timeout")
    task = (data.get("task") or "").strip()
    output_template = (data.get("output_template") or "").strip()
    system_prompt = (data.get("system_prompt") or "").strip()
    user_prompt_template = (data.get("user_prompt_template") or "").strip()

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
    if temperature is not None and str(temperature).strip() != "":
        cmd += ["--temperature", str(temperature)]
    if str(timeout).isdigit():
        cmd += ["--timeout", str(timeout)]

    source = "llm_info_extractor.py"
    _log_pipeline("开始执行 LLM 抽取建表", source=source)
    result = run_subprocess(cmd, source=source)
    _log_pipeline(
        f"完成 LLM 抽取建表 -> {'OK' if result['ok'] else 'FAILED'}",
        source=source,
        level=logging.INFO if result["ok"] else logging.ERROR,
    )
    return jsonify(result)


if __name__ == "__main__":
    port = int(os.getenv("BENSCI_UI_PORT", "7860"))
    app.run(host="127.0.0.1", port=port, debug=False)
