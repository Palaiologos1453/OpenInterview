const apiFromUrl = new URLSearchParams(window.location.search).get("api");
if (apiFromUrl) localStorage.setItem("openinterview_api_base", apiFromUrl);
const API_BASE = apiFromUrl || localStorage.getItem("openinterview_api_base") || "http://127.0.0.1:8000";
const PROVIDER_CONFIG_KEY = "openinterview_provider_config";
const LOCAL_AUTH_KEY = "openinterview_local_auth";

const defaultProviderConfig = {
  llm: {
    provider: "openai_compatible",
    api_base: "",
    model: "",
    api_key: "",
    temperature: 0.4,
    timeout_seconds: 45
  },
  asr: {
    provider: "browser",
    api_base: "",
    model: "",
    api_key: "",
    language: "zh-CN",
    timeout_seconds: 60,
    device: "auto"
  },
  tts: {
    provider: "browser",
    api_base: "",
    model: "",
    api_key: "",
    voice: "",
    response_format: "mp3",
    timeout_seconds: 60,
    voice_profile_id: "young_engineer"
  }
};

const fallbackCatalog = {
  directions: [{ id: "backend", name: "后端开发", summary: "数据库、缓存、并发、分布式基础。" }],
  difficulties: [{ id: "campus", name: "普通校招", summary: "基础、项目、算法均衡。" }],
  modes: [{ id: "comprehensive", name: "综合模拟", summary: "完整流程。" }],
  voice_profiles: [{ id: "young_engineer", name: "青年工程师" }]
};

const state = {
  catalog: fallbackCatalog,
  sessionId: null,
  realtimeSessionId: null,
  backendReady: false,
  authRequired: false,
  localAuth: loadLocalAuth(),
  readiness: null,
  messages: [],
  mediaRecorder: null,
  mediaStream: null,
  realtimeSocket: null,
  realtimeMode: "idle",
  ttsChunks: [],
  audioContext: null,
  pcmPlaybackTime: 0,
  pcmSampleRate: 16000,
  pcmChannels: 1,
  currentAudio: null,
  recordedChunks: [],
  providerConfig: loadProviderConfig()
};

const $ = (selector) => document.querySelector(selector);
const elements = {
  direction: $("#direction"),
  difficulty: $("#difficulty"),
  mode: $("#mode"),
  voiceProfile: $("#voice-profile"),
  candidateName: $("#candidate-name"),
  resume: $("#resume"),
  voiceOutput: $("#voice-output"),
  llmProvider: $("#llm-provider"),
  llmApiBase: $("#llm-api-base"),
  llmModel: $("#llm-model"),
  llmApiKey: $("#llm-api-key"),
  llmTemperature: $("#llm-temperature"),
  asrProvider: $("#asr-provider"),
  asrApiBase: $("#asr-api-base"),
  asrModel: $("#asr-model"),
  asrApiKey: $("#asr-api-key"),
  ttsProvider: $("#tts-provider"),
  ttsApiBase: $("#tts-api-base"),
  ttsModel: $("#tts-model"),
  ttsVoice: $("#tts-voice"),
  ttsApiKey: $("#tts-api-key"),
  saveProviderConfig: $("#save-provider-config"),
  testLlmConfig: $("#test-llm-config"),
  clearProviderConfig: $("#clear-provider-config"),
  setupForm: $("#setup-form"),
  runtimeStatus: $("#runtime-status"),
  setupChecklist: $("#setup-checklist"),
  resumePanel: $("#resume-panel"),
  sessionTitle: $("#session-title"),
  conversation: $("#conversation"),
  answerForm: $("#answer-form"),
  answer: $("#answer"),
  sendButton: $("#send-button"),
  listenButton: $("#listen-button"),
  reportButton: $("#report-button"),
  historyButton: $("#history-button"),
  analyzeResumeButton: $("#analyze-resume-button"),
  report: $("#report")
};

init();

async function init() {
  try {
    const health = await fetchJson(`${API_BASE}/health`, { timeoutMs: 1800 });
    state.authRequired = Boolean(health.require_auth);
    if (state.authRequired) {
      await ensureLocalAuth();
    }
    state.catalog = await fetchJson(`${API_BASE}/v1/catalog`, { timeoutMs: 3000 });
    state.backendReady = true;
    setStatus(`已连接本地后端：${API_BASE}。填写兼容 OpenAI 的 URL、模型名和 Key 后即可开始文本面试；语音为可选能力。`);
  } catch (error) {
    state.backendReady = false;
    state.catalog = fallbackCatalog;
    setStatus(`本地后端不可用：${error.message}。请先启动 API，再刷新页面。`);
  }

  fillSelect(elements.direction, state.catalog.directions);
  fillSelect(elements.difficulty, state.catalog.difficulties);
  fillSelect(elements.mode, state.catalog.modes);
  fillSelect(elements.voiceProfile, state.catalog.voice_profiles || [], "id", "name");
  fillProviderForm(state.providerConfig);
  wireEvents();
  renderSetupChecklist();
  if (state.backendReady) refreshReadiness();
}

function wireEvents() {
  elements.setupForm.addEventListener("submit", safeHandler(startInterview));
  elements.answerForm.addEventListener("submit", safeHandler(submitAnswer));
  elements.reportButton.addEventListener("click", safeHandler(generateReport));
  elements.listenButton.addEventListener("click", safeHandler(handleVoiceInput));
  elements.saveProviderConfig.addEventListener("click", saveProviderConfig);
  elements.testLlmConfig.addEventListener("click", safeHandler(testLlmConfig));
  elements.clearProviderConfig.addEventListener("click", clearProviderConfig);
  elements.analyzeResumeButton.addEventListener("click", safeHandler(analyzeResume));
  elements.historyButton.addEventListener("click", safeHandler(loadHistory));
  providerInputs().forEach((input) => {
    input.addEventListener("input", renderSetupChecklist);
    input.addEventListener("change", renderSetupChecklist);
  });
  [elements.direction, elements.difficulty, elements.mode, elements.voiceProfile].forEach((input) => {
    input.addEventListener("change", renderSetupChecklist);
  });
}

function safeHandler(handler) {
  return async (event) => {
    try {
      await handler(event);
    } catch (error) {
      setStatus(error.message || String(error));
    }
  };
}

function fillSelect(select, items, valueKey = "id", labelKey = "name") {
  select.innerHTML = items
    .map((item) => `<option value="${item[valueKey]}">${escapeHtml(item[labelKey] || item[valueKey])}</option>`)
    .join("");
}

async function startInterview(event) {
  event.preventDefault();
  ensureBackend();
  const config = readConfig();
  validateProviderConfig(config.provider_config);
  state.providerConfig = config.provider_config;
  state.messages = [];
  elements.report.hidden = true;

  const payload = await postJson(`${API_BASE}/v1/interviews`, config);
  state.sessionId = payload.session_id;
  const realtime = await postJson(`${API_BASE}/v1/realtime/sessions`, { interview_id: state.sessionId });
  state.realtimeSessionId = realtime.id;
  elements.sessionTitle.textContent = `${selectedName(elements.direction)} / ${selectedName(elements.difficulty)}`;
  elements.answer.disabled = false;
  elements.sendButton.disabled = false;
  elements.listenButton.disabled = !canUseVoiceInput();
  elements.reportButton.disabled = false;
  elements.conversation.innerHTML = "";
  addMessage("interviewer", "面试官", payload.opening_message);
  addMessage("interviewer", "问题", payload.next_question);
  showProviderNotice(payload.provider_notice);
  speak(`${payload.opening_message} ${payload.next_question}`);
}

async function submitAnswer(event) {
  event.preventDefault();
  ensureBackend();
  const answer = elements.answer.value.trim();
  if (!answer) return;
  addMessage("candidate", "候选人", answer);
  elements.answer.value = "";
  elements.sendButton.disabled = true;
  try {
    const payload = await postJson(`${API_BASE}/v1/interviews/${state.sessionId}/turn`, { answer });
    addMessage("interviewer", "反馈", payload.interviewer_message, payload.focus_tags);
    addMessage("interviewer", payload.is_finished ? "结束" : "问题", payload.next_question);
    showProviderNotice(payload.provider_notice);
    speak(`${payload.interviewer_message} ${payload.next_question}`);
  } finally {
    elements.sendButton.disabled = false;
  }
}

async function generateReport() {
  ensureBackend();
  const report = await fetchJson(`${API_BASE}/v1/interviews/${state.sessionId}/report`);
  renderReport(report);
}

async function analyzeResume() {
  ensureBackend();
  const text = elements.resume.value.trim();
  if (!text) return;
  const result = await postJson(`${API_BASE}/v1/resume/analyze`, { text });
  elements.resumePanel.hidden = false;
  elements.resumePanel.innerHTML = `
    <strong>简历分析</strong>
    ${renderMiniList("技术栈", result.tech_stack)}
    ${renderMiniList("项目", result.projects)}
    ${renderMiniList("风险", result.risks)}
  `;
}

async function loadHistory() {
  ensureBackend();
  const payload = await fetchJson(`${API_BASE}/v1/interviews`);
  renderHistory(payload.interviews || []);
  setStatus(`历史记录：${payload.interviews.length} 条。点击“报告”可打开完整报告，点击“复练题”可只看练习项。`);
}

function renderHistory(interviews) {
  elements.report.hidden = false;
  if (!interviews.length) {
    elements.report.innerHTML = `
      <div class="section-heading">
        <h3>历史记录</h3>
        <div class="inline-actions">
          <button id="export-history-button" class="secondary" type="button">导出历史</button>
          <button id="clear-history-button" class="secondary danger-action" type="button">清空历史</button>
        </div>
      </div>
      <p class="muted-text">还没有本地面试记录。完成一轮面试后，这里会显示报告和复练入口。</p>
    `;
    $("#export-history-button")?.addEventListener("click", safeHandler(exportHistory));
    $("#clear-history-button")?.addEventListener("click", safeHandler(clearHistory));
    return;
  }
  elements.report.innerHTML = `
    <div class="section-heading">
      <h3>历史记录</h3>
      <div class="inline-actions">
        <button id="export-history-button" class="secondary" type="button">导出历史</button>
        <button id="clear-history-button" class="secondary danger-action" type="button">清空历史</button>
      </div>
    </div>
    <div class="history-list">
      ${interviews.map((item) => {
        const config = item.config || {};
        const summary = [
          catalogName("directions", config.direction_id),
          catalogName("difficulties", config.difficulty_id),
          catalogName("modes", config.mode_id)
        ].filter(Boolean).join(" / ");
        return `
          <article class="history-item">
            <div>
              <div class="history-title">${escapeHtml(summary || "未命名面试")}</div>
              <div class="history-meta">
                <span>${escapeHtml(formatDate(item.updated_at || item.created_at))}</span>
                <span>${escapeHtml(item.status || "active")}</span>
                ${item.has_report ? "<span>已有报告</span>" : "<span>可生成报告</span>"}
              </div>
            </div>
            <div class="history-actions">
              <button class="secondary" type="button" data-history-report="${escapeHtml(item.id)}">报告</button>
              <button class="secondary" type="button" data-history-drills="${escapeHtml(item.id)}">复练题</button>
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
  elements.report.querySelectorAll("[data-history-report]").forEach((button) => {
    button.addEventListener("click", safeHandler(() => openHistoryReport(button.dataset.historyReport)));
  });
  elements.report.querySelectorAll("[data-history-drills]").forEach((button) => {
    button.addEventListener("click", safeHandler(() => openHistoryDrills(button.dataset.historyDrills)));
  });
  $("#export-history-button")?.addEventListener("click", safeHandler(exportHistory));
  $("#clear-history-button")?.addEventListener("click", safeHandler(clearHistory));
}

async function exportHistory() {
  ensureBackend();
  const response = await authedFetch(`${API_BASE}/v1/interviews/export`);
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `openinterview-history-${Date.now()}.json`;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  setStatus("历史记录已导出为 JSON 文件。");
}

async function clearHistory() {
  ensureBackend();
  const ok = window.confirm("确认清空所有本地面试历史、报告、转写和 trace？此操作不会清空模型配置。");
  if (!ok) return;
  const payload = await deleteJson(`${API_BASE}/v1/interviews`);
  state.sessionId = null;
  state.realtimeSessionId = null;
  elements.reportButton.disabled = true;
  elements.report.hidden = true;
  elements.sessionTitle.textContent = "选择方向后开始模拟";
  elements.conversation.innerHTML = `
    <div class="empty-state">
      <strong>OpenInterview</strong>
      <span>选择方向和难度，填写本地模型配置后开始一轮计算机校招模拟面试。</span>
    </div>
  `;
  setStatus(`已清空 ${payload.deleted || 0} 条历史记录。`);
}

async function openHistoryReport(sessionId) {
  const report = await fetchJson(`${API_BASE}/v1/interviews/${sessionId}/report`);
  renderReport(report);
  state.sessionId = report.session_id;
  elements.reportButton.disabled = false;
  elements.sessionTitle.textContent = `历史报告 / ${shortText(report.session_id, 8)}`;
  setStatus("已打开历史报告。");
}

async function openHistoryDrills(sessionId) {
  const report = await fetchJson(`${API_BASE}/v1/interviews/${sessionId}/report`);
  elements.report.hidden = false;
  elements.report.innerHTML = `
    <h3>历史复练：${escapeHtml(String(report.overall_score))} / 100</h3>
    ${report.ai_summary ? `<p>${escapeHtml(report.ai_summary)}</p>` : ""}
    ${renderPracticeDrills(report.practice_drills || [])}
    ${renderAnswerGuides(report.answer_guides || [])}
  `;
  setStatus("已打开历史复练题。");
}

function readConfig() {
  return {
    direction_id: elements.direction.value,
    difficulty_id: elements.difficulty.value,
    mode_id: elements.mode.value,
    candidate_name: elements.candidateName.value.trim() || null,
    resume_text: elements.resume.value.trim() || null,
    duration_minutes: 30,
    language: "zh-CN",
    provider_config: readProviderConfig()
  };
}

function readProviderConfig() {
  return {
    llm: {
      provider: elements.llmProvider.value,
      api_base: elements.llmApiBase.value.trim(),
      model: elements.llmModel.value.trim(),
      api_key: elements.llmApiKey.value.trim(),
      temperature: Number(elements.llmTemperature.value || 0.4),
      timeout_seconds: 45
    },
    asr: {
      provider: elements.asrProvider.value,
      api_base: elements.asrApiBase.value.trim(),
      model: elements.asrModel.value.trim(),
      api_key: elements.asrApiKey.value.trim(),
      language: "zh-CN",
      timeout_seconds: 60,
      device: "auto"
    },
    tts: {
      provider: elements.ttsProvider.value,
      api_base: elements.ttsApiBase.value.trim(),
      model: elements.ttsModel.value.trim(),
      api_key: elements.ttsApiKey.value.trim(),
      voice: elements.ttsVoice.value.trim(),
      response_format: elements.ttsProvider.value === "cosyvoice" ? "wav" : "mp3",
      timeout_seconds: 60,
      voice_profile_id: elements.voiceProfile.value || "young_engineer"
    }
  };
}

function validateProviderConfig(config) {
  if (config.llm.provider === "openai_compatible") {
    if (!config.llm.api_base || !config.llm.model || !config.llm.api_key) {
      throw new Error("请填写大模型面试官的 API URL、模型名和 API Key。");
    }
  }
}

async function refreshReadiness() {
  try {
    state.readiness = await fetchJson(`${API_BASE}/v1/readiness`, { timeoutMs: 5000 });
  } catch {
    state.readiness = null;
  }
  renderSetupChecklist();
}

async function testLlmConfig() {
  ensureBackend();
  const provider_config = readProviderConfig();
  const missing = llmMissingFields(provider_config.llm);
  if (missing.length) {
    throw new Error(`LLM 配置缺少 ${missing.join("、")}。`);
  }
  elements.testLlmConfig.disabled = true;
  setStatus("正在测试 LLM 连接。");
  try {
    const result = await postJson(`${API_BASE}/v1/providers/llm/test`, { provider_config });
    if (!result.ok) {
      throw new Error(result.message || "LLM 连接测试失败。");
    }
    setStatus(`${result.message}${result.sample ? ` 返回：${result.sample}` : ""}`);
  } finally {
    elements.testLlmConfig.disabled = false;
    renderSetupChecklist();
  }
}

function llmMissingFields(llm) {
  if (llm.provider === "mock") return [];
  if (llm.provider === "ollama") return llm.model ? [] : ["Model"];
  const missing = [];
  if (!llm.api_base) missing.push("API Base");
  if (!llm.model) missing.push("Model");
  if (!llm.api_key) missing.push("API Key");
  return missing;
}

function renderSetupChecklist() {
  if (!elements.setupChecklist) return;
  const config = readProviderConfig();
  const items = [
    {
      label: "本地 API",
      status: state.backendReady ? "ok" : "bad",
      detail: state.backendReady ? API_BASE : "未连接，请先启动 API"
    },
    llmChecklistItem(config.llm),
    {
      label: "面试模式",
      status: "ok",
      detail: selectedName(elements.mode) || "已选择默认模式"
    },
    asrChecklistItem(config.asr),
    ttsChecklistItem(config.tts),
    resumeChecklistItem()
  ];
  elements.setupChecklist.innerHTML = `
    <div class="checklist-title">首次使用检查</div>
    <div class="checklist-items">
      ${items.map((item) => `
        <div class="check-item ${item.status}">
          <span class="check-dot" aria-hidden="true"></span>
          <div>
            <strong>${escapeHtml(item.label)}</strong>
            <p>${escapeHtml(item.detail)}</p>
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function llmChecklistItem(llm) {
  if (llm.provider === "mock") {
    return { label: "LLM 面试官", status: "warn", detail: "当前是 Mock，只适合本地开发验证流程" };
  }
  if (llm.provider === "ollama") {
    return {
      label: "LLM 面试官",
      status: llm.model ? "ok" : "warn",
      detail: llm.model ? `Ollama：${llm.model}` : "Ollama 未填写模型名，将使用后端默认值"
    };
  }
  const missing = llmMissingFields(llm);
  return {
    label: "LLM 面试官",
    status: missing.length ? "bad" : "ok",
    detail: missing.length ? `缺少 ${missing.join("、")}` : `${llm.model} 已配置`
  };
}

function asrChecklistItem(asr) {
  if (asr.provider === "disabled") {
    return { label: "语音输入", status: "warn", detail: "已关闭，不影响文本面试" };
  }
  if (asr.provider === "browser") {
    const supported = Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
    return {
      label: "语音输入",
      status: supported ? "ok" : "warn",
      detail: supported ? "浏览器内置语音可用" : "浏览器不支持时可改用文本回答"
    };
  }
  if (asr.provider === "sensevoice") {
    const checks = state.readiness?.checks || {};
    const ok = Boolean(checks.ffmpeg?.ok && checks.asr_model?.ok && checks.funasr?.ok);
    return {
      label: "语音输入",
      status: ok ? "ok" : "warn",
      detail: ok ? "Local SenseVoice 依赖已就绪" : "Local SenseVoice 依赖未完全确认"
    };
  }
  const ready = Boolean(asr.api_base && asr.model && asr.api_key);
  return {
    label: "语音输入",
    status: ready ? "ok" : "warn",
    detail: ready ? "API ASR 已配置" : "API ASR 缺少 URL、模型名或 Key"
  };
}

function ttsChecklistItem(tts) {
  if (tts.provider === "disabled") {
    return { label: "语音播报", status: "warn", detail: "已关闭，不影响文本面试" };
  }
  if (tts.provider === "browser") {
    return {
      label: "语音播报",
      status: window.speechSynthesis ? "ok" : "warn",
      detail: window.speechSynthesis ? "浏览器播报可用" : "当前浏览器不支持播报"
    };
  }
  if (tts.provider === "cosyvoice") {
    return {
      label: "语音播报",
      status: state.readiness?.ready_for_local_voice ? "ok" : "warn",
      detail: state.readiness?.ready_for_local_voice ? "Local CosyVoice 依赖已就绪" : "Local CosyVoice 依赖未完全确认"
    };
  }
  const ready = Boolean(tts.api_base && tts.model && tts.api_key);
  return {
    label: "语音播报",
    status: ready ? "ok" : "warn",
    detail: ready ? "API TTS 已配置" : "API TTS 缺少 URL、模型名或 Key"
  };
}

function resumeChecklistItem() {
  const needsResume = elements.mode.value === "project_deep_dive";
  const hasResume = Boolean(elements.resume.value.trim());
  if (needsResume && !hasResume) {
    return { label: "简历材料", status: "warn", detail: "简历拷打模式建议先粘贴项目经历" };
  }
  return {
    label: "简历材料",
    status: hasResume ? "ok" : "warn",
    detail: hasResume ? "已填写，可用于项目追问" : "可选；不填也能开始八股/综合面试"
  };
}

function providerInputs() {
  return [
    elements.llmProvider,
    elements.llmApiBase,
    elements.llmModel,
    elements.llmApiKey,
    elements.llmTemperature,
    elements.asrProvider,
    elements.asrApiBase,
    elements.asrModel,
    elements.asrApiKey,
    elements.ttsProvider,
    elements.ttsApiBase,
    elements.ttsModel,
    elements.ttsVoice,
    elements.ttsApiKey,
    elements.resume
  ].filter(Boolean);
}

function fillProviderForm(config) {
  elements.llmProvider.value = config.llm.provider;
  elements.llmApiBase.value = config.llm.api_base || "";
  elements.llmModel.value = config.llm.model || "";
  elements.llmApiKey.value = config.llm.api_key || "";
  elements.llmTemperature.value = config.llm.temperature;
  elements.asrProvider.value = config.asr.provider;
  elements.asrApiBase.value = config.asr.api_base || "";
  elements.asrModel.value = config.asr.model || "";
  elements.asrApiKey.value = config.asr.api_key || "";
  elements.ttsProvider.value = config.tts.provider;
  elements.ttsApiBase.value = config.tts.api_base || "";
  elements.ttsModel.value = config.tts.model || "";
  elements.ttsVoice.value = config.tts.voice || "";
  elements.ttsApiKey.value = config.tts.api_key || "";
  if (config.tts.voice_profile_id) elements.voiceProfile.value = config.tts.voice_profile_id;
  renderSetupChecklist();
}

function loadProviderConfig() {
  try {
    const stored = JSON.parse(localStorage.getItem(PROVIDER_CONFIG_KEY) || "{}");
    return {
      llm: { ...defaultProviderConfig.llm, ...(stored.llm || {}) },
      asr: { ...defaultProviderConfig.asr, ...(stored.asr || {}) },
      tts: { ...defaultProviderConfig.tts, ...(stored.tts || {}) }
    };
  } catch {
    return structuredClone(defaultProviderConfig);
  }
}

function saveProviderConfig() {
  state.providerConfig = readProviderConfig();
  localStorage.setItem(PROVIDER_CONFIG_KEY, JSON.stringify(state.providerConfig));
  renderSetupChecklist();
  setStatus("模型配置已保存到本机浏览器。这个项目默认仅本地个人使用，请不要把页面暴露到公网。");
}

function clearProviderConfig() {
  state.providerConfig = structuredClone(defaultProviderConfig);
  localStorage.removeItem(PROVIDER_CONFIG_KEY);
  fillProviderForm(state.providerConfig);
  renderSetupChecklist();
  setStatus("模型配置已清空。填写 LLM 的 API Base、Model 和 API Key 后即可开始。");
}

async function handleVoiceInput() {
  ensureBackend();
  const config = readProviderConfig();
  if (config.asr.provider === "browser") {
    startBrowserSpeechRecognition();
    return;
  }
  if (state.realtimeSessionId && state.sessionId && window.WebSocket) {
    await toggleDuplexStreaming(config);
    return;
  }
  await toggleServerRecording(config);
}

async function toggleDuplexStreaming(config) {
  if (state.realtimeMode === "recording") {
    commitDuplexAudio();
    return;
  }
  if (state.realtimeMode === "speaking" || state.realtimeMode === "thinking") {
    cancelDuplexTurn();
    return;
  }
  await startDuplexStreaming(config);
}

async function startDuplexStreaming(config) {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mimeType = selectRecordingMimeType();
  const socket = new WebSocket(realtimeWebSocketUrl());
  state.mediaStream = stream;
  state.realtimeSocket = socket;
  state.realtimeMode = "connecting";
  state.ttsChunks = [];
  setStatus("正在建立实时语音通道。");

  socket.onopen = () => {
    socket.send(JSON.stringify({
      type: "start",
      provider_config: config,
      mime_type: mimeType || "audio/webm",
      partial_interval_chunks: 6,
      partial_window_chunks: 12,
      enable_partial_asr: true
    }));
    state.recordedChunks = [];
    state.mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    state.mediaRecorder.ondataavailable = (event) => sendDuplexAudioChunk(event.data);
    state.mediaRecorder.onstop = () => stopMediaStream();
    state.mediaRecorder.start(500);
    state.realtimeMode = "recording";
    elements.listenButton.textContent = "提交语音";
    setStatus("实时收音中。");
  };
  socket.onmessage = (event) => handleDuplexMessage(JSON.parse(event.data));
  socket.onerror = () => setStatus("实时语音通道异常。");
  socket.onclose = () => {
    resetRealtimeUi();
  };
}

async function sendDuplexAudioChunk(blob) {
  if (!blob || !blob.size || state.realtimeSocket?.readyState !== WebSocket.OPEN) return;
  state.realtimeSocket.send(JSON.stringify({
    type: "audio",
    data: await blobToBase64(blob)
  }));
}

function commitDuplexAudio() {
  if (state.mediaRecorder?.state === "recording") state.mediaRecorder.stop();
  stopMediaStream();
  if (state.realtimeSocket?.readyState === WebSocket.OPEN) {
    state.realtimeSocket.send(JSON.stringify({
      type: "commit",
      provider_config: readProviderConfig()
    }));
  }
  state.realtimeMode = "thinking";
  elements.listenButton.textContent = "取消";
  setStatus("正在端点检测、转写和生成反馈。");
}

function cancelDuplexTurn() {
  if (state.currentAudio) {
    state.currentAudio.pause();
    state.currentAudio = null;
  }
  resetPcmPlayback();
  if (state.mediaRecorder?.state === "recording") state.mediaRecorder.stop();
  stopMediaStream();
  if (state.realtimeSocket?.readyState === WebSocket.OPEN) {
    state.realtimeSocket.send(JSON.stringify({ type: "cancel" }));
  }
  state.realtimeMode = "idle";
  elements.listenButton.textContent = "语音输入";
  setStatus("已取消实时语音轮次。");
}

function handleDuplexMessage(message) {
  if (message.type === "ready" || message.type === "listening") return;
  if (message.type === "asr_partial") {
    if (message.text) elements.answer.value = message.text;
    setStatus(message.text ? `实时转写：${message.text}` : `已接收音频 ${message.audio_bytes || 0} 字节。`);
    return;
  }
  if (message.type === "vad_start") {
    setStatus("正在检测语音端点。");
    return;
  }
  if (message.type === "asr_start") {
    setStatus("正在转写语音。");
    return;
  }
  if (message.type === "asr_final") {
    elements.answer.value = "";
    if (message.text) addMessage("candidate", "候选人", message.text);
    return;
  }
  if (message.type === "turn") {
    const turn = message.turn;
    addMessage("interviewer", "反馈", turn.interviewer_message, turn.focus_tags);
    addMessage("interviewer", turn.is_finished ? "结束" : "问题", turn.next_question);
    showProviderNotice(turn.provider_notice);
    state.realtimeMode = "speaking";
    elements.listenButton.textContent = "取消";
    return;
  }
  if (message.type === "tts_text") {
    speakWithBrowser(message.text);
    return;
  }
  if (message.type === "tts_start") {
    state.ttsChunks = [];
    setStatus("正在接收语音播报。");
    return;
  }
  if (message.type === "tts_pcm_start") {
    startPcmPlayback(message);
    setStatus("正在流式播放语音。");
    return;
  }
  if (message.type === "tts_pcm_chunk") {
    queuePcmChunk(message.data);
    return;
  }
  if (message.type === "tts_audio_chunk") {
    state.ttsChunks.push(message.data);
    return;
  }
  if (message.type === "tts_done") {
    if (state.ttsChunks.length) playStreamedTts(message.format || "mp3");
    return;
  }
  if (message.type === "done") {
    resetRealtimeUi();
    if (message.skipped) setStatus(message.reason === "no_speech" ? "未检测到有效语音。" : "实时语音轮次已跳过。");
    else setStatus("实时语音轮次完成。");
    return;
  }
  if (message.type === "cancelled") {
    resetRealtimeUi();
    setStatus("实时语音轮次已取消。");
    return;
  }
  if (message.type === "error") {
    resetRealtimeUi();
    setStatus(`实时语音错误：${message.error}`);
  }
}

function resetRealtimeUi() {
  stopMediaStream();
  resetPcmPlayback();
  state.realtimeMode = "idle";
  state.realtimeSocket = null;
  elements.listenButton.textContent = "语音输入";
  elements.listenButton.disabled = !canUseVoiceInput();
  elements.sendButton.disabled = false;
}

function playStreamedTts(format) {
  if (!state.ttsChunks.length) return;
  const bytes = base64ChunksToUint8Array(state.ttsChunks);
  const blob = new Blob([bytes], { type: audioMimeType(format) });
  state.currentAudio = new Audio(URL.createObjectURL(blob));
  state.currentAudio.onended = () => {
    state.currentAudio = null;
  };
  state.currentAudio.play().catch((error) => setStatus(`语音播放失败：${error.message}`));
}

function startPcmPlayback(message) {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;
  if (!state.audioContext) state.audioContext = new AudioContextClass();
  state.pcmSampleRate = message.sample_rate || 16000;
  state.pcmChannels = message.channels || 1;
  state.pcmPlaybackTime = Math.max(state.audioContext.currentTime + 0.05, state.pcmPlaybackTime || 0);
}

function queuePcmChunk(base64Data) {
  if (!state.audioContext) startPcmPlayback({});
  if (!state.audioContext) return;
  const pcm = base64ToInt16Array(base64Data);
  const channels = Math.max(state.pcmChannels || 1, 1);
  const frameCount = Math.floor(pcm.length / channels);
  const buffer = state.audioContext.createBuffer(channels, frameCount, state.pcmSampleRate || 16000);
  for (let channel = 0; channel < channels; channel += 1) {
    const output = buffer.getChannelData(channel);
    for (let i = 0; i < frameCount; i += 1) {
      output[i] = pcm[i * channels + channel] / 32768;
    }
  }
  const source = state.audioContext.createBufferSource();
  source.buffer = buffer;
  source.connect(state.audioContext.destination);
  const startAt = Math.max(state.pcmPlaybackTime, state.audioContext.currentTime + 0.02);
  source.start(startAt);
  state.pcmPlaybackTime = startAt + buffer.duration;
}

function startBrowserSpeechRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    setStatus("当前浏览器不支持内置语音输入。");
    return;
  }
  const recognition = new Recognition();
  recognition.lang = "zh-CN";
  recognition.interimResults = false;
  recognition.onresult = (event) => {
    elements.answer.value = [elements.answer.value.trim(), event.results[0][0].transcript].filter(Boolean).join("\n");
  };
  recognition.onerror = () => setStatus("浏览器语音输入失败，可以继续使用文本回答。");
  recognition.start();
}

async function toggleServerRecording(config) {
  if (state.mediaRecorder?.state === "recording") {
    state.mediaRecorder.stop();
    return;
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "";
  state.recordedChunks = [];
  state.mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
  state.mediaRecorder.ondataavailable = (event) => {
    if (event.data.size > 0) state.recordedChunks.push(event.data);
  };
  state.mediaRecorder.onstop = async () => {
    stream.getTracks().forEach((track) => track.stop());
    elements.listenButton.textContent = "语音输入";
    const blob = new Blob(state.recordedChunks, { type: mimeType || "audio/webm" });
    try {
      if (state.realtimeSessionId && state.sessionId) {
        await submitRealtimeAudioTurn(blob, config);
      } else {
        const text = await transcribeWithServer(blob, config);
        elements.answer.value = [elements.answer.value.trim(), text].filter(Boolean).join("\n");
        setStatus("语音转写完成。");
      }
    } catch (error) {
      setStatus(`语音轮次失败：${error.message}`);
    }
  };
  state.mediaRecorder.start();
  elements.listenButton.textContent = "停止录音";
  setStatus("正在录音。");
}

async function transcribeWithServer(blob, config) {
  const payload = await postJson(`${API_BASE}/v1/asr/transcribe`, {
      audio_base64: await blobToBase64(blob),
      filename: "answer.webm",
      provider_config: config
    });
  return payload.text || "";
}

async function submitRealtimeAudioTurn(blob, config) {
  elements.listenButton.disabled = true;
  elements.sendButton.disabled = true;
  setStatus("正在转写并推进面试轮次。");
  try {
    const payload = await postJson(`${API_BASE}/v1/realtime/sessions/${state.realtimeSessionId}/audio-turn`, {
      audio_base64: await blobToBase64(blob),
      filename: "answer.webm",
      provider_config: config,
      submit_to_interview: true
    });
    if (payload.skipped) {
      setStatus(payload.reason === "no_speech" ? "未检测到有效语音。" : "语音轮次已跳过。");
      return;
    }
    const transcript = payload.transcript || "";
    const turn = payload.turn;
    if (transcript) addMessage("candidate", "候选人", transcript);
    if (turn) {
      addMessage("interviewer", "反馈", turn.interviewer_message, turn.focus_tags);
      addMessage("interviewer", turn.is_finished ? "结束" : "问题", turn.next_question);
      showProviderNotice(turn.provider_notice);
      speak(`${turn.interviewer_message} ${turn.next_question}`);
    }
    setStatus("语音轮次完成。");
  } finally {
    elements.listenButton.disabled = !canUseVoiceInput();
    elements.sendButton.disabled = false;
  }
}

async function speak(text) {
  const config = readProviderConfig();
  if (!elements.voiceOutput.checked || config.tts.provider === "disabled") return;
  if (config.tts.provider === "browser") {
    speakWithBrowser(text);
    return;
  }
  try {
    await speakWithServer(text, config);
  } catch (error) {
    setStatus(`TTS 调用失败：${error.message}`);
  }
}

function speakWithBrowser(text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  window.speechSynthesis.speak(utterance);
}

async function speakWithServer(text, config) {
  const response = await authedFetch(`${API_BASE}/v1/tts/speech`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ text, provider_config: config, voice_profile_id: elements.voiceProfile.value })
  });
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob();
  const audio = new Audio(URL.createObjectURL(blob));
  await audio.play();
}

function canUseVoiceInput() {
  const config = readProviderConfig();
  return Boolean(
    config.asr.provider !== "disabled" &&
      (navigator.mediaDevices || window.SpeechRecognition || window.webkitSpeechRecognition)
  );
}

function renderReport(report) {
  elements.report.hidden = false;
  elements.report.innerHTML = `
    <h3>面试报告：${escapeHtml(String(report.overall_score))} / 100</h3>
    ${report.ai_summary ? `<p>${escapeHtml(report.ai_summary)}</p>` : ""}
    <div class="score-grid">
      ${report.dimensions.map((item) => `
        <div class="score-item">
          <div class="score-value">${escapeHtml(String(item.score))}</div>
          <strong>${escapeHtml(item.name)}</strong>
          <p>${escapeHtml(item.advice || "")}</p>
        </div>
      `).join("")}
    </div>
    ${renderList("优势", report.strengths)}
    ${renderList("改进建议", report.improvements)}
    ${renderList("复习计划", report.review_plan)}
    ${renderPracticeDrills(report.practice_drills || [])}
    ${renderAnswerGuides(report.answer_guides || [])}
    ${renderTurnReview(report.turns || [])}
  `;
}

function renderPracticeDrills(drills) {
  if (!drills.length) return "";
  return `
    <h3>复练题</h3>
    <div class="turn-review">
      ${drills.map((drill) => `
        <div class="turn-review-item">
          <div class="turn-review-title">
            <strong>${escapeHtml(drill.topic || "practice")}</strong>
            <span>${escapeHtml(drill.focus || "")}</span>
          </div>
          <p>${escapeHtml(drill.prompt || "")}</p>
          ${Array.isArray(drill.target_structure) && drill.target_structure.length ? `
            <div class="tags">${drill.target_structure.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>
          ` : ""}
        </div>
      `).join("")}
    </div>
  `;
}

function renderAnswerGuides(guides) {
  if (!guides.length) return "";
  return `
    <h3>推荐回答结构 / 示例答案</h3>
    <div class="answer-guides">
      ${guides.map((guide) => `
        <article class="guide-item">
          <div class="turn-review-title">
            <strong>${escapeHtml(guide.topic || "interview")}</strong>
            <span>${escapeHtml(guide.focus || "")}</span>
          </div>
          <p class="guide-question">${escapeHtml(shortText(guide.question || "", 160))}</p>
          ${Array.isArray(guide.structure) && guide.structure.length ? `
            <ol class="guide-structure">
              ${guide.structure.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
            </ol>
          ` : ""}
          <div class="example-answer">${escapeHtml(guide.example_answer || "")}</div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderTurnReview(turns) {
  if (!turns.length) return "";
  return `
    <h3>逐题复盘</h3>
    <div class="turn-review">
      ${turns.map((turn, index) => {
        const meta = turn.question_meta || {};
        const gaps = turn.rubric_gaps || [];
        const title = meta.topic || meta.id || `第 ${index + 1} 题`;
        return `
          <div class="turn-review-item">
            <div class="turn-review-title">
              <strong>${escapeHtml(title)}</strong>
              <span>${escapeHtml(String(turn.score || 0))} 分</span>
            </div>
            <p>${escapeHtml(shortText(turn.question, 120))}</p>
            ${gaps.length ? `<div class="tags">${gaps.slice(0, 3).map((gap) => `<span class="tag">${escapeHtml(gap)}</span>`).join("")}</div>` : ""}
          </div>
        `;
      }).join("")}
    </div>
  `;
}

function shortText(value, maxLength) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}

function addMessage(role, title, content, tags = []) {
  state.messages.push({ role, title, content, tags });
  const node = document.createElement("article");
  node.className = `message ${role}`;
  node.innerHTML = `
    <div class="message-title"><strong>${escapeHtml(title)}</strong><span>${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}</span></div>
    <div class="message-content">${escapeHtml(content)}</div>
    ${tags.length ? `<div class="tags">${tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
  `;
  elements.conversation.appendChild(node);
  elements.conversation.scrollTop = elements.conversation.scrollHeight;
}

function renderList(title, items = []) {
  return `<h3>${escapeHtml(title)}</h3><ul class="report-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderMiniList(title, items = []) {
  return `<div><b>${escapeHtml(title)}：</b>${items.length ? items.map(escapeHtml).join("、") : "无"}</div>`;
}

function catalogName(group, id) {
  const item = (state.catalog[group] || []).find((candidate) => candidate.id === id);
  return item?.name || id || "";
}

function formatDate(value) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result || "").split(",")[1] || "");
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

function realtimeWebSocketUrl() {
  const url = new URL(API_BASE);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = `/v1/realtime/sessions/${state.realtimeSessionId}/duplex`;
  url.search = "";
  if (state.authRequired && state.localAuth?.api_token && state.localAuth?.user_id) {
    url.searchParams.set("token", state.localAuth.api_token);
    url.searchParams.set("user_id", state.localAuth.user_id);
  }
  return url.toString();
}

function selectRecordingMimeType() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  return candidates.find((item) => MediaRecorder.isTypeSupported(item)) || "";
}

function stopMediaStream() {
  if (state.mediaStream) {
    state.mediaStream.getTracks().forEach((track) => track.stop());
    state.mediaStream = null;
  }
}

function base64ChunksToUint8Array(chunks) {
  const binary = chunks.map((chunk) => atob(chunk)).join("");
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function base64ToInt16Array(base64Data) {
  const binary = atob(base64Data || "");
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return new Int16Array(bytes.buffer);
}

function resetPcmPlayback() {
  if (state.audioContext) {
    state.audioContext.close().catch(() => {});
    state.audioContext = null;
  }
  state.pcmPlaybackTime = 0;
}

function audioMimeType(format) {
  const normalized = String(format || "mp3").toLowerCase();
  if (normalized === "wav") return "audio/wav";
  if (normalized === "opus") return "audio/ogg";
  if (normalized === "aac") return "audio/aac";
  return "audio/mpeg";
}

async function fetchJson(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs || 8000);
  try {
    const response = await authedFetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function postJson(url, body) {
  const response = await authedFetch(url, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function deleteJson(url) {
  const response = await authedFetch(url, { method: "DELETE" });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function authedFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.authRequired && state.localAuth?.api_token && state.localAuth?.user_id) {
    headers.set("Authorization", `Bearer ${state.localAuth.api_token}`);
    headers.set("X-OpenInterview-User", state.localAuth.user_id);
  }
  const response = await fetch(url, { ...options, headers });
  if (!state.authRequired || response.status !== 401 || String(url).endsWith("/v1/users")) {
    return response;
  }
  localStorage.removeItem(LOCAL_AUTH_KEY);
  state.localAuth = null;
  await ensureLocalAuth();
  const retryHeaders = new Headers(options.headers || {});
  retryHeaders.set("Authorization", `Bearer ${state.localAuth.api_token}`);
  retryHeaders.set("X-OpenInterview-User", state.localAuth.user_id);
  return fetch(url, { ...options, headers: retryHeaders });
}

function jsonHeaders() {
  return { "Content-Type": "application/json" };
}

async function ensureLocalAuth() {
  if (state.localAuth?.api_token && state.localAuth?.user_id) return;
  const response = await fetch(`${API_BASE}/v1/users`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ display_name: "Local User" })
  });
  if (!response.ok) throw new Error(await response.text());
  state.localAuth = await response.json();
  localStorage.setItem(LOCAL_AUTH_KEY, JSON.stringify(state.localAuth));
}

function loadLocalAuth() {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_AUTH_KEY) || "null");
  } catch {
    localStorage.removeItem(LOCAL_AUTH_KEY);
    return null;
  }
}

function ensureBackend() {
  if (!state.backendReady) {
    throw new Error("后端不可用。请先启动 OpenInterview API。");
  }
}

function selectedName(select) {
  return select.options[select.selectedIndex]?.textContent || "";
}

function showProviderNotice(message) {
  if (message) setStatus(message);
}

function setStatus(message) {
  elements.runtimeStatus.textContent = message;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  })[char]);
}
