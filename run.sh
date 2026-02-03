#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env"
API_KEYS_CONFIGURED=0

declare -r STAGE_METADATA=1
declare -r STAGE_FILTER=2
declare -r STAGE_DOWNLOAD=3
declare -r STAGE_CONVERT=4
declare -r STAGE_LLM=5

PIPELINE_STAGE_ORDER=(
  "${STAGE_METADATA}"
  "${STAGE_FILTER}"
  "${STAGE_DOWNLOAD}"
  "${STAGE_CONVERT}"
  "${STAGE_LLM}"
)

PIPELINE_STAGE_LABELS=()
PIPELINE_STAGE_LABELS[${STAGE_METADATA}]="元数据聚合"
PIPELINE_STAGE_LABELS[${STAGE_FILTER}]="摘要筛选"
PIPELINE_STAGE_LABELS[${STAGE_DOWNLOAD}]="下载全文"
PIPELINE_STAGE_LABELS[${STAGE_CONVERT}]="格式转化统一"
PIPELINE_STAGE_LABELS[${STAGE_LLM}]="LLM 抽取/建表"

# ---------- 预先收集的交互配置 ----------
METADATA_CFG_QUERY=""
METADATA_CFG_MAX_RESULTS=""
METADATA_CFG_PROVIDER_LIMIT=""

DOWNLOAD_CFG_PROVIDER="auto"
DOWNLOAD_CFG_MANUAL_FLOW=0
DOWNLOAD_CFG_DOIS=""

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

is_valid_stage() {
  local value="$1"
  if [[ "${value}" =~ ^[0-9]+$ ]] && (( value >= STAGE_METADATA && value <= STAGE_LLM )); then
    return 0
  fi
  return 1
}

show_pipeline_stage_menu() {
  echo "流水线阶段："
  local stage
  for stage in "${PIPELINE_STAGE_ORDER[@]}"; do
    printf "  %d) %s\n" "${stage}" "${PIPELINE_STAGE_LABELS[${stage}]}"
  done
}

read_stage_sequence() {
  local prompt="$1"
  local input
  while true; do
    read -rp "${prompt}: " input
    input="${input//,/ }"
    if [ -z "$(echo "${input}" | tr -d '[:space:]')" ]; then
      echo "请输入至少一个阶段编号。"
      continue
    fi

    local selections=()
    local invalid=0
    local token
    for token in ${input}; do
      if ! is_valid_stage "${token}"; then
        invalid=1
        break
      fi
      if [[ " ${selections[*]} " == *" ${token} "* ]]; then
        echo "阶段 ${token} 重复，请重新输入。"
        invalid=1
        break
      fi
      selections+=("${token}")
    done
    if [ "${invalid}" -eq 0 ]; then
      echo "${selections[@]}"
      return 0
    fi
    echo "无效阶段编号，请重新输入（范围 ${STAGE_METADATA}-${STAGE_LLM}）。"
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

show_main_menu() {
  cat <<'EOF'
请选择要执行的操作：
  1) 自定义流水线（勾选执行步骤）
  2) 摘要快速筛选（未解基元动力学 + 具体反应）
  3) 仅配置/更新 API Key
  4) 退出
EOF
}

ensure_env_file() {
  if [ ! -f "${ENV_FILE}" ]; then
    touch "${ENV_FILE}"
  fi
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
    # Trim possible whitespace around the value to match dotenv semantics.
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

configure_api_keys() {
  if [ "${API_KEYS_CONFIGURED}" -eq 1 ]; then
    return
  fi

  LOG_SECTION "API" "配置 API Key（可回车跳过，沿用 .env 中已有值）"
  local current_els current_spring current_spring_meta
  current_els="${ELSEVIER_API_KEY:-$(get_env_current "ELSEVIER_API_KEY")}"
  current_spring="${SPRINGER_OPEN_ACCESS_KEY:-$(get_env_current "SPRINGER_OPEN_ACCESS_KEY")}"
  current_spring_meta="${SPRINGER_META_API_KEY:-$(get_env_current "SPRINGER_META_API_KEY")}"

  local els_key spring_key spring_meta_key
  els_key="$(prompt_with_default "Elsevier/Scopus API Key" "${current_els}")"
  spring_key="$(prompt_with_default "Springer Open Access API Key" "${current_spring}")"
  spring_meta_key="$(prompt_with_default "Springer Meta API Key（如需下载）" "${current_spring_meta}")"

  set_env_value "ELSEVIER_API_KEY" "${els_key}"
  set_env_value "SPRINGER_OPEN_ACCESS_KEY" "${spring_key}"
  set_env_value "SPRINGER_META_API_KEY" "${spring_meta_key}"

  API_KEYS_CONFIGURED=1
}

collect_metadata_config() {
  local default_query default_max default_providers
  default_query="$(python_config_value 'METADATA_DEFAULT_QUERY')"
  default_max="$(python_config_value 'METADATA_MAX_RESULTS')"
  default_providers="$(python_config_value 'METADATA_PROVIDERS')"
  if [ -z "${default_providers}" ]; then
    default_providers="全部 Provider"
  fi
  echo "当前 Provider 配置：${default_providers}"

  local search_query max_results provider_input
  search_query="$(prompt_with_default "请输入元数据检索关键词（能源小分子催化）" "${default_query}")"
  max_results="$(prompt_with_default "最大返回条目数" "${default_max}")"
  if ! [[ "${max_results}" =~ ^[0-9]+$ ]]; then
    echo "最大返回条目数必须为正整数。" >&2
    exit 1
  fi
  provider_input="$(prompt_with_default "限制元数据 Provider（逗号分隔，可留空表示沿用配置）" "")"

  METADATA_CFG_QUERY="${search_query}"
  METADATA_CFG_MAX_RESULTS="${max_results}"
  METADATA_CFG_PROVIDER_LIMIT="${provider_input}"
}

run_metadata_stage() {
  LOG_SECTION "METADATA" "执行元数据聚合"

  local search_query="$1"
  local max_results="$2"
  local provider_input="$3"

  if python - <<PY 2>&1 | tee "${PROJECT_ROOT}/logs_metadata_fetcher.tmp"; then
import sys
from bensci import config
from bensci import metadata_fetcher

query = """${search_query}"""
max_results = int("${max_results}")
provider_raw = """${provider_input}""".strip()

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
PY
    echo "元数据聚合完成，结果已写入 $(python_config_value 'METADATA_CSV_PATH')."
  else
    echo "元数据聚合失败，详情见 logs_metadata_fetcher.tmp。"
    exit 1
  fi
}

prompt_provider_override() {
  local provider
  provider="$(prompt_with_default "指定抓取 Provider（auto/elsevier/springer/acs/rsc/wiley/scihub）" "auto")"
  echo "${provider:-auto}"
}

prompt_doi_input() {
  echo "请输入一个或多个 DOI，可使用逗号、空格分隔："
  local raw
  read -r raw
  echo "${raw}"
}

collect_download_config() {
  local metadata_before_download="$1"

  DOWNLOAD_CFG_PROVIDER="$(prompt_provider_override)"
  DOWNLOAD_CFG_MANUAL_FLOW=0
  DOWNLOAD_CFG_DOIS=""

  if (( metadata_before_download == 1 )); then
    echo "下载阶段位于元数据之后，将默认使用最新生成的 CSV。"
    DOWNLOAD_CFG_MANUAL_FLOW=0
  else
    echo "下载阶段未在元数据之后，可选择沿用现有 CSV 或手动输入 DOI。"
    DOWNLOAD_CFG_MANUAL_FLOW="$(ask_yes_no "使用手动 DOI 而非现有 CSV?" "n")"
  fi

  if (( DOWNLOAD_CFG_MANUAL_FLOW == 1 )); then
    DOWNLOAD_CFG_DOIS="$(prompt_doi_input)"
    if [ -z "$(echo "${DOWNLOAD_CFG_DOIS}" | tr -d '[:space:],;')" ]; then
      echo "未输入任何 DOI，已取消操作。"
      exit 1
    fi
  fi
}

download_from_csv() {
  local provider_override="$1"
  local csv_path="$2"
  LOG_SECTION "DOWNLOAD" "根据 CSV 下载全文"
  local cmd=(python -m bensci.literature_fetcher)
  if [ -n "${csv_path}" ]; then
    cmd+=("--input" "${csv_path}")
  fi
  if [ "${provider_override}" != "auto" ]; then
    cmd+=("--provider" "${provider_override}")
  fi
  if "${cmd[@]}" 2>&1 | tee "${PROJECT_ROOT}/logs_literature_fetcher.tmp"; then
    echo "全文下载完成。"
  else
    echo "全文下载过程中出现错误，详见 logs_literature_fetcher.tmp。"
  fi
}

convert_fulltexts() {
  LOG_SECTION "TRANSFORM" "格式转化统一（JSON/MD）"
  if python -m bensci.literature_transer 2>&1 | tee "${PROJECT_ROOT}/logs_literature_transer.tmp"; then
    echo "格式转化完成。"
  else
    echo "格式转化失败，详见 logs_literature_transer.tmp。"
    exit 1
  fi
}

run_llm_extraction() {
  LOG_SECTION "LLM" "执行 TAP 动力学信息抽取"
  local output_path
  output_path="$(python_config_value 'LLM_EXTRACTION_OUTPUT_PATH')"
  if python -m bensci.llm_info_extractor 2>&1 | tee "${PROJECT_ROOT}/logs_llm_extractor.tmp"; then
    if [ -n "${output_path}" ]; then
      echo "LLM 信息抽取完成，结果写入 ${output_path}。"
    else
      echo "LLM 信息抽取完成。"
    fi
  else
    echo "LLM 信息抽取失败，详见 logs_llm_extractor.tmp。"
    exit 1
  fi
}

run_metadata_filter() {
  LOG_SECTION "FILTER" "执行摘要筛选（未解基元动力学）"
  if python -m bensci.metadata_filter_utils 2>&1 | tee "${PROJECT_ROOT}/logs_metadata_filter.tmp"; then
    echo "元数据筛选完成，结果详见 logs_metadata_filter.tmp。"
  else
    echo "元数据筛选失败，详见 logs_metadata_filter.tmp。"
    exit 1
  fi
}

execute_doi_flow() {
  local doi_input="$1"
  local provider_override="$2"

  LOG_SECTION "DOI" "根据 DOI 下载全文"

  export BENF_DOI_LIST="${doi_input}"
  if [ "${provider_override}" != "auto" ]; then
    export BENF_PROVIDER_OVERRIDE="${provider_override}"
  else
    unset BENF_PROVIDER_OVERRIDE || true
  fi

  if python - <<'PY' 2>&1 | tee "${PROJECT_ROOT}/logs_doi_pipeline.tmp"; then
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

from bensci.config import ASSETS2_DIR
from bensci.fetcher_tools import get_fetcher  # noqa: F401
from bensci.literature_fetcher import guess_provider

raw = os.environ.get("BENF_DOI_LIST", "")
tokens = [token for token in re.split(r"[,\s]+", raw.strip()) if token]
if not tokens:
    print("未提供有效 DOI。")
    sys.exit(1)

override = os.environ.get("BENF_PROVIDER_OVERRIDE") or None

output_dir = Path(ASSETS2_DIR)

groups: dict[str, list[str]] = defaultdict(list)
for doi in tokens:
    provider = override or guess_provider(doi)
    groups[provider].append(doi)

success = 0
errors = 0

for provider, doi_list in groups.items():
    try:
        fetcher = get_fetcher(provider)
    except KeyError:
        print(f"[provider][error] 未注册 provider={provider}，跳过：{', '.join(doi_list)}")
        errors += len(doi_list)
        continue

    print(f"[provider] {provider} -> {len(doi_list)} 篇")
    for doi, path, error in fetcher.fetch_many(doi_list, output_dir):
        if error:
            print(f"[fetch][error] {doi} :: {error}")
            errors += 1
            continue

        print(f"[fetch][ok] {doi} -> {path}")
        success += 1

print(f"[summary] success={success} errors={errors}")
PY
    echo "DOI 处理完成，具体信息见 logs_doi_pipeline.tmp。"
  else
    echo "DOI 处理过程中发生错误，详见 logs_doi_pipeline.tmp。"
    exit 1
  fi
}

run_custom_pipeline() {
  LOG_SECTION "PIPELINE" "自定义流水线"
  show_pipeline_stage_menu
  local selected_raw
  selected_raw="$(read_stage_sequence "请输入要执行的阶段编号（空格分隔，顺序即执行顺序）")"
  local -a selected_stages
  read -r -a selected_stages <<< "${selected_raw}"

  local -A stage_index=()
  local idx
  for idx in "${!selected_stages[@]}"; do
    stage_index["${selected_stages[$idx]}"]="${idx}"
  done

  local run_metadata=0
  local run_filter=0
  local run_download=0
  local run_convert=0
  local run_llm=0

  if [[ -n "${stage_index[${STAGE_METADATA}]:-}" ]]; then
    run_metadata=1
  fi
  if [[ -n "${stage_index[${STAGE_FILTER}]:-}" ]]; then
    run_filter=1
  fi
  if [[ -n "${stage_index[${STAGE_DOWNLOAD}]:-}" ]]; then
    run_download=1
  fi
  if [[ -n "${stage_index[${STAGE_CONVERT}]:-}" ]]; then
    run_convert=1
  fi
  if [[ -n "${stage_index[${STAGE_LLM}]:-}" ]]; then
    run_llm=1
  fi

  if (( run_metadata == 1 )); then
    collect_metadata_config
  else
    METADATA_CFG_QUERY=""
    METADATA_CFG_MAX_RESULTS=""
    METADATA_CFG_PROVIDER_LIMIT=""
  fi

  local metadata_before_download=0
  if (( run_metadata == 1 && run_download == 1 )); then
    if (( stage_index[${STAGE_METADATA}] < stage_index[${STAGE_DOWNLOAD}] )); then
      metadata_before_download=1
    fi
  fi

  if (( run_download == 1 )); then
    collect_download_config "${metadata_before_download}"
  else
    DOWNLOAD_CFG_PROVIDER="auto"
    DOWNLOAD_CFG_MANUAL_FLOW=0
    DOWNLOAD_CFG_DOIS=""
  fi

  local metadata_csv_path
  metadata_csv_path="$(python_config_value 'METADATA_CSV_PATH')"
  local filtered_csv_path
  filtered_csv_path="$(python_config_value 'FILTERED_METADATA_CSV_PATH')"
  local current_csv_path="${metadata_csv_path}"

  local used_manual_download=0
  local stage
  for stage in "${selected_stages[@]}"; do
    case "${stage}" in
      "${STAGE_METADATA}")
        configure_api_keys
        run_metadata_stage "${METADATA_CFG_QUERY}" "${METADATA_CFG_MAX_RESULTS}" "${METADATA_CFG_PROVIDER_LIMIT}"
        current_csv_path="${metadata_csv_path}"
        ;;
      "${STAGE_FILTER}")
        run_metadata_filter
        if [ -n "${filtered_csv_path}" ] && [ -f "${filtered_csv_path}" ]; then
          current_csv_path="${filtered_csv_path}"
        fi
        ;;
      "${STAGE_DOWNLOAD}")
        configure_api_keys
        if (( DOWNLOAD_CFG_MANUAL_FLOW == 1 )); then
          execute_doi_flow "${DOWNLOAD_CFG_DOIS}" "${DOWNLOAD_CFG_PROVIDER}"
          used_manual_download=1
        else
          download_from_csv "${DOWNLOAD_CFG_PROVIDER}" "${current_csv_path}"
        fi
        ;;
      "${STAGE_CONVERT}")
        convert_fulltexts
        ;;
      "${STAGE_LLM}")
        run_llm_extraction
        ;;
      *)
        echo "未知阶段编号：${stage}"
        ;;
    esac
  done

  LOG_SECTION "SUMMARY" "流水线执行完成。相关日志："
  if (( run_metadata == 1 )); then
    echo "  - metadata: ${PROJECT_ROOT}/logs_metadata_fetcher.tmp"
  fi
  if (( run_filter == 1 )); then
    echo "  - filter: ${PROJECT_ROOT}/logs_metadata_filter.tmp"
  fi
  if (( run_download == 1 )); then
    if (( used_manual_download == 1 )); then
      echo "  - doi pipeline: ${PROJECT_ROOT}/logs_doi_pipeline.tmp"
    else
      echo "  - download: ${PROJECT_ROOT}/logs_literature_fetcher.tmp"
    fi
  fi
  if (( run_convert == 1 )); then
    echo "  - transform: ${PROJECT_ROOT}/logs_literature_transer.tmp"
  fi
  if (( run_llm == 1 )); then
    echo "  - llm: ${PROJECT_ROOT}/logs_llm_extractor.tmp"
  fi
}

main() {
  LOG_SECTION "INIT" "环境检查"
  command -v python >/dev/null 2>&1 || { echo "未找到 python，请先激活虚拟环境或安装 Python。"; exit 1; }
  ensure_env_file

  show_main_menu
  read -rp "请输入选项编号：" action

  case "${action}" in
    1)
      run_custom_pipeline
      ;;
    2)
      run_metadata_filter
      ;;
    3)
      configure_api_keys
      echo "API Key 已更新。"
      ;;
    4)
      echo "已取消操作。"
      exit 0
      ;;
    *)
      echo "无效选项：${action}"
      exit 1
      ;;
  esac
}

main "$@"
