const stepLabels = {
  metadata: "元数据聚合",
  filter: "摘要筛选",
  download: "下载全文",
  convert: "格式转化统一",
  llm: "LLM 抽取建表",
};

const ocrPresets = [
  {
    id: "custom",
    name: "自定义(不覆盖)",
    values: null,
  },
  {
    id: "auto_default",
    name: "自动(推荐)",
    values: {
      engine: "auto",
      dpi: 300,
      preprocess: "none",
      lang: "eng",
    },
  },
  {
    id: "paddle_en",
    name: "PaddleOCR 英文论文",
    values: {
      engine: "paddle",
      dpi: 300,
      preprocess: "grayscale",
      paddleLang: "en",
      paddleAngle: "true",
      paddleGpu: "false",
    },
  },
  {
    id: "easyocr_en",
    name: "EasyOCR 英文(轻量)",
    values: {
      engine: "easyocr",
      dpi: 300,
      preprocess: "grayscale",
      easyocrLangs: "en",
      easyocrGpu: "false",
    },
  },
  {
    id: "rapidocr_fast",
    name: "RapidOCR 快速",
    values: {
      engine: "rapidocr",
      dpi: 250,
      preprocess: "none",
    },
  },
  {
    id: "tesseract_cn",
    name: "Tesseract 中文+英文",
    values: {
      engine: "tesseract",
      dpi: 350,
      preprocess: "binarize",
      lang: "chi_sim+eng",
      tesseractConfig: "--psm 6",
    },
  },
];

const llmPresets = [
  {
    id: "tap_default",
    name: "TAP 动力学问题表",
    task: "聚焦未解决的基元动力学问题与 TAP 适用性，给出实验建议。",
    template: {
      article_title: "文献标题",
      doi: "文献 DOI",
      reaction_system: "具体反应或反应体系",
      reactants: "反应物",
      products: "产物",
      catalyst: "催化剂组成/材料",
      catalyst_form: "催化剂形态/载体/结构",
      active_site_or_mechanism: "活性位或机理要点",
      conditions: "重要条件",
      unresolved_elementary_kinetics_issue: "未解决的基元反应动力学问题",
      tap_relevance: "为什么适合用 TAP 研究",
      suggested_tap_experiments: "可执行的 TAP 实验设计要点",
      evidence_snippet: "支持性语句",
      source_blocks: "原 JSON 中的块编号列表",
      confidence_score: "0-1 自评置信度",
      verification_notes: "复核建议或线索",
    },
  },
  {
    id: "reaction_table",
    name: "反应体系/催化条件",
    task: "整理反应体系与催化条件，突出反应物、产物、催化剂组成及条件。",
    template: {
      article_title: "文献标题",
      doi: "文献 DOI",
      reaction_system: "反应体系/反应类型",
      reactants: "反应物",
      products: "主要产物",
      catalyst: "催化剂组成",
      catalyst_form: "催化剂形态/载体",
      conditions: "温度/压力/进料比例等",
      performance: "关键性能指标（转化率/选择性等）",
      evidence_snippet: "原文证据",
    },
  },
  {
    id: "kinetic_constants",
    name: "主客体常数/动力学参数",
    task: "提取动力学相关常数和表征参数，包括主客体常数、反应级数、活化能等。",
    template: {
      article_title: "文献标题",
      doi: "文献 DOI",
      reaction_system: "反应体系",
      kinetic_constants: "速率常数/主客体常数",
      activation_energy: "活化能",
      reaction_order: "反应级数",
      rate_law: "速率表达式",
      substrate_crystal_form: "底物晶形/结构",
      evidence_snippet: "原文证据",
      notes: "补充说明",
    },
  },
  {
    id: "abstract_translate",
    name: "摘要中文翻译 + 关键点",
    task: "输出摘要中文翻译，并提炼 3-5 条关键点与可能的催化反应。",
    template: {
      article_title: "文献标题",
      doi: "文献 DOI",
      abstract_cn: "摘要中文翻译",
      key_points: "关键点",
      possible_reactions: "可能的催化反应/体系",
      evidence_snippet: "原文证据",
    },
  },
  {
    id: "custom",
    name: "自定义(不覆盖)",
    task: "",
    template: null,
  },
];

const pipelineQueue = [];
const removedEnvKeys = new Set();
const statusBuffer = [];

const logEl = document.getElementById("pipelineLog");
const logSourceEl = document.getElementById("logSource");
const logRefreshBtn = document.getElementById("refreshLog");
const logStatusEl = document.getElementById("pipelineStatus");
const queueEl = document.getElementById("pipelineQueue");
const configSections = document.querySelectorAll(".config-section");
const pathMetadataCsvEl = document.getElementById("pathMetadataCsv");
const pathFilteredCsvEl = document.getElementById("pathFilteredCsv");
const pathAssets2El = document.getElementById("pathAssets2");
const pathXmlSourceEl = document.getElementById("pathXmlSource");
const pathBlocksOutputEl = document.getElementById("pathBlocksOutput");
const pathLlmOutputEl = document.getElementById("pathLlmOutput");

const stopOnErrorEl = document.getElementById("stopOnError");
const runPipelineBtn = document.getElementById("runPipeline");

const envListEl = document.getElementById("envList");
const overrideJsonEl = document.getElementById("overrideJson");

const metadataQueryEl = document.getElementById("metadataQuery");
const metadataMaxEl = document.getElementById("metadataMax");
const metadataProvidersEl = document.getElementById("metadataProviders");

const filterModelEl = document.getElementById("filterModel");
const filterProviderEl = document.getElementById("filterProvider");

const downloadProviderEl = document.getElementById("downloadProvider");
const downloadDoiEl = document.getElementById("downloadDoi");
const downloadCsvEl = document.getElementById("downloadCsv");
const downloadOutputEl = document.getElementById("downloadOutput");

const convertInputEl = document.getElementById("convertInput");
const convertOutputEl = document.getElementById("convertOutput");
const convertFormatEl = document.getElementById("convertFormat");
const ocrEngineEl = document.getElementById("ocrEngine");
const ocrPresetEl = document.getElementById("ocrPreset");
const ocrLangEl = document.getElementById("ocrLang");
const ocrDpiEl = document.getElementById("ocrDpi");
const ocrPreprocessEl = document.getElementById("ocrPreprocess");
const ocrTesseractConfigEl = document.getElementById("ocrTesseractConfig");
const ocrEasyocrLangsEl = document.getElementById("ocrEasyocrLangs");
const ocrEasyocrGpuEl = document.getElementById("ocrEasyocrGpu");
const ocrPaddleLangEl = document.getElementById("ocrPaddleLang");
const ocrPaddleAngleEl = document.getElementById("ocrPaddleAngle");
const ocrPaddleGpuEl = document.getElementById("ocrPaddleGpu");


const llmInputEl = document.getElementById("llmInput");
const llmOutputEl = document.getElementById("llmOutput");
const llmPresetEl = document.getElementById("llmPreset");
const llmTaskEl = document.getElementById("llmTask");
const llmOutputTemplateEl = document.getElementById("llmOutputTemplate");
const llmProviderEl = document.getElementById("llmProvider");
const llmModelEl = document.getElementById("llmModel");
const llmBaseUrlEl = document.getElementById("llmBaseUrl");
const llmChatPathEl = document.getElementById("llmChatPath");
const llmKeyEnvEl = document.getElementById("llmKeyEnv");
const llmKeyHeaderEl = document.getElementById("llmKeyHeader");
const llmKeyPrefixEl = document.getElementById("llmKeyPrefix");
const llmBlockLimitEl = document.getElementById("llmBlockLimit");
const llmTemperatureEl = document.getElementById("llmTemperature");
const llmTimeoutEl = document.getElementById("llmTimeout");

let cachedConfig = {};

function appendLog(text) {
  const timestamp = new Date().toLocaleTimeString();
  const line = `[${timestamp}] ${text}`;
  if (!logStatusEl) return;
  statusBuffer.push(line);
  if (statusBuffer.length > 5) {
    statusBuffer.shift();
  }
  logStatusEl.textContent = statusBuffer.join("\n");
}

async function apiGet(path) {
  const res = await fetch(path);
  return res.json();
}

async function apiPost(path, payload) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(errorText || `HTTP ${res.status}`);
  }
  return res.json();
}

function updateLogSources(sources, selected) {
  if (!logSourceEl) return;
  const current = selected || logSourceEl.value || "__all__";
  logSourceEl.innerHTML = "";

  const allOpt = document.createElement("option");
  allOpt.value = "__all__";
  allOpt.textContent = "全部";
  logSourceEl.appendChild(allOpt);

  (sources || []).forEach((source) => {
    const opt = document.createElement("option");
    opt.value = source;
    opt.textContent = source;
    logSourceEl.appendChild(opt);
  });

  const exists = Array.from(logSourceEl.options).some((opt) => opt.value === current);
  logSourceEl.value = exists ? current : "__all__";
}

async function loadLogs() {
  if (!logEl) return;
  const params = new URLSearchParams();
  const selected = logSourceEl ? logSourceEl.value : "__all__";
  if (selected && selected !== "__all__") {
    params.set("source", selected);
  }
  params.set("limit", "2000");
  const query = params.toString();
  const data = await apiGet(query ? `/api/logs?${query}` : "/api/logs");
  updateLogSources(data.sources || [], selected);
  logEl.textContent = (data.lines || []).join("\n");
  logEl.scrollTop = logEl.scrollHeight;
}

function renderQueue() {
  queueEl.innerHTML = "";
  pipelineQueue.forEach((step, index) => {
    const item = document.createElement("div");
    item.className = "queue-item";

    const label = document.createElement("span");
    label.textContent = `${index + 1}. ${stepLabels[step] || step}`;

    const actions = document.createElement("div");
    actions.className = "queue-actions";

    const upBtn = document.createElement("button");
    upBtn.textContent = "↑";
    upBtn.disabled = index === 0;
    upBtn.addEventListener("click", () => {
      if (index === 0) return;
      [pipelineQueue[index - 1], pipelineQueue[index]] = [pipelineQueue[index], pipelineQueue[index - 1]];
      renderQueue();
    });

    const downBtn = document.createElement("button");
    downBtn.textContent = "↓";
    downBtn.disabled = index === pipelineQueue.length - 1;
    downBtn.addEventListener("click", () => {
      if (index === pipelineQueue.length - 1) return;
      [pipelineQueue[index + 1], pipelineQueue[index]] = [pipelineQueue[index], pipelineQueue[index + 1]];
      renderQueue();
    });

    const removeBtn = document.createElement("button");
    removeBtn.textContent = "移除";
    removeBtn.addEventListener("click", () => {
      pipelineQueue.splice(index, 1);
      renderQueue();
    });

    actions.appendChild(upBtn);
    actions.appendChild(downBtn);
    actions.appendChild(removeBtn);
    item.appendChild(label);
    item.appendChild(actions);
    queueEl.appendChild(item);
  });
  updateConfigVisibility();
}

function addStep(step) {
  pipelineQueue.push(step);
  renderQueue();
}

function addEnvRow(key = "", value = "") {
  const row = document.createElement("div");
  row.className = "env-row";

  const keyInput = document.createElement("input");
  keyInput.value = key;
  keyInput.placeholder = "KEY";

  const valueInput = document.createElement("input");
  valueInput.value = value;
  valueInput.placeholder = "VALUE";

  const removeBtn = document.createElement("button");
  removeBtn.textContent = "删除";
  removeBtn.addEventListener("click", () => {
    const currentKey = keyInput.value.trim();
    if (currentKey) {
      removedEnvKeys.add(currentKey);
    }
    row.remove();
  });

  row.appendChild(keyInput);
  row.appendChild(valueInput);
  row.appendChild(removeBtn);
  envListEl.appendChild(row);
}

function collectEnvUpdates() {
  const updates = {};
  const rows = envListEl.querySelectorAll(".env-row");
  rows.forEach((row) => {
    const [keyInput, valueInput] = row.querySelectorAll("input");
    const key = keyInput.value.trim();
    if (!key) return;
    updates[key] = valueInput.value.trim();
  });
  removedEnvKeys.forEach((key) => {
    if (!(key in updates)) {
      updates[key] = null;
    }
  });
  return updates;
}

function populateProviders(selectEl, providers, extraOption) {
  selectEl.innerHTML = "";
  if (extraOption) {
    const opt = document.createElement("option");
    opt.value = extraOption.value;
    opt.textContent = extraOption.label;
    selectEl.appendChild(opt);
  }
  providers.forEach((provider) => {
    const opt = document.createElement("option");
    opt.value = provider;
    opt.textContent = provider;
    selectEl.appendChild(opt);
  });
}

function setMultiSelect(selectEl, values) {
  const normalized = new Set((values || []).map((v) => v.toString()));
  Array.from(selectEl.options).forEach((opt) => {
    opt.selected = normalized.has(opt.value);
  });
}

function populatePresetSelect(selectEl, presets) {
  selectEl.innerHTML = "";
  presets.forEach((preset) => {
    const opt = document.createElement("option");
    opt.value = preset.id;
    opt.textContent = preset.name;
    selectEl.appendChild(opt);
  });
}

function applyOcrPreset(presetId) {
  const preset = ocrPresets.find((item) => item.id === presetId);
  if (!preset || !preset.values) return;
  const values = preset.values;
  if (values.engine) ocrEngineEl.value = values.engine;
  if (values.lang) ocrLangEl.value = values.lang;
  if (values.dpi) ocrDpiEl.value = values.dpi;
  if (values.preprocess) ocrPreprocessEl.value = values.preprocess;
  if (values.tesseractConfig) ocrTesseractConfigEl.value = values.tesseractConfig;
  if (values.easyocrLangs) ocrEasyocrLangsEl.value = values.easyocrLangs;
  if (values.easyocrGpu) ocrEasyocrGpuEl.value = values.easyocrGpu;
  if (values.paddleLang) ocrPaddleLangEl.value = values.paddleLang;
  if (values.paddleAngle) ocrPaddleAngleEl.value = values.paddleAngle;
  if (values.paddleGpu) ocrPaddleGpuEl.value = values.paddleGpu;
}

function applyLlmPreset(presetId) {
  const preset = llmPresets.find((item) => item.id === presetId);
  if (!preset) return;
  if (preset.id === "custom") {
    return;
  }
  if (preset.task !== undefined) {
    llmTaskEl.value = preset.task || "";
  }
  if (preset.template) {
    llmOutputTemplateEl.value = JSON.stringify(preset.template, null, 2);
  }
}

function updateConfigVisibility() {
  const used = new Set(pipelineQueue);
  configSections.forEach((section) => {
    const always = section.dataset.always === "true";
    if (always) {
      section.classList.remove("is-hidden");
      return;
    }
    const raw = section.dataset.config || "";
    const keys = raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const shouldShow = keys.some((key) => used.has(key));
    if (shouldShow) {
      section.classList.remove("is-hidden");
    } else {
      section.classList.add("is-hidden");
    }
  });
}

function readOverrideJson() {
  const raw = overrideJsonEl.value.trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      return parsed;
    }
  } catch (err) {
    appendLog("Override JSON 无法解析，请先修正格式。");
  }
  return {};
}

function writeOverrideJson(data) {
  overrideJsonEl.value = JSON.stringify(data, null, 2);
}

async function runStage(stage) {
  appendLog(`开始执行 ${stepLabels[stage] || stage} ...`);
  let payload = {};
  let path = "";

  if (stage === "metadata") {
    payload = {
      query: metadataQueryEl.value.trim(),
      max_results: metadataMaxEl.value.trim(),
      providers: Array.from(metadataProvidersEl.selectedOptions).map((opt) => opt.value),
    };
    path = "/api/run/metadata";
  } else if (stage === "filter") {
    payload = {
      provider: filterProviderEl.value,
      model: filterModelEl.value.trim(),
    };
    path = "/api/run/filter";
  } else if (stage === "download") {
    payload = {
      provider: downloadProviderEl.value,
      doi: downloadDoiEl.value.trim(),
      input_csv: downloadCsvEl.value.trim(),
      output_dir: downloadOutputEl.value.trim(),
    };
    path = "/api/run/download";
  } else if (stage === "convert") {
    payload = {
      input_path: convertInputEl.value.trim(),
      output_dir: convertOutputEl.value.trim(),
      output_format: convertFormatEl.value,
      ocr_engine: ocrEngineEl.value,
      ocr_lang: ocrLangEl.value.trim(),
      ocr_dpi: ocrDpiEl.value.trim(),
      ocr_preprocess: ocrPreprocessEl.value,
      ocr_tesseract_config: ocrTesseractConfigEl.value.trim(),
      ocr_easyocr_langs: ocrEasyocrLangsEl.value.trim(),
      ocr_easyocr_gpu: ocrEasyocrGpuEl.value,
      ocr_paddle_lang: ocrPaddleLangEl.value.trim(),
      ocr_paddle_use_angle_cls: ocrPaddleAngleEl.value,
      ocr_paddle_use_gpu: ocrPaddleGpuEl.value,
    };
    path = "/api/run/convert";
  } else if (stage === "llm") {
    payload = {
      input_path: llmInputEl.value.trim(),
      output_path: llmOutputEl.value.trim(),
      task: llmTaskEl.value.trim(),
      output_template: llmOutputTemplateEl.value.trim(),
      provider: llmProviderEl.value,
      model: llmModelEl.value.trim(),
      base_url: llmBaseUrlEl.value.trim(),
      chat_path: llmChatPathEl.value.trim(),
      api_key_env: llmKeyEnvEl.value.trim(),
      api_key_header: llmKeyHeaderEl.value.trim(),
      api_key_prefix: llmKeyPrefixEl.value.trim(),
      block_limit: llmBlockLimitEl.value.trim(),
      temperature: llmTemperatureEl.value.trim(),
      timeout: llmTimeoutEl.value.trim(),
    };
    path = "/api/run/llm";
  } else {
    appendLog(`未知阶段: ${stage}`);
    return { ok: false };
  }

  const result = await apiPost(path, payload);
  try {
    await loadLogs();
  } catch (err) {
    appendLog(`日志刷新失败: ${err.message}`);
  }
  appendLog(`完成 ${stepLabels[stage] || stage} -> ${result.ok ? "OK" : "FAILED"}`);
  return result;
}

async function init() {
  const state = await apiGet("/api/state");
  cachedConfig = state.config || {};

  document.getElementById("projectRoot").textContent = state.paths.project_root || "--";
  document.getElementById("envPath").textContent = state.paths.env_file || "--";
  document.getElementById("overridePath").textContent = state.paths.override_file || "--";

  const knownEnvKeys = [
    "ELSEVIER_API_KEY",
    "SPRINGER_OPEN_ACCESS_KEY",
    "SPRINGER_META_API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "CHAT_ANYWHERE_API_KEY",
    "DASHSCOPE_API_KEY",
    "DEEPSEEK_API_KEY",
    "MOONSHOT_API_KEY",
    "ZHIPU_API_KEY",
    "BAICHUAN_API_KEY",
    "MINIMAX_API_KEY",
  ];

  const envValues = state.env || {};
  envListEl.innerHTML = "";
  knownEnvKeys.forEach((key) => {
    addEnvRow(key, envValues[key] || "");
  });
  Object.keys(envValues)
    .filter((key) => !knownEnvKeys.includes(key))
    .forEach((key) => addEnvRow(key, envValues[key] || ""));

  overrideJsonEl.value = JSON.stringify(state.override || {}, null, 2);

  metadataQueryEl.value = cachedConfig.METADATA_DEFAULT_QUERY || "";
  metadataMaxEl.value = cachedConfig.METADATA_MAX_RESULTS || "";
  populateProviders(metadataProvidersEl, state.providers.metadata || []);
  setMultiSelect(metadataProvidersEl, cachedConfig.METADATA_PROVIDERS || []);

  populateProviders(filterProviderEl, state.providers.llm || []);
  filterProviderEl.value = cachedConfig.METADATA_FILTER_PROVIDER || "";
  filterModelEl.value = cachedConfig.METADATA_FILTER_MODEL || "";

  populatePresetSelect(ocrPresetEl, ocrPresets);
  ocrPresetEl.value = "custom";

  populateProviders(downloadProviderEl, state.providers.download || [], {
    value: "auto",
    label: "auto",
  });
  downloadProviderEl.value = "auto";
  downloadCsvEl.value = cachedConfig.METADATA_CSV_PATH || "";
  downloadOutputEl.value = cachedConfig.ASSETS2_DIR || "";

  convertInputEl.value = cachedConfig.XML_SOURCE_DIR || cachedConfig.ASSETS2_DIR || "";
  convertOutputEl.value = cachedConfig.BLOCKS_OUTPUT_DIR || "";
  if (cachedConfig.TRANSER_OUTPUT_FORMAT) {
    convertFormatEl.value = cachedConfig.TRANSER_OUTPUT_FORMAT;
  }
  ocrEngineEl.value = cachedConfig.OCR_ENGINE || "auto";
  ocrLangEl.value = cachedConfig.OCR_LANG || "";
  ocrDpiEl.value = cachedConfig.OCR_DPI || "";
  ocrPreprocessEl.value = cachedConfig.OCR_PREPROCESS || "none";
  ocrTesseractConfigEl.value = cachedConfig.OCR_TESSERACT_CONFIG || "";
  if (Array.isArray(cachedConfig.OCR_EASYOCR_LANGS)) {
    ocrEasyocrLangsEl.value = cachedConfig.OCR_EASYOCR_LANGS.join(",");
  } else if (typeof cachedConfig.OCR_EASYOCR_LANGS === "string") {
    ocrEasyocrLangsEl.value = cachedConfig.OCR_EASYOCR_LANGS;
  } else {
    ocrEasyocrLangsEl.value = "";
  }
  if (typeof cachedConfig.OCR_EASYOCR_GPU === "boolean") {
    ocrEasyocrGpuEl.value = cachedConfig.OCR_EASYOCR_GPU ? "true" : "false";
  } else {
    ocrEasyocrGpuEl.value = "";
  }
  ocrPaddleLangEl.value = cachedConfig.OCR_PADDLE_LANG || "";
  if (typeof cachedConfig.OCR_PADDLE_USE_ANGLE_CLS === "boolean") {
    ocrPaddleAngleEl.value = cachedConfig.OCR_PADDLE_USE_ANGLE_CLS ? "true" : "false";
  } else {
    ocrPaddleAngleEl.value = "";
  }
  if (typeof cachedConfig.OCR_PADDLE_USE_GPU === "boolean") {
    ocrPaddleGpuEl.value = cachedConfig.OCR_PADDLE_USE_GPU ? "true" : "false";
  } else {
    ocrPaddleGpuEl.value = "";
  }

  populateProviders(llmProviderEl, state.providers.llm || []);
  llmProviderEl.value = cachedConfig.LLM_EXTRACTION_PROVIDER || "";
  llmModelEl.value = cachedConfig.LLM_EXTRACTION_MODEL || "";
  llmBaseUrlEl.value = cachedConfig.LLM_EXTRACTION_BASE_URL || "";
  llmChatPathEl.value = cachedConfig.LLM_EXTRACTION_CHAT_PATH || "";
  llmKeyEnvEl.value = cachedConfig.LLM_EXTRACTION_API_KEY_ENV || "";
  llmKeyHeaderEl.value = cachedConfig.LLM_EXTRACTION_API_KEY_HEADER || "";
  llmKeyPrefixEl.value = cachedConfig.LLM_EXTRACTION_API_KEY_PREFIX || "";
  llmBlockLimitEl.value = cachedConfig.LLM_EXTRACTION_BLOCK_LIMIT || "";
  llmTemperatureEl.value = cachedConfig.LLM_EXTRACTION_TEMPERATURE || "";
  llmTimeoutEl.value = cachedConfig.LLM_EXTRACTION_TIMEOUT || "";
  llmInputEl.value = cachedConfig.BLOCKS_OUTPUT_DIR || "";
  llmOutputEl.value = cachedConfig.LLM_EXTRACTION_OUTPUT_PATH || "";
  llmTaskEl.value = cachedConfig.LLM_EXTRACTION_TASK_PROMPT || "";
  if (cachedConfig.LLM_EXTRACTION_OUTPUT_TEMPLATE) {
    llmOutputTemplateEl.value = JSON.stringify(cachedConfig.LLM_EXTRACTION_OUTPUT_TEMPLATE, null, 2);
  }
  populatePresetSelect(llmPresetEl, llmPresets);
  llmPresetEl.value = "custom";

  pathMetadataCsvEl.value = cachedConfig.METADATA_CSV_PATH || "";
  pathFilteredCsvEl.value = cachedConfig.FILTERED_METADATA_CSV_PATH || "";
  pathAssets2El.value = cachedConfig.ASSETS2_DIR || "";
  pathXmlSourceEl.value = cachedConfig.XML_SOURCE_DIR || "";
  pathBlocksOutputEl.value = cachedConfig.BLOCKS_OUTPUT_DIR || "";
  pathLlmOutputEl.value = cachedConfig.LLM_EXTRACTION_OUTPUT_PATH || "";
  updateConfigVisibility();
  try {
    await loadLogs();
  } catch (err) {
    appendLog(`日志加载失败: ${err.message}`);
  }
}


document.querySelectorAll(".step-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    addStep(btn.dataset.step);
  });
});

ocrPresetEl.addEventListener("change", () => {
  applyOcrPreset(ocrPresetEl.value);
});

llmPresetEl.addEventListener("change", () => {
  applyLlmPreset(llmPresetEl.value);
});

runPipelineBtn.addEventListener("click", async () => {
  if (pipelineQueue.length === 0) {
    appendLog("队列为空，请先添加阶段。");
    return;
  }
  runPipelineBtn.disabled = true;
  appendLog("开始执行队列...");
  for (const step of pipelineQueue) {
    try {
      const result = await runStage(step);
      if (!result.ok && stopOnErrorEl.checked) {
        appendLog("遇到错误，已停止队列。");
        break;
      }
    } catch (err) {
      appendLog(`执行异常: ${err.message}`);
      if (stopOnErrorEl.checked) {
        break;
      }
    }
  }
  appendLog("队列执行结束。");
  runPipelineBtn.disabled = false;
});


document.querySelectorAll(".run-btn").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const stage = btn.dataset.run;
    if (!stage) return;
    btn.disabled = true;
    try {
      await runStage(stage);
    } catch (err) {
      appendLog(`执行异常: ${err.message}`);
    }
    btn.disabled = false;
  });
});


document.getElementById("addEnv").addEventListener("click", () => addEnvRow());

document.getElementById("saveEnv").addEventListener("click", async () => {
  const updates = collectEnvUpdates();
  try {
    await apiPost("/api/env", { values: updates });
    removedEnvKeys.clear();
    appendLog("ENV 已保存。");
  } catch (err) {
    appendLog(`ENV 保存失败: ${err.message}`);
  }
});


document.getElementById("savePaths").addEventListener("click", async () => {
  const overrides = readOverrideJson();
  const updates = {
    METADATA_CSV_PATH: pathMetadataCsvEl.value.trim() || null,
    FILTERED_METADATA_CSV_PATH: pathFilteredCsvEl.value.trim() || null,
    ASSETS2_DIR: pathAssets2El.value.trim() || null,
    XML_SOURCE_DIR: pathXmlSourceEl.value.trim() || null,
    BLOCKS_OUTPUT_DIR: pathBlocksOutputEl.value.trim() || null,
    LLM_EXTRACTION_OUTPUT_PATH: pathLlmOutputEl.value.trim() || null,
  };
  Object.entries(updates).forEach(([key, value]) => {
    if (!value) {
      delete overrides[key];
    } else {
      overrides[key] = value;
    }
  });

  try {
    await apiPost("/api/config", { overrides });
    writeOverrideJson(overrides);
    appendLog("路径配置已保存到 Override。");
  } catch (err) {
    appendLog(`路径保存失败: ${err.message}`);
  }
});


document.getElementById("saveOverride").addEventListener("click", async () => {
  let overrides = {};
  const raw = overrideJsonEl.value.trim();
  if (raw) {
    try {
      overrides = JSON.parse(raw);
    } catch (err) {
      appendLog("Override JSON 无法解析，请检查格式。");
      return;
    }
  }
  try {
    await apiPost("/api/config", { overrides });
    appendLog("Override 已保存。下次任务调用将自动生效。");
  } catch (err) {
    appendLog(`Override 保存失败: ${err.message}`);
  }
});


document.getElementById("useFiltered").addEventListener("click", () => {
  if (cachedConfig.FILTERED_METADATA_CSV_PATH) {
    downloadCsvEl.value = cachedConfig.FILTERED_METADATA_CSV_PATH;
  }
});

if (logSourceEl) {
  logSourceEl.addEventListener("change", () => {
    loadLogs().catch((err) => appendLog(`日志刷新失败: ${err.message}`));
  });
}
if (logRefreshBtn) {
  logRefreshBtn.addEventListener("click", () => {
    loadLogs().catch((err) => appendLog(`日志刷新失败: ${err.message}`));
  });
}

init().catch((err) => {
  appendLog(`初始化失败: ${err.message}`);
});
