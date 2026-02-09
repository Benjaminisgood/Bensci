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
const LOG_POLL_INTERVAL_MS = 1000;
const logStreamState = {
  running: false,
  pending: false,
  timer: null,
  lastLine: null,
  source: "__all__",
  minTimestamp: null,
};

const logEl = document.getElementById("pipelineLog");
const logSourceEl = document.getElementById("logSource");
const logRefreshBtn = document.getElementById("refreshLog");
const logStatusEl = document.getElementById("pipelineStatus");
const queueEl = document.getElementById("pipelineQueue");
const configSections = document.querySelectorAll(".config-section");
const metadataOutputEl = document.getElementById("metadataOutput");
const filterInputEl = document.getElementById("filterInput");
const filterOutputEl = document.getElementById("filterOutput");

const stopOnErrorEl = document.getElementById("stopOnError");
const runPipelineBtn = document.getElementById("runPipeline");

const envListEl = document.getElementById("envList");
const envEmptyEl = document.getElementById("envEmpty");
const overrideJsonEl = document.getElementById("overrideJson");
const exportConfigBtn = document.getElementById("exportConfig");
const saveLlmQuickBtn = document.getElementById("saveLlmQuick");

const llmQuickProviderEl = document.getElementById("llmQuickProvider");
const llmQuickModelEl = document.getElementById("llmQuickModel");
const llmQuickKeyEl = document.getElementById("llmQuickKey");
const llmQuickEnvEl = document.getElementById("llmQuickEnv");
const llmQuickBaseUrlEl = document.getElementById("llmQuickBaseUrl");
const llmQuickChatPathEl = document.getElementById("llmQuickChatPath");

const metadataQueryEl = document.getElementById("metadataQuery");
const metadataMaxEl = document.getElementById("metadataMax");
const metadataProvidersEl = document.getElementById("metadataProviders");

const filterModelEl = document.getElementById("filterModel");
const filterProviderEl = document.getElementById("filterProvider");
const filterSystemPromptEl = document.getElementById("filterSystemPrompt");
const filterUserPromptEl = document.getElementById("filterUserPrompt");

const downloadProviderEl = document.getElementById("downloadProvider");
const downloadDoiEl = document.getElementById("downloadDoi");
const downloadCsvEl = document.getElementById("downloadCsv");
const downloadOutputEl = document.getElementById("downloadOutput");
const downloadPriorityListEl = document.getElementById("downloadPriorityList");
const downloadPrioritySaveBtn = document.getElementById("downloadPrioritySave");
const downloadPriorityResetBtn = document.getElementById("downloadPriorityReset");

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
const llmSystemPromptEl = document.getElementById("llmSystemPrompt");
const llmUserPromptEl = document.getElementById("llmUserPrompt");
const llmAutoSchemaEl = document.getElementById("llmAutoSchema");
const llmSchemaSampleSizeEl = document.getElementById("llmSchemaSampleSize");
const llmSchemaMaxFieldsEl = document.getElementById("llmSchemaMaxFields");
const llmProviderEl = document.getElementById("llmProvider");
const llmModelEl = document.getElementById("llmModel");
const llmBaseUrlEl = document.getElementById("llmBaseUrl");
const llmChatPathEl = document.getElementById("llmChatPath");
const llmKeyEnvEl = document.getElementById("llmKeyEnv");
const llmKeyHeaderEl = document.getElementById("llmKeyHeader");
const llmKeyPrefixEl = document.getElementById("llmKeyPrefix");
const llmBlockLimitEl = document.getElementById("llmBlockLimit");
const llmCharLimitEl = document.getElementById("llmCharLimit");
const llmTemperatureEl = document.getElementById("llmTemperature");
const llmTimeoutEl = document.getElementById("llmTimeout");

let cachedConfig = {};
let cachedEnv = {};
let cachedPaths = {};
let cachedStageDefaults = {};
let llmProviderPresets = {};
let downloadProviders = [];

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

function parseLogTimestamp(line) {
  const match = line.match(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}),(\d{3})/);
  if (!match) return null;
  const stamp = `${match[1]}T${match[2]}.${match[3]}`;
  const date = new Date(stamp);
  return Number.isNaN(date.getTime()) ? null : date.getTime();
}

function filterLogLines(lines) {
  const minTimestamp = logStreamState.minTimestamp;
  if (!minTimestamp) return lines;
  return lines.filter((line) => {
    const ts = parseLogTimestamp(line);
    if (!ts) return true;
    return ts >= minTimestamp;
  });
}

async function fetchLogs({ source, limit = 2000 } = {}) {
  const params = new URLSearchParams();
  if (source && source !== "__all__") {
    params.set("source", source);
  }
  if (limit) {
    params.set("limit", String(limit));
  }
  const query = params.toString();
  return apiGet(query ? `/api/logs?${query}` : "/api/logs");
}

function clearLogView() {
  if (!logEl) return;
  logEl.textContent = "";
  logEl.scrollTop = 0;
}

function appendLogLines(lines) {
  if (!logEl || !lines.length) return;
  const current = logEl.textContent;
  const text = lines.join("\n");
  logEl.textContent = current ? `${current}\n${text}` : text;
  logEl.scrollTop = logEl.scrollHeight;
}

function getNewLogLines(lines) {
  if (!logStreamState.lastLine) {
    return lines;
  }
  const idx = lines.lastIndexOf(logStreamState.lastLine);
  if (idx === -1) {
    return lines;
  }
  return lines.slice(idx + 1);
}

async function pollLogStream() {
  if (!logStreamState.running || logStreamState.pending || !logEl) return;
  logStreamState.pending = true;
  try {
    const data = await fetchLogs({ source: logStreamState.source, limit: 2000 });
    updateLogSources(data.sources || [], logStreamState.source);
    const filtered = filterLogLines(data.lines || []);
    const newLines = getNewLogLines(filtered);
    appendLogLines(newLines);
    if (filtered.length) {
      logStreamState.lastLine = filtered[filtered.length - 1];
    }
  } catch (err) {
    appendLog(`日志刷新失败: ${err.message}`);
  } finally {
    logStreamState.pending = false;
  }
}

async function startLogStream({ reset = false } = {}) {
  if (!logEl) return;
  stopLogStream();
  logStreamState.running = true;
  logStreamState.pending = false;
  logStreamState.source = logSourceEl ? logSourceEl.value : "__all__";
  logStreamState.lastLine = null;
  if (reset) {
    clearLogView();
  } else {
    const data = await fetchLogs({ source: logStreamState.source, limit: 2000 });
    updateLogSources(data.sources || [], logStreamState.source);
    const filtered = filterLogLines(data.lines || []);
    logEl.textContent = filtered.join("\n");
    logEl.scrollTop = logEl.scrollHeight;
    if (filtered.length) {
      logStreamState.lastLine = filtered[filtered.length - 1];
    }
  }
  await pollLogStream();
  logStreamState.timer = setInterval(pollLogStream, LOG_POLL_INTERVAL_MS);
}

function stopLogStream() {
  if (logStreamState.timer) {
    clearInterval(logStreamState.timer);
    logStreamState.timer = null;
  }
  logStreamState.running = false;
  logStreamState.pending = false;
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
  const selected = logSourceEl ? logSourceEl.value : "__all__";
  const data = await fetchLogs({ source: selected, limit: 2000 });
  updateLogSources(data.sources || [], selected);
  const filtered = filterLogLines(data.lines || []);
  logEl.textContent = filtered.join("\n");
  logEl.scrollTop = logEl.scrollHeight;
  if (filtered.length) {
    logStreamState.lastLine = filtered[filtered.length - 1];
  }
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

function updateEnvEmptyState() {
  if (!envEmptyEl || !envListEl) return;
  const hasRows = envListEl.querySelector(".env-row");
  envEmptyEl.style.display = hasRows ? "none" : "block";
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
    updateEnvEmptyState();
  });

  row.appendChild(keyInput);
  row.appendChild(valueInput);
  row.appendChild(removeBtn);
  envListEl.appendChild(row);
  updateEnvEmptyState();
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

function getDownloadProviderMeta(provider) {
  const key = (provider || "").toLowerCase();
  if (key === "elsevier") {
    return { requiredEnv: "ELSEVIER_API_KEY", optionalEnv: null, label: "Elsevier" };
  }
  if (key === "springer") {
    return { requiredEnv: "SPRINGER_OPEN_ACCESS_KEY", optionalEnv: null, label: "Springer" };
  }
  if (key === "acs") {
    return { requiredEnv: null, optionalEnv: "ACS_API_KEY", label: "ACS" };
  }
  if (key === "wiley") {
    return { requiredEnv: null, optionalEnv: null, label: "Wiley" };
  }
  if (key === "rsc") {
    return { requiredEnv: null, optionalEnv: null, label: "RSC" };
  }
  if (key === "scihub") {
    return { requiredEnv: null, optionalEnv: null, label: "Sci-Hub" };
  }
  return { requiredEnv: null, optionalEnv: null, label: provider };
}

function buildDownloadBadge(provider) {
  const meta = getDownloadProviderMeta(provider);
  const requiredEnv = meta.requiredEnv;
  const optionalEnv = meta.optionalEnv;
  if (requiredEnv) {
    const hasKey = !!cachedEnv[requiredEnv];
    return {
      className: hasKey ? "ok" : "warn",
      text: hasKey ? "API 已配置" : "缺少 API",
      title: `需要 ${requiredEnv}`,
      usable: hasKey,
    };
  }
  if (optionalEnv) {
    const hasKey = !!cachedEnv[optionalEnv];
    return {
      className: hasKey ? "ok" : "neutral",
      text: hasKey ? "API 已配置" : "可选 API",
      title: `可选 ${optionalEnv}`,
      usable: true,
    };
  }
  return {
    className: "neutral",
    text: "无需 API",
    title: "无需 API",
    usable: true,
  };
}

function updatePriorityItemState(item) {
  const checkbox = item.querySelector('input[type="checkbox"]');
  if (!checkbox) return;
  item.classList.toggle("is-disabled", !checkbox.checked);
}

function renderDownloadPriorityList(providers, configuredOrder) {
  if (!downloadPriorityListEl) return;
  const available = (providers || []).filter((name) => name && name !== "scihub");
  const normalizedOrder = Array.isArray(configuredOrder)
    ? configuredOrder.map((name) => name.toString().toLowerCase())
    : [];
  const activeOrder = normalizedOrder.filter((name) => available.includes(name));
  const baseOrder = activeOrder.length > 0 ? activeOrder : [];
  const remaining = available.filter((name) => !baseOrder.includes(name));
  const order = baseOrder.concat(remaining);
  const enabledSet =
    activeOrder.length > 0 ? new Set(activeOrder) : new Set(order);

  downloadPriorityListEl.innerHTML = "";
  order.forEach((provider) => {
    const badge = buildDownloadBadge(provider);
    const item = document.createElement("div");
    item.className = "priority-item";
    item.dataset.provider = provider;

    const name = document.createElement("div");
    name.className = "priority-name";
    name.textContent = provider;

    const meta = document.createElement("div");
    meta.className = "priority-meta";

    const badgeEl = document.createElement("span");
    badgeEl.className = `badge ${badge.className}`;
    badgeEl.textContent = badge.text;
    badgeEl.title = badge.title;
    meta.appendChild(badgeEl);

    const toggle = document.createElement("label");
    toggle.className = "priority-toggle";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = enabledSet.has(provider);
    checkbox.addEventListener("change", () => updatePriorityItemState(item));
    toggle.appendChild(checkbox);
    toggle.appendChild(document.createTextNode("启用"));
    meta.appendChild(toggle);

    const actions = document.createElement("div");
    actions.className = "priority-actions";
    const upBtn = document.createElement("button");
    upBtn.className = "ghost";
    upBtn.type = "button";
    upBtn.textContent = "上移";
    upBtn.addEventListener("click", () => {
      const prev = item.previousElementSibling;
      if (prev) {
        downloadPriorityListEl.insertBefore(item, prev);
      }
    });
    const downBtn = document.createElement("button");
    downBtn.className = "ghost";
    downBtn.type = "button";
    downBtn.textContent = "下移";
    downBtn.addEventListener("click", () => {
      const next = item.nextElementSibling;
      if (next) {
        downloadPriorityListEl.insertBefore(next, item);
      }
    });
    actions.appendChild(upBtn);
    actions.appendChild(downBtn);

    item.appendChild(name);
    item.appendChild(meta);
    item.appendChild(actions);
    updatePriorityItemState(item);
    downloadPriorityListEl.appendChild(item);
  });
}

function refreshDownloadPriorityBadges() {
  if (!downloadPriorityListEl) return;
  const items = downloadPriorityListEl.querySelectorAll(".priority-item");
  items.forEach((item) => {
    const provider = item.dataset.provider || "";
    const badge = buildDownloadBadge(provider);
    const badgeEl = item.querySelector(".badge");
    if (!badgeEl) return;
    badgeEl.className = `badge ${badge.className}`;
    badgeEl.textContent = badge.text;
    badgeEl.title = badge.title;
  });
}

function collectDownloadPriorityOrder() {
  if (!downloadPriorityListEl) return [];
  const items = downloadPriorityListEl.querySelectorAll(".priority-item");
  const order = [];
  items.forEach((item) => {
    const checkbox = item.querySelector('input[type="checkbox"]');
    if (!checkbox || !checkbox.checked) return;
    const provider = item.dataset.provider;
    if (provider) {
      order.push(provider);
    }
  });
  return order;
}

async function saveDownloadPriority(button) {
  const overrides = parseOverrideJson();
  if (overrides === null) {
    return;
  }
  const order = collectDownloadPriorityOrder();
  if (order.length > 0) {
    overrides.LITERATURE_FETCHER_PROVIDER_ORDER = order;
  } else {
    delete overrides.LITERATURE_FETCHER_PROVIDER_ORDER;
  }
  if (button) button.disabled = true;
  try {
    await apiPost("/api/config", { overrides });
    writeOverrideJson(overrides);
    cachedConfig.LITERATURE_FETCHER_PROVIDER_ORDER = order;
    appendLog("已保存下载优先级。");
  } catch (err) {
    appendLog(`优先级保存失败: ${err.message}`);
  } finally {
    if (button) button.disabled = false;
  }
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

function ensureOption(selectEl, value) {
  if (!selectEl || !value) return;
  const exists = Array.from(selectEl.options).some((opt) => opt.value === value);
  if (!exists) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    selectEl.appendChild(opt);
  }
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

function applyLlmQuickPreset(provider) {
  if (!llmQuickEnvEl || !llmQuickBaseUrlEl || !llmQuickChatPathEl) return null;
  const preset = llmProviderPresets[provider];
  if (!preset) {
    llmQuickEnvEl.value = "";
    llmQuickBaseUrlEl.value = "";
    llmQuickChatPathEl.value = "";
    if (llmQuickKeyEl) {
      llmQuickKeyEl.value = "";
    }
    return null;
  }
  llmQuickEnvEl.value = preset.api_key_env || "";
  llmQuickBaseUrlEl.value = preset.base_url || "";
  llmQuickChatPathEl.value = preset.chat_path || "";
  if (llmQuickKeyEl) {
    const envKey = preset.api_key_env;
    llmQuickKeyEl.value = envKey && cachedEnv[envKey] ? cachedEnv[envKey] : "";
  }
  return preset;
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

function parseOverrideJson() {
  const raw = overrideJsonEl.value.trim();
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      return parsed;
    }
  } catch (err) {
    appendLog("Override JSON 无法解析，请先修正格式。");
    return null;
  }
  appendLog("Override JSON 必须是一个对象。");
  return null;
}

function writeOverrideJson(data) {
  overrideJsonEl.value = JSON.stringify(data, null, 2);
}

function normalizeStageDefaults(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return {};
  }
  const normalized = {};
  Object.entries(raw).forEach(([stage, config]) => {
    if (config && typeof config === "object" && !Array.isArray(config)) {
      normalized[stage] = { ...config };
    }
  });
  return normalized;
}

function collectStagePathConfig(stage) {
  const stageFields = {
    metadata: { output_csv: metadataOutputEl },
    filter: { input_csv: filterInputEl, output_csv: filterOutputEl },
    download: { input_csv: downloadCsvEl, output_dir: downloadOutputEl },
    convert: { input_path: convertInputEl, output_dir: convertOutputEl },
    llm: { input_path: llmInputEl, output_path: llmOutputEl },
  };
  const fields = stageFields[stage];
  if (!fields) return null;
  const payload = {};
  Object.entries(fields).forEach(([key, el]) => {
    if (!el) return;
    const value = el.value.trim();
    if (value) {
      payload[key] = value;
    }
  });
  return payload;
}

async function saveStagePaths(stage, button) {
  const overrides = parseOverrideJson();
  if (overrides === null) {
    return;
  }
  const stageDefaults = normalizeStageDefaults(overrides.STAGE_CONFIGS);
  const pathConfig = collectStagePathConfig(stage);
  if (pathConfig && Object.keys(pathConfig).length > 0) {
    stageDefaults[stage] = pathConfig;
  } else {
    delete stageDefaults[stage];
  }

  if (Object.keys(stageDefaults).length === 0) {
    delete overrides.STAGE_CONFIGS;
  } else {
    overrides.STAGE_CONFIGS = stageDefaults;
  }

  if (button) button.disabled = true;
  try {
    await apiPost("/api/config", { overrides });
    writeOverrideJson(overrides);
    cachedStageDefaults = stageDefaults;
    appendLog(`已保存 ${stepLabels[stage] || stage} 的路径配置。`);
  } catch (err) {
    appendLog(`路径保存失败: ${err.message}`);
  } finally {
    if (button) button.disabled = false;
  }
}

function buildEnvSnapshot() {
  const snapshot = { ...cachedEnv };
  const updates = collectEnvUpdates();
  Object.entries(updates).forEach(([key, value]) => {
    if (value === null || value === "") {
      delete snapshot[key];
    } else {
      snapshot[key] = value;
    }
  });
  if (llmQuickEnvEl && llmQuickKeyEl) {
    const envKey = llmQuickEnvEl.value.trim();
    const envValue = llmQuickKeyEl.value.trim();
    if (envKey && envValue) {
      snapshot[envKey] = envValue;
    }
  }
  return snapshot;
}

function collectUiSnapshot() {
  return {
    llm_quick: {
      provider: llmQuickProviderEl ? llmQuickProviderEl.value : "",
      model: llmQuickModelEl ? llmQuickModelEl.value.trim() : "",
      api_key_env: llmQuickEnvEl ? llmQuickEnvEl.value.trim() : "",
      base_url: llmQuickBaseUrlEl ? llmQuickBaseUrlEl.value.trim() : "",
      chat_path: llmQuickChatPathEl ? llmQuickChatPathEl.value.trim() : "",
    },
    paths: {
      metadata_output_csv: metadataOutputEl.value.trim(),
      filter_input_csv: filterInputEl.value.trim(),
      filter_output_csv: filterOutputEl.value.trim(),
      download_input_csv: downloadCsvEl.value.trim(),
      download_output_dir: downloadOutputEl.value.trim(),
      convert_input_path: convertInputEl.value.trim(),
      convert_output_dir: convertOutputEl.value.trim(),
      llm_input_path: llmInputEl.value.trim(),
      llm_output_path: llmOutputEl.value.trim(),
    },
    metadata: {
      query: metadataQueryEl.value.trim(),
      max_results: metadataMaxEl.value.trim(),
      providers: Array.from(metadataProvidersEl.selectedOptions).map((opt) => opt.value),
      output_csv: metadataOutputEl.value.trim(),
    },
    filter: {
      provider: filterProviderEl.value,
      model: filterModelEl.value.trim(),
      input_csv: filterInputEl.value.trim(),
      output_csv: filterOutputEl.value.trim(),
      system_prompt: filterSystemPromptEl ? filterSystemPromptEl.value.trim() : "",
      user_prompt_template: filterUserPromptEl ? filterUserPromptEl.value.trim() : "",
    },
    download: {
      provider: downloadProviderEl.value,
      doi: downloadDoiEl.value.trim(),
      input_csv: downloadCsvEl.value.trim(),
      output_dir: downloadOutputEl.value.trim(),
    },
    convert: {
      input_path: convertInputEl.value.trim(),
      output_dir: convertOutputEl.value.trim(),
      output_format: convertFormatEl.value,
      ocr: {
        engine: ocrEngineEl.value,
        preset: ocrPresetEl.value,
        lang: ocrLangEl.value.trim(),
        dpi: ocrDpiEl.value.trim(),
        preprocess: ocrPreprocessEl.value,
        tesseract_config: ocrTesseractConfigEl.value.trim(),
        easyocr_langs: ocrEasyocrLangsEl.value.trim(),
        easyocr_gpu: ocrEasyocrGpuEl.value,
        paddle_lang: ocrPaddleLangEl.value.trim(),
        paddle_use_angle_cls: ocrPaddleAngleEl.value,
        paddle_use_gpu: ocrPaddleGpuEl.value,
      },
    },
    llm: {
      preset: llmPresetEl.value,
      task: llmTaskEl.value.trim(),
      output_template: llmOutputTemplateEl.value.trim(),
      system_prompt: llmSystemPromptEl ? llmSystemPromptEl.value.trim() : "",
      user_prompt_template: llmUserPromptEl ? llmUserPromptEl.value.trim() : "",

      auto_schema_mode: llmAutoSchemaEl ? llmAutoSchemaEl.value : "auto",
      schema_sample_size: llmSchemaSampleSizeEl ? llmSchemaSampleSizeEl.value.trim() : "",
      schema_max_fields: llmSchemaMaxFieldsEl ? llmSchemaMaxFieldsEl.value.trim() : "",
      input_path: llmInputEl.value.trim(),
      output_path: llmOutputEl.value.trim(),
      provider: llmProviderEl.value,
      model: llmModelEl.value.trim(),
      base_url: llmBaseUrlEl.value.trim(),
      chat_path: llmChatPathEl.value.trim(),
      api_key_env: llmKeyEnvEl.value.trim(),
      api_key_header: llmKeyHeaderEl.value.trim(),
      api_key_prefix: llmKeyPrefixEl.value.trim(),
      block_limit: llmBlockLimitEl.value.trim(),
      char_limit: llmCharLimitEl ? llmCharLimitEl.value.trim() : "",
      temperature: llmTemperatureEl.value.trim(),
      timeout: llmTimeoutEl.value.trim(),
    },
  };
}

function triggerJsonDownload(payload) {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const filename = `bensci-config-${stamp}.json`;
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function runStage(stage) {
  appendLog(`开始执行 ${stepLabels[stage] || stage} ...`);
  let payload = {};

  if (stage === "metadata") {
    payload = {
      query: metadataQueryEl.value.trim(),
      max_results: metadataMaxEl.value.trim(),
      providers: Array.from(metadataProvidersEl.selectedOptions).map((opt) => opt.value),
      output_csv: metadataOutputEl.value.trim(),
    };
  } else if (stage === "filter") {
    payload = {
      provider: filterProviderEl.value,
      model: filterModelEl.value.trim(),
      input_csv: filterInputEl.value.trim(),
      output_csv: filterOutputEl.value.trim(),
      system_prompt: filterSystemPromptEl ? filterSystemPromptEl.value.trim() : "",
      user_prompt_template: filterUserPromptEl ? filterUserPromptEl.value.trim() : "",
    };
  } else if (stage === "download") {
    payload = {
      provider: downloadProviderEl.value,
      doi: downloadDoiEl.value.trim(),
      input_csv: downloadCsvEl.value.trim(),
      output_dir: downloadOutputEl.value.trim(),
    };
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
  } else if (stage === "llm") {
    const rawTask = llmTaskEl.value.trim();
    const rawTemplate = llmOutputTemplateEl.value.trim();
    const autoMode = (llmAutoSchemaEl && llmAutoSchemaEl.value) ? llmAutoSchemaEl.value : "auto";
    const autoSchema =
      autoMode === "true"
        ? true
        : autoMode === "false"
          ? false
          : !rawTask && !rawTemplate;
    payload = {
      input_path: llmInputEl.value.trim(),
      output_path: llmOutputEl.value.trim(),
      system_prompt: llmSystemPromptEl ? llmSystemPromptEl.value.trim() : "",
      user_prompt_template: llmUserPromptEl ? llmUserPromptEl.value.trim() : "",

      task: rawTask,
      output_template: rawTemplate,
      auto_schema: autoSchema,
      schema_sample_size: llmSchemaSampleSizeEl ? llmSchemaSampleSizeEl.value.trim() : "",
      schema_max_fields: llmSchemaMaxFieldsEl ? llmSchemaMaxFieldsEl.value.trim() : "",
      provider: llmProviderEl.value,
      model: llmModelEl.value.trim(),
      base_url: llmBaseUrlEl.value.trim(),
      chat_path: llmChatPathEl.value.trim(),
      api_key_env: llmKeyEnvEl.value.trim(),
      api_key_header: llmKeyHeaderEl.value.trim(),
      api_key_prefix: llmKeyPrefixEl.value.trim(),
      block_limit: llmBlockLimitEl.value.trim(),
      char_limit: llmCharLimitEl ? llmCharLimitEl.value.trim() : "",
      temperature: llmTemperatureEl.value.trim(),
      timeout: llmTimeoutEl.value.trim(),
    };
  } else {
    appendLog(`未知阶段: ${stage}`);
    return { ok: false };
  }

  const result = await apiPost("/api/run", { stage, params: payload });
  try {
    if (logStreamState.running) {
      await pollLogStream();
    } else {
      await loadLogs();
    }
  } catch (err) {
    appendLog(`日志刷新失败: ${err.message}`);
  }
  appendLog(`完成 ${stepLabels[stage] || stage} -> ${result.ok ? "OK" : "FAILED"}`);
  return result;
}

async function init() {
  const state = await apiGet("/api/state");
  cachedConfig = state.config || {};
  cachedEnv = state.env || {};
  cachedPaths = state.paths || {};
  llmProviderPresets = (state.providers && state.providers.llm_presets) || {};
  downloadProviders = (state.providers && state.providers.download) || [];

  document.getElementById("projectRoot").textContent = state.paths.project_root || "--";
  document.getElementById("envPath").textContent = state.paths.env_file || "--";
  document.getElementById("overridePath").textContent = state.paths.override_file || "--";

  envListEl.innerHTML = "";
  removedEnvKeys.clear();
  const llmEnvKeys = new Set(
    Object.values(llmProviderPresets)
      .map((preset) => preset.api_key_env)
      .filter(Boolean)
  );
  Object.entries(cachedEnv)
    .filter(([key, value]) => value && value.toString().trim() !== "" && !llmEnvKeys.has(key))
    .forEach(([key, value]) => addEnvRow(key, value));
  updateEnvEmptyState();

  overrideJsonEl.value = JSON.stringify(state.override || {}, null, 2);
  const stageDefaults = normalizeStageDefaults((state.override || {}).STAGE_CONFIGS);
  cachedStageDefaults = stageDefaults;

  const metadataOutputDefault =
    (stageDefaults.metadata && stageDefaults.metadata.output_csv) ||
    cachedConfig.METADATA_CSV_PATH ||
    "";
  if (metadataOutputEl) metadataOutputEl.value = metadataOutputDefault;
  if (filterInputEl) {
    filterInputEl.value =
      (stageDefaults.filter && stageDefaults.filter.input_csv) ||
      metadataOutputDefault ||
      cachedConfig.METADATA_CSV_PATH ||
      "";
  }
  if (filterOutputEl) {
    filterOutputEl.value =
      (stageDefaults.filter && stageDefaults.filter.output_csv) ||
      cachedConfig.FILTERED_METADATA_CSV_PATH ||
      "";
  }

  metadataQueryEl.value = cachedConfig.METADATA_DEFAULT_QUERY || "";
  metadataMaxEl.value = cachedConfig.METADATA_MAX_RESULTS || "";
  populateProviders(metadataProvidersEl, state.providers.metadata || []);
  setMultiSelect(metadataProvidersEl, cachedConfig.METADATA_PROVIDERS || []);

  const llmProviders = state.providers.llm || [];
  populateProviders(filterProviderEl, llmProviders);
  ensureOption(filterProviderEl, cachedConfig.METADATA_FILTER_PROVIDER);
  filterProviderEl.value = cachedConfig.METADATA_FILTER_PROVIDER || "";
  filterModelEl.value = cachedConfig.METADATA_FILTER_MODEL || "";
  if (filterSystemPromptEl) {
    filterSystemPromptEl.value = cachedConfig.METADATA_FILTER_SYSTEM_PROMPT || "";
  }
  if (filterUserPromptEl) {
    filterUserPromptEl.value = cachedConfig.METADATA_FILTER_USER_PROMPT_TEMPLATE || "";
  }

  populatePresetSelect(ocrPresetEl, ocrPresets);
  ocrPresetEl.value = "custom";

  populateProviders(downloadProviderEl, downloadProviders, {
    value: "auto",
    label: "auto",
  });
  downloadProviderEl.value = "auto";
  renderDownloadPriorityList(
    downloadProviders,
    cachedConfig.LITERATURE_FETCHER_PROVIDER_ORDER || []
  );
  downloadCsvEl.value =
    (stageDefaults.download && stageDefaults.download.input_csv) ||
    cachedConfig.METADATA_CSV_PATH ||
    "";
  downloadOutputEl.value =
    (stageDefaults.download && stageDefaults.download.output_dir) ||
    cachedConfig.ASSETS2_DIR ||
    "";

  convertInputEl.value =
    (stageDefaults.convert && stageDefaults.convert.input_path) ||
    cachedConfig.XML_SOURCE_DIR ||
    cachedConfig.ASSETS2_DIR ||
    "";
  convertOutputEl.value =
    (stageDefaults.convert && stageDefaults.convert.output_dir) ||
    cachedConfig.BLOCKS_OUTPUT_DIR ||
    "";
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

  populateProviders(llmProviderEl, llmProviders);
  ensureOption(llmProviderEl, cachedConfig.LLM_EXTRACTION_PROVIDER);
  llmProviderEl.value = cachedConfig.LLM_EXTRACTION_PROVIDER || "";
  llmModelEl.value = cachedConfig.LLM_EXTRACTION_MODEL || "";
  llmBaseUrlEl.value = cachedConfig.LLM_EXTRACTION_BASE_URL || "";
  llmChatPathEl.value = cachedConfig.LLM_EXTRACTION_CHAT_PATH || "";
  llmKeyEnvEl.value = cachedConfig.LLM_EXTRACTION_API_KEY_ENV || "";
  llmKeyHeaderEl.value = cachedConfig.LLM_EXTRACTION_API_KEY_HEADER || "";
  llmKeyPrefixEl.value = cachedConfig.LLM_EXTRACTION_API_KEY_PREFIX || "";
  llmBlockLimitEl.value = cachedConfig.LLM_EXTRACTION_BLOCK_LIMIT || "";
  if (llmCharLimitEl) {
    llmCharLimitEl.value = cachedConfig.LLM_EXTRACTION_CHAR_LIMIT || "";
  }
  llmTemperatureEl.value = cachedConfig.LLM_EXTRACTION_TEMPERATURE || "";
  llmTimeoutEl.value = cachedConfig.LLM_EXTRACTION_TIMEOUT || "";
  llmInputEl.value =
    (stageDefaults.llm && stageDefaults.llm.input_path) ||
    cachedConfig.BLOCKS_OUTPUT_DIR ||
    "";
  llmOutputEl.value =
    (stageDefaults.llm && stageDefaults.llm.output_path) ||
    cachedConfig.LLM_EXTRACTION_OUTPUT_PATH ||
    "";
  llmTaskEl.value = cachedConfig.LLM_EXTRACTION_TASK_PROMPT || "";
  if (llmSystemPromptEl) {
    llmSystemPromptEl.value = cachedConfig.LLM_EXTRACTION_SYSTEM_PROMPT || "";
  }
  if (llmUserPromptEl) {
    llmUserPromptEl.value = cachedConfig.LLM_EXTRACTION_USER_PROMPT_TEMPLATE || "";
  }

  if (llmAutoSchemaEl) {
    llmAutoSchemaEl.value = "auto";
  }
  if (llmSchemaSampleSizeEl) {
    llmSchemaSampleSizeEl.value = "";
  }
  if (llmSchemaMaxFieldsEl) {
    llmSchemaMaxFieldsEl.value = "";
  }
  if (cachedConfig.LLM_EXTRACTION_OUTPUT_TEMPLATE) {
    llmOutputTemplateEl.value = JSON.stringify(cachedConfig.LLM_EXTRACTION_OUTPUT_TEMPLATE, null, 2);
  }
  populatePresetSelect(llmPresetEl, llmPresets);
  llmPresetEl.value = "custom";

  if (llmQuickProviderEl) {
    populateProviders(llmQuickProviderEl, llmProviders);
    const defaultProvider = cachedConfig.LLM_EXTRACTION_PROVIDER || llmProviders[0] || "";
    ensureOption(llmQuickProviderEl, defaultProvider);
    llmQuickProviderEl.value = defaultProvider;
    applyLlmQuickPreset(defaultProvider);
  }
  if (llmQuickModelEl) {
    llmQuickModelEl.value = cachedConfig.LLM_EXTRACTION_MODEL || "";
  }

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

if (llmQuickProviderEl) {
  llmQuickProviderEl.addEventListener("change", () => {
    applyLlmQuickPreset(llmQuickProviderEl.value);
  });
}

runPipelineBtn.addEventListener("click", async () => {
  if (pipelineQueue.length === 0) {
    appendLog("队列为空，请先添加阶段。");
    return;
  }
  runPipelineBtn.disabled = true;
  appendLog("开始执行队列...");
  logStreamState.minTimestamp = Date.now();
  await startLogStream({ reset: true });
  try {
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
  } finally {
    await pollLogStream();
    stopLogStream();
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

document.querySelectorAll("[data-save]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const stage = btn.dataset.save;
    if (!stage) return;
    await saveStagePaths(stage, btn);
  });
});

if (downloadPrioritySaveBtn) {
  downloadPrioritySaveBtn.addEventListener("click", async () => {
    await saveDownloadPriority(downloadPrioritySaveBtn);
  });
}

if (downloadPriorityResetBtn) {
  downloadPriorityResetBtn.addEventListener("click", () => {
    renderDownloadPriorityList(
      downloadProviders,
      cachedConfig.LITERATURE_FETCHER_PROVIDER_ORDER || []
    );
    appendLog("已重置下载优先级。");
  });
}


document.getElementById("addEnv").addEventListener("click", () => addEnvRow());

document.getElementById("saveEnv").addEventListener("click", async () => {
  const updates = collectEnvUpdates();
  try {
    await apiPost("/api/env", { values: updates });
    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === "") {
        delete cachedEnv[key];
      } else {
        cachedEnv[key] = value;
      }
    });
    removedEnvKeys.clear();
    refreshDownloadPriorityBadges();
    appendLog("ENV 已保存。");
  } catch (err) {
    appendLog(`ENV 保存失败: ${err.message}`);
  }
});

if (saveLlmQuickBtn) {
  saveLlmQuickBtn.addEventListener("click", async () => {
    const provider = llmQuickProviderEl ? llmQuickProviderEl.value : "";
    const model = llmQuickModelEl ? llmQuickModelEl.value.trim() : "";
    if (!provider) {
      appendLog("请先选择 LLM Provider。");
      return;
    }
    if (!model) {
      appendLog("请输入 LLM 模型。");
      return;
    }
    const preset = llmProviderPresets[provider];
    if (!preset) {
      appendLog(`未找到 ${provider} 的预设配置。`);
      return;
    }
    const overrides = parseOverrideJson();
    if (overrides === null) {
      return;
    }
    const overrideUpdates = {
      LLM_EXTRACTION_PROVIDER: provider,
      LLM_EXTRACTION_MODEL: model,
      LLM_EXTRACTION_BASE_URL: preset.base_url,
      LLM_EXTRACTION_CHAT_PATH: preset.chat_path,
      LLM_EXTRACTION_API_KEY_ENV: preset.api_key_env,
      METADATA_FILTER_PROVIDER: provider,
      METADATA_FILTER_MODEL: model,
    };
    Object.entries(overrideUpdates).forEach(([key, value]) => {
      if (value !== undefined) {
        overrides[key] = value;
      }
    });
    saveLlmQuickBtn.disabled = true;
    try {
      await apiPost("/api/config", { overrides });
      writeOverrideJson(overrides);
      cachedConfig = { ...cachedConfig, ...overrideUpdates };
      if (filterProviderEl) filterProviderEl.value = provider;
      if (filterModelEl) filterModelEl.value = model;
      if (llmProviderEl) llmProviderEl.value = provider;
      if (llmModelEl) llmModelEl.value = model;
      if (llmBaseUrlEl) llmBaseUrlEl.value = preset.base_url || "";
      if (llmChatPathEl) llmChatPathEl.value = preset.chat_path || "";
      if (llmKeyEnvEl) llmKeyEnvEl.value = preset.api_key_env || "";

      const apiKey = llmQuickKeyEl ? llmQuickKeyEl.value.trim() : "";
      if (apiKey && preset.api_key_env) {
        await apiPost("/api/env", { values: { [preset.api_key_env]: apiKey } });
        cachedEnv[preset.api_key_env] = apiKey;
        appendLog("LLM 配置已保存并写入 ENV。");
      } else {
        appendLog("LLM 配置已保存。");
      }
    } catch (err) {
      appendLog(`LLM 配置保存失败: ${err.message}`);
    } finally {
      saveLlmQuickBtn.disabled = false;
    }
  });
}


document.getElementById("saveOverride").addEventListener("click", async () => {
  const overrides = parseOverrideJson();
  if (overrides === null) {
    return;
  }
  try {
    await apiPost("/api/config", { overrides });
    appendLog("Override 已保存。下次任务调用将自动生效。");
  } catch (err) {
    appendLog(`Override 保存失败: ${err.message}`);
  }
});

if (exportConfigBtn) {
  exportConfigBtn.addEventListener("click", () => {
    const overrides = parseOverrideJson();
    if (overrides === null) {
      return;
    }
    const payload = {
      exported_at: new Date().toISOString(),
      project: cachedPaths,
      pipeline_queue: [...pipelineQueue],
      env: buildEnvSnapshot(),
      overrides,
      ui: collectUiSnapshot(),
    };
    triggerJsonDownload(payload);
    appendLog("配置 JSON 已导出。");
  });
}


document.getElementById("useFiltered").addEventListener("click", () => {
  const filteredValue =
    (filterOutputEl && filterOutputEl.value.trim()) ||
    (cachedStageDefaults.filter && cachedStageDefaults.filter.output_csv) ||
    cachedConfig.FILTERED_METADATA_CSV_PATH ||
    "";
  if (filteredValue) {
    downloadCsvEl.value = filteredValue;
  }
});

if (logSourceEl) {
  logSourceEl.addEventListener("change", () => {
    if (logStreamState.running) {
      logStreamState.source = logSourceEl.value;
      logStreamState.lastLine = null;
      clearLogView();
      pollLogStream().catch((err) => appendLog(`日志刷新失败: ${err.message}`));
    } else {
      loadLogs().catch((err) => appendLog(`日志刷新失败: ${err.message}`));
    }
  });
}
if (logRefreshBtn) {
  logRefreshBtn.addEventListener("click", () => {
    if (logStreamState.running) {
      pollLogStream().catch((err) => appendLog(`日志刷新失败: ${err.message}`));
    } else {
      loadLogs().catch((err) => appendLog(`日志刷新失败: ${err.message}`));
    }
  });
}

init().catch((err) => {
  appendLog(`初始化失败: ${err.message}`);
});
