#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${PROJECT_ROOT}"

ENV_FILE="${PROJECT_ROOT}/.env"
LOG_DIR="${PROJECT_ROOT}/data_resourse/logs"
UI_PID_FILE="${LOG_DIR}/bensci_ui.pid"
UI_PORT_FILE="${LOG_DIR}/bensci_ui.port"
UI_LOG_FILE="${LOG_DIR}/bensci_ui.log"

export PYTHONPATH="${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

LOG_SECTION() {
  printf "\n\033[1m[%s]\033[0m %s\n" "$1" "$2"
}

prompt_with_default() {
  local prompt="$1"
  local default="$2"
  local var
  if [ -n "${default}" ]; then
    read -rp "${prompt} [默认: ${default}]: " var
    if [ -z "${var}" ]; then
      var="${default}"
    fi
  else
    read -rp "${prompt}: " var
  fi
  printf "%s" "${var}"
}

prompt_int() {
  local prompt="$1"
  local default="$2"
  local value
  while true; do
    value="$(prompt_with_default "${prompt}" "${default}")"
    if [ -z "${value}" ]; then
      printf "%s" ""
      return 0
    fi
    if [[ "${value}" =~ ^[0-9]+$ ]]; then
      printf "%s" "${value}"
      return 0
    fi
    echo "请输入正整数。"
  done
}

prompt_float() {
  local prompt="$1"
  local default="$2"
  local value
  while true; do
    value="$(prompt_with_default "${prompt}" "${default}")"
    if [ -z "${value}" ]; then
      printf "%s" ""
      return 0
    fi
    if [[ "${value}" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
      printf "%s" "${value}"
      return 0
    fi
    echo "请输入数字（例如 0.5）。"
  done
}

ask_yes_no() {
  local prompt="$1"
  local default="${2:-N}"
  local hint
  case "${default}" in
    [Yy]) hint="[Y/n]" ;;
    *) hint="[y/N]" ;;
  esac
  local input
  while true; do
    read -rp "${prompt} ${hint}: " input
    input="${input:-${default}}"
    case "${input}" in
      [Yy]|[Yy][Ee][Ss])
        echo "1"
        return 0
        ;;
      [Nn]|[Nn][Oo])
        echo "0"
        return 0
        ;;
    esac
    echo "请输入 y 或 n。"
  done
}

ensure_python() {
  command -v python >/dev/null 2>&1 || {
    echo "未找到 python，请先激活虚拟环境或安装 Python。"
    exit 1
  }
}

ensure_env_file() {
  if [ ! -f "${ENV_FILE}" ]; then
    touch "${ENV_FILE}"
  fi
}

ensure_log_dir() {
  mkdir -p "${LOG_DIR}"
}

get_env_current() {
  local key="$1"
  if [ ! -f "${ENV_FILE}" ]; then
    return
  fi
  local line
  line="$(grep -E "^${key}[[:space:]]*=" "${ENV_FILE}" | tail -n 1 || true)"
  if [ -n "${line}" ]; then
    line="${line#*=}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    printf "%s" "${line}"
  fi
}

set_env_value() {
  local key="$1"
  local value="$2"
  if [ -z "${value}" ]; then
    return
  fi
  ensure_env_file
  if grep -qE "^${key}[[:space:]]*=" "${ENV_FILE}"; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
      sed -i '' "s|^${key}[[:space:]]*=.*|${key}=${value}|g" "${ENV_FILE}"
    else
      sed -i "s|^${key}[[:space:]]*=.*|${key}=${value}|g" "${ENV_FILE}"
    fi
  else
    printf "%s=%s\n" "${key}" "${value}" >> "${ENV_FILE}"
  fi
}

configure_api_keys() {
  LOG_SECTION "API" "配置 Elsevier / Springer API Key（可回车跳过）"
  local current_els current_spring current_spring_meta
  current_els="${ELSEVIER_API_KEY:-$(get_env_current "ELSEVIER_API_KEY")}" || true
  current_spring="${SPRINGER_OPEN_ACCESS_KEY:-$(get_env_current "SPRINGER_OPEN_ACCESS_KEY")}" || true
  current_spring_meta="${SPRINGER_META_API_KEY:-$(get_env_current "SPRINGER_META_API_KEY")}" || true

  local els_key spring_key spring_meta_key
  els_key="$(prompt_with_default "Elsevier/Scopus API Key" "${current_els}")"
  spring_key="$(prompt_with_default "Springer Open Access API Key" "${current_spring}")"
  spring_meta_key="$(prompt_with_default "Springer Meta API Key（如需下载）" "${current_spring_meta}")"

  set_env_value "ELSEVIER_API_KEY" "${els_key}"
  set_env_value "SPRINGER_OPEN_ACCESS_KEY" "${spring_key}"
  set_env_value "SPRINGER_META_API_KEY" "${spring_meta_key}"
}

maybe_configure_publisher_keys() {
  local should_configure
  should_configure="$(ask_yes_no "需要配置/更新 Elsevier/Springer API Key 吗?" "n")"
  if [ "${should_configure}" -eq 1 ]; then
    configure_api_keys
  fi
}

python_config_value() {
  local expression="$1"
  python - <<PY
from bensci.config import ${expression} as value
if value is None:
    print("")
elif isinstance(value, (list, tuple)):
    print(",".join(str(v) for v in value))
else:
    print(value)
PY
}

open_browser() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then
    open "${url}" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${url}" >/dev/null 2>&1 || true
  else
    echo "请在浏览器中打开：${url}"
  fi
}

is_process_running() {
  local pid_file="$1"
  if [ ! -f "${pid_file}" ]; then
    return 1
  fi
  local pid
  pid="$(cat "${pid_file}" 2>/dev/null || true)"
  if [ -z "${pid}" ]; then
    return 1
  fi
  if kill -0 "${pid}" 2>/dev/null; then
    return 0
  fi
  return 1
}

start_ui() {
  LOG_SECTION "UI" "启动可视化界面"
  ensure_log_dir

  local default_port
  default_port="${BENSCI_UI_PORT:-7860}"
  local port
  port="$(prompt_with_default "UI 端口" "${default_port}")"

  if is_process_running "${UI_PID_FILE}"; then
    local running_pid
    running_pid="$(cat "${UI_PID_FILE}")"
    local running_port
    running_port="$(cat "${UI_PORT_FILE}" 2>/dev/null || true)"
    echo "UI 已在运行 (PID: ${running_pid})"
    if [ -n "${running_port}" ]; then
      port="${running_port}"
    fi
    open_browser "http://127.0.0.1:${port}"
    return 0
  fi

  BENSCI_UI_PORT="${port}" \
  PYTHONPATH="${PROJECT_ROOT}${PYTHONPATH:+:${PYTHONPATH}}" \
  nohup python "${PROJECT_ROOT}/ui/app.py" > "${UI_LOG_FILE}" 2>&1 &

  local pid=$!
  echo "${pid}" > "${UI_PID_FILE}"
  echo "${port}" > "${UI_PORT_FILE}"
  sleep 1
  if kill -0 "${pid}" 2>/dev/null; then
    echo "UI 已启动 (PID: ${pid})"
    echo "日志：${UI_LOG_FILE}"
    open_browser "http://127.0.0.1:${port}"
  else
    echo "UI 启动失败，请查看日志：${UI_LOG_FILE}"
    rm -f "${UI_PID_FILE}" "${UI_PORT_FILE}"
    return 1
  fi
}

stop_process_by_pidfile() {
  local name="$1"
  local pid_file="$2"
  if [ ! -f "${pid_file}" ]; then
    return 1
  fi
  local pid
  pid="$(cat "${pid_file}" 2>/dev/null || true)"
  if [ -z "${pid}" ]; then
    rm -f "${pid_file}"
    return 1
  fi
  if kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" >/dev/null 2>&1 || true
    sleep 1
    if kill -0 "${pid}" 2>/dev/null; then
      kill -9 "${pid}" >/dev/null 2>&1 || true
    fi
    echo "${name} 已停止 (PID: ${pid})"
  else
    echo "${name} 未在运行 (PID: ${pid})"
  fi
  rm -f "${pid_file}"
  return 0
}

stop_ui_fallback() {
  local matches
  matches="$(ps -ax -o pid=,command= | grep "${PROJECT_ROOT}/ui/app.py" | grep -v grep || true)"
  if [ -z "${matches}" ]; then
    return 1
  fi
  echo "检测到未记录的 UI 进程，尝试停止："
  echo "${matches}"
  local pids
  pids="$(echo "${matches}" | awk '{print $1}')"
  if [ -n "${pids}" ]; then
    kill ${pids} >/dev/null 2>&1 || true
    sleep 1
    for pid in ${pids}; do
      if kill -0 "${pid}" 2>/dev/null; then
        kill -9 "${pid}" >/dev/null 2>&1 || true
      fi
    done
    echo "UI 进程已停止。"
    return 0
  fi
  return 1
}

stop_all() {
  LOG_SECTION "EXIT" "停止前端/后端进程"
  if ! stop_process_by_pidfile "UI" "${UI_PID_FILE}"; then
    stop_ui_fallback || echo "未找到正在运行的 UI 进程。"
  fi
  rm -f "${UI_PORT_FILE}" || true
}

show_main_menu() {
  cat <<'EOF'
请选择要执行的操作：
  1) 打开前端 UI（可视化运行）
  2) 运行单个任务（交互填写参数）
  3) 退出项目（停止前端/后端进程）
EOF
}

show_task_menu() {
  cat <<'EOF'
请选择要执行的任务：
  1) 元数据聚合
  2) 摘要筛选
  3) 下载全文
  4) 格式转化统一
  5) LLM 抽取建表
  6) 返回上一级
EOF
}

run_metadata_task() {
  LOG_SECTION "METADATA" "执行元数据聚合"
  maybe_configure_publisher_keys

  local default_query default_max default_providers default_output
  default_query="$(python_config_value 'METADATA_DEFAULT_QUERY')"
  default_max="$(python_config_value 'METADATA_MAX_RESULTS')"
  default_providers="$(python_config_value 'METADATA_PROVIDERS')"
  default_output="$(python_config_value 'METADATA_CSV_PATH')"

  if [ -z "${default_providers}" ]; then
    echo "当前 Provider 配置：全部 Provider"
  else
    echo "当前 Provider 配置：${default_providers}"
  fi

  local query max_results providers output_csv
  query="$(prompt_with_default "请输入元数据检索关键词" "${default_query}")"
  max_results="$(prompt_int "最大返回条目数" "${default_max}")"
  providers="$(prompt_with_default "限制 Provider（逗号分隔，可留空）" "${default_providers}")"
  output_csv="$(prompt_with_default "输出 CSV 路径" "${default_output}")"

  if BENSCI_QUERY="${query}" \
     BENSCI_MAX_RESULTS="${max_results}" \
     BENSCI_PROVIDERS="${providers}" \
     BENSCI_OUTPUT_CSV="${output_csv}" \
     python - <<'PY'
import os
import sys
from pathlib import Path
from bensci import config
from bensci import metadata_fetcher

query = os.environ.get("BENSCI_QUERY", "").strip()
max_raw = os.environ.get("BENSCI_MAX_RESULTS", "").strip()
provider_raw = os.environ.get("BENSCI_PROVIDERS", "").strip()
output_csv = os.environ.get("BENSCI_OUTPUT_CSV", "").strip()

if not query:
    query = getattr(config, "METADATA_DEFAULT_QUERY", "")

if output_csv:
    path = Path(output_csv)
    config.METADATA_CSV_PATH = path
    config.ASSETS1_DIR = path.parent
    metadata_fetcher.METADATA_CSV_PATH = config.METADATA_CSV_PATH
    metadata_fetcher.ASSETS1_DIR = config.ASSETS1_DIR

if max_raw.isdigit():
    max_results = int(max_raw)
else:
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
print(f"metadata_saved={config.METADATA_CSV_PATH}")
PY
  then
    echo "元数据聚合完成。"
  else
    echo "元数据聚合失败，请查看日志：${LOG_DIR}/pipeline.log"
  fi
}

run_filter_task() {
  LOG_SECTION "FILTER" "执行摘要筛选"

  local default_provider default_model default_base_url default_chat_path
  local default_api_key_env default_api_key_header default_api_key_prefix
  local default_temp default_timeout default_sleep
  local default_input default_output

  default_provider="$(python_config_value 'METADATA_FILTER_PROVIDER')"
  default_model="$(python_config_value 'METADATA_FILTER_MODEL')"
  default_base_url="$(python_config_value 'METADATA_FILTER_BASE_URL')"
  default_chat_path="$(python_config_value 'METADATA_FILTER_CHAT_PATH')"
  default_api_key_env="$(python_config_value 'METADATA_FILTER_API_KEY_ENV')"
  default_api_key_header="$(python_config_value 'METADATA_FILTER_API_KEY_HEADER')"
  default_api_key_prefix="$(python_config_value 'METADATA_FILTER_API_KEY_PREFIX')"
  default_temp="$(python_config_value 'METADATA_FILTER_TEMPERATURE')"
  default_timeout="$(python_config_value 'METADATA_FILTER_TIMEOUT')"
  default_sleep="$(python_config_value 'METADATA_FILTER_SLEEP_SECONDS')"
  default_input="$(python_config_value 'METADATA_CSV_PATH')"
  default_output="$(python_config_value 'FILTERED_METADATA_CSV_PATH')"

  local input_csv output_csv provider model temperature timeout sleep
  input_csv="$(prompt_with_default "输入 CSV 路径" "${default_input}")"
  output_csv="$(prompt_with_default "输出 CSV 路径" "${default_output}")"
  provider="$(prompt_with_default "LLM Provider" "${default_provider}")"
  model="$(prompt_with_default "LLM 模型" "${default_model}")"
  temperature="$(prompt_float "temperature" "${default_temp}")"
  timeout="$(prompt_int "超时时间（秒）" "${default_timeout}")"
  sleep="$(prompt_float "请求间隔（秒）" "${default_sleep}")"

  local base_url=""
  local chat_path=""
  local api_key_env=""
  local api_key_header=""
  local api_key_prefix=""

  local enable_advanced
  enable_advanced="$(ask_yes_no "是否配置高级 API 参数?" "n")"
  if [ "${enable_advanced}" -eq 1 ]; then
    base_url="$(prompt_with_default "Base URL" "${default_base_url}")"
    chat_path="$(prompt_with_default "Chat Path" "${default_chat_path}")"
    api_key_env="$(prompt_with_default "API Key 环境变量名" "${default_api_key_env}")"
    api_key_header="$(prompt_with_default "API Key Header" "${default_api_key_header}")"
    api_key_prefix="$(prompt_with_default "API Key Prefix" "${default_api_key_prefix}")"
  fi

  if BENSCI_FILTER_INPUT="${input_csv}" \
     BENSCI_FILTER_OUTPUT="${output_csv}" \
     BENSCI_FILTER_PROVIDER="${provider}" \
     BENSCI_FILTER_MODEL="${model}" \
     BENSCI_FILTER_BASE_URL="${base_url}" \
     BENSCI_FILTER_CHAT_PATH="${chat_path}" \
     BENSCI_FILTER_API_KEY_ENV="${api_key_env}" \
     BENSCI_FILTER_API_KEY_HEADER="${api_key_header}" \
     BENSCI_FILTER_API_KEY_PREFIX="${api_key_prefix}" \
     BENSCI_FILTER_TEMPERATURE="${temperature}" \
     BENSCI_FILTER_TIMEOUT="${timeout}" \
     BENSCI_FILTER_SLEEP="${sleep}" \
     python - <<'PY'
import os
from pathlib import Path
from bensci import metadata_filter_utils as mf

input_csv = os.environ.get("BENSCI_FILTER_INPUT", "").strip()
output_csv = os.environ.get("BENSCI_FILTER_OUTPUT", "").strip()

if input_csv:
    mf.SOURCE_CSV = Path(input_csv)
if output_csv:
    mf.TARGET_CSV = Path(output_csv)
if output_csv:
    mf.ASSETS1_DIR = Path(output_csv).parent
elif input_csv:
    mf.ASSETS1_DIR = Path(input_csv).parent

provider = os.environ.get("BENSCI_FILTER_PROVIDER", "").strip() or mf.DEFAULT_PROVIDER
model = os.environ.get("BENSCI_FILTER_MODEL", "").strip() or mf.DEFAULT_MODEL
base_url = os.environ.get("BENSCI_FILTER_BASE_URL", "").strip() or mf.DEFAULT_BASE_URL
chat_path = os.environ.get("BENSCI_FILTER_CHAT_PATH", "").strip() or mf.DEFAULT_CHAT_PATH
api_key_env = os.environ.get("BENSCI_FILTER_API_KEY_ENV", "").strip() or mf.DEFAULT_API_KEY_ENV
api_key_header = os.environ.get("BENSCI_FILTER_API_KEY_HEADER", "").strip() or mf.DEFAULT_API_KEY_HEADER
api_key_prefix = os.environ.get("BENSCI_FILTER_API_KEY_PREFIX", "")
if api_key_prefix == "":
    api_key_prefix = mf.DEFAULT_API_KEY_PREFIX

temperature_raw = os.environ.get("BENSCI_FILTER_TEMPERATURE", "").strip()
timeout_raw = os.environ.get("BENSCI_FILTER_TIMEOUT", "").strip()
sleep_raw = os.environ.get("BENSCI_FILTER_SLEEP", "").strip()

def _parse_float(value, fallback):
    try:
        return float(value)
    except Exception:
        return fallback

def _parse_int(value, fallback):
    try:
        return int(value)
    except Exception:
        return fallback

temperature = _parse_float(temperature_raw, mf.DEFAULT_TEMPERATURE)
timeout = _parse_int(timeout_raw, mf.DEFAULT_TIMEOUT)
sleep_seconds = _parse_float(sleep_raw, mf.DEFAULT_SLEEP_SECONDS)

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
)
print(f"filter_passed={count}")
PY
  then
    echo "摘要筛选完成。"
  else
    echo "摘要筛选失败，请查看日志：${LOG_DIR}/pipeline.log"
  fi
}

run_download_task() {
  LOG_SECTION "DOWNLOAD" "执行全文下载"
  maybe_configure_publisher_keys

  local default_input default_output
  default_input="$(python_config_value 'FILTERED_METADATA_CSV_PATH')"
  default_output="$(python_config_value 'ASSETS2_DIR')"

  local provider doi input_csv output_dir
  provider="$(prompt_with_default "下载 Provider（auto/elsevier/springer/acs/rsc/wiley/scihub）" "auto")"
  doi="$(prompt_with_default "直接输入 DOI（多个用逗号/空格分隔，留空则使用 CSV）" "")"
  if [ -z "${doi}" ]; then
    input_csv="$(prompt_with_default "输入 CSV 路径" "${default_input}")"
  else
    input_csv=""
  fi
  output_dir="$(prompt_with_default "输出目录" "${default_output}")"

  local cmd=(python -m bensci.literature_fetcher)
  if [ -n "${input_csv}" ]; then
    cmd+=(--input "${input_csv}")
  fi
  if [ -n "${output_dir}" ]; then
    cmd+=(--output "${output_dir}")
  fi
  if [ -n "${provider}" ]; then
    cmd+=(--provider "${provider}")
  fi
  if [ -n "${doi}" ]; then
    cmd+=(--doi "${doi}")
  fi

  if "${cmd[@]}"; then
    echo "全文下载完成。"
  else
    echo "全文下载失败，请查看日志：${LOG_DIR}/pipeline.log"
  fi
}

run_convert_task() {
  LOG_SECTION "CONVERT" "执行格式转化统一"

  local default_input default_output default_format
  default_input="$(python_config_value 'XML_SOURCE_DIR')"
  default_output="$(python_config_value 'BLOCKS_OUTPUT_DIR')"
  default_format="$(python_config_value 'TRANSER_OUTPUT_FORMAT')"

  local input_path output_dir parser output_format
  input_path="$(prompt_with_default "输入路径（XML 文件或目录）" "${default_input}")"
  output_dir="$(prompt_with_default "输出目录" "${default_output}")"
  parser="$(prompt_with_default "解析器名称（留空自动检测）" "")"
  output_format="$(prompt_with_default "输出格式（json/md/both）" "${default_format}")"

  local cmd=(python -m bensci.literature_transer)
  if [ -n "${input_path}" ]; then
    cmd+=(--input "${input_path}")
  fi
  if [ -n "${output_dir}" ]; then
    cmd+=(--output "${output_dir}")
  fi
  if [ -n "${parser}" ]; then
    cmd+=(--parser "${parser}")
  fi
  if [ -n "${output_format}" ]; then
    cmd+=(--output-format "${output_format}")
  fi

  local enable_ocr
  enable_ocr="$(ask_yes_no "是否配置 OCR 参数?" "n")"
  if [ "${enable_ocr}" -eq 1 ]; then
    local ocr_engine ocr_lang ocr_dpi ocr_preprocess
    local ocr_tesseract_config ocr_easyocr_langs ocr_easyocr_gpu
    local ocr_paddle_lang ocr_paddle_use_angle_cls ocr_paddle_use_gpu

    ocr_engine="$(prompt_with_default "OCR 引擎（auto/tesseract/paddle/easyocr/rapidocr/pypdf2）" "")"
    ocr_lang="$(prompt_with_default "OCR 语言" "")"
    ocr_dpi="$(prompt_int "OCR DPI" "")"
    ocr_preprocess="$(prompt_with_default "OCR 预处理（none/grayscale/binarize/sharpen）" "")"
    ocr_tesseract_config="$(prompt_with_default "Tesseract 额外参数" "")"
    ocr_easyocr_langs="$(prompt_with_default "EasyOCR 语言列表（逗号分隔）" "")"
    ocr_easyocr_gpu="$(prompt_with_default "EasyOCR GPU（true/false）" "")"
    ocr_paddle_lang="$(prompt_with_default "PaddleOCR 语言" "")"
    ocr_paddle_use_angle_cls="$(prompt_with_default "PaddleOCR 方向分类（true/false）" "")"
    ocr_paddle_use_gpu="$(prompt_with_default "PaddleOCR GPU（true/false）" "")"

    if [ -n "${ocr_engine}" ]; then
      cmd+=(--ocr-engine "${ocr_engine}")
    fi
    if [ -n "${ocr_lang}" ]; then
      cmd+=(--ocr-lang "${ocr_lang}")
    fi
    if [ -n "${ocr_dpi}" ]; then
      cmd+=(--ocr-dpi "${ocr_dpi}")
    fi
    if [ -n "${ocr_preprocess}" ]; then
      cmd+=(--ocr-preprocess "${ocr_preprocess}")
    fi
    if [ -n "${ocr_tesseract_config}" ]; then
      cmd+=(--ocr-tesseract-config "${ocr_tesseract_config}")
    fi
    if [ -n "${ocr_easyocr_langs}" ]; then
      cmd+=(--ocr-easyocr-langs "${ocr_easyocr_langs}")
    fi
    if [[ "${ocr_easyocr_gpu}" == "true" || "${ocr_easyocr_gpu}" == "false" ]]; then
      cmd+=(--ocr-easyocr-gpu "${ocr_easyocr_gpu}")
    fi
    if [ -n "${ocr_paddle_lang}" ]; then
      cmd+=(--ocr-paddle-lang "${ocr_paddle_lang}")
    fi
    if [[ "${ocr_paddle_use_angle_cls}" == "true" || "${ocr_paddle_use_angle_cls}" == "false" ]]; then
      cmd+=(--ocr-paddle-use-angle-cls "${ocr_paddle_use_angle_cls}")
    fi
    if [[ "${ocr_paddle_use_gpu}" == "true" || "${ocr_paddle_use_gpu}" == "false" ]]; then
      cmd+=(--ocr-paddle-use-gpu "${ocr_paddle_use_gpu}")
    fi
  fi

  # Ensure PaddleX performs connectivity checks so models can be auto-downloaded.
  export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=

  if "${cmd[@]}"; then
    echo "格式转化完成。"
  else
    echo "格式转化失败，请查看日志：${LOG_DIR}/pipeline.log"
  fi
}

run_llm_task() {
  LOG_SECTION "LLM" "执行 LLM 抽取建表"

  local default_input default_output default_provider default_model
  local default_block_limit default_temperature default_timeout

  default_input="$(python_config_value 'BLOCKS_OUTPUT_DIR')"
  default_output="$(python_config_value 'LLM_EXTRACTION_OUTPUT_PATH')"
  default_provider="$(python_config_value 'LLM_EXTRACTION_PROVIDER')"
  default_model="$(python_config_value 'LLM_EXTRACTION_MODEL')"
  default_block_limit="$(python_config_value 'LLM_EXTRACTION_BLOCK_LIMIT')"
  default_temperature="$(python_config_value 'LLM_EXTRACTION_TEMPERATURE')"
  default_timeout="$(python_config_value 'LLM_EXTRACTION_TIMEOUT')"

  local input_path output_path provider model block_limit temperature timeout
  input_path="$(prompt_with_default "输入路径（JSON 文件或目录）" "${default_input}")"
  output_path="$(prompt_with_default "输出 CSV 路径" "${default_output}")"
  provider="$(prompt_with_default "LLM Provider" "${default_provider}")"
  model="$(prompt_with_default "LLM 模型" "${default_model}")"
  block_limit="$(prompt_int "片段数量上限" "${default_block_limit}")"
  temperature="$(prompt_float "temperature" "${default_temperature}")"
  timeout="$(prompt_int "超时时间（秒）" "${default_timeout}")"

  local cmd=(python -m bensci.llm_info_extractor)
  if [ -n "${input_path}" ]; then
    cmd+=(--input "${input_path}")
  fi
  if [ -n "${output_path}" ]; then
    cmd+=(--output "${output_path}")
  fi
  if [ -n "${provider}" ]; then
    cmd+=(--provider "${provider}")
  fi
  if [ -n "${model}" ]; then
    cmd+=(--model "${model}")
  fi
  if [ -n "${block_limit}" ]; then
    cmd+=(--block-limit "${block_limit}")
  fi
  if [ -n "${temperature}" ]; then
    cmd+=(--temperature "${temperature}")
  fi
  if [ -n "${timeout}" ]; then
    cmd+=(--timeout "${timeout}")
  fi

  local enable_advanced
  enable_advanced="$(ask_yes_no "是否配置高级 LLM 参数?" "n")"
  if [ "${enable_advanced}" -eq 1 ]; then
    local base_url chat_path api_key_env api_key_header api_key_prefix
    local task output_template system_prompt user_prompt_template
    local auto_schema schema_sample_size schema_max_fields schema_output

    base_url="$(prompt_with_default "Base URL" "")"
    chat_path="$(prompt_with_default "Chat Path" "")"
    api_key_env="$(prompt_with_default "API Key 环境变量名" "")"
    api_key_header="$(prompt_with_default "API Key Header" "")"
    api_key_prefix="$(prompt_with_default "API Key Prefix" "")"
    task="$(prompt_with_default "追加任务说明" "")"
    output_template="$(prompt_with_default "输出模板（JSON 文本）" "")"
    system_prompt="$(prompt_with_default "System Prompt" "")"
    user_prompt_template="$(prompt_with_default "User Prompt 模板" "")"

    auto_schema="$(ask_yes_no "是否启用自动 schema?" "n")"
    if [ "${auto_schema}" -eq 1 ]; then
      schema_sample_size="$(prompt_int "Schema 抽样数量" "6")"
      schema_max_fields="$(prompt_int "Schema 最大字段数" "18")"
      schema_output="$(prompt_with_default "Schema 输出路径" "")"
      cmd+=(--auto-schema)
    else
      schema_sample_size=""
      schema_max_fields=""
      schema_output=""
    fi

    if [ -n "${base_url}" ]; then
      cmd+=(--base-url "${base_url}")
    fi
    if [ -n "${chat_path}" ]; then
      cmd+=(--chat-path "${chat_path}")
    fi
    if [ -n "${api_key_env}" ]; then
      cmd+=(--api-key-env "${api_key_env}")
    fi
    if [ -n "${api_key_header}" ]; then
      cmd+=(--api-key-header "${api_key_header}")
    fi
    if [ -n "${api_key_prefix}" ]; then
      cmd+=(--api-key-prefix "${api_key_prefix}")
    fi
    if [ -n "${task}" ]; then
      cmd+=(--task "${task}")
    fi
    if [ -n "${output_template}" ]; then
      cmd+=(--output-template "${output_template}")
    fi
    if [ -n "${system_prompt}" ]; then
      cmd+=(--system-prompt "${system_prompt}")
    fi
    if [ -n "${user_prompt_template}" ]; then
      cmd+=(--user-prompt-template "${user_prompt_template}")
    fi
    if [ -n "${schema_sample_size}" ]; then
      cmd+=(--schema-sample-size "${schema_sample_size}")
    fi
    if [ -n "${schema_max_fields}" ]; then
      cmd+=(--schema-max-fields "${schema_max_fields}")
    fi
    if [ -n "${schema_output}" ]; then
      cmd+=(--schema-output "${schema_output}")
    fi
  fi

  if "${cmd[@]}"; then
    echo "LLM 抽取完成。"
  else
    echo "LLM 抽取失败，请查看日志：${LOG_DIR}/pipeline.log"
  fi
}

run_single_task() {
  show_task_menu
  read -rp "请输入任务编号：" task
  case "${task}" in
    1) run_metadata_task ;;
    2) run_filter_task ;;
    3) run_download_task ;;
    4) run_convert_task ;;
    5) run_llm_task ;;
    6) return 0 ;;
    *) echo "无效选项：${task}" ;;
  esac
}

main() {
  ensure_python
  ensure_log_dir

  while true; do
    show_main_menu
    read -rp "请输入选项编号：" action
    case "${action}" in
      1)
        start_ui
        ;;
      2)
        run_single_task
        ;;
      3)
        stop_all
        exit 0
        ;;
      *)
        echo "无效选项：${action}"
        ;;
    esac
  done
}

main "$@"
