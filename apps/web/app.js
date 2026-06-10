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
    timeout_seconds: 45,
    allow_fallback: false
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

const llmTemplates = {
  openai: {
    provider: "openai_compatible",
    api_base: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    note: "OpenAI 官方 Chat Completions 兼容接口。"
  },
  deepseek: {
    provider: "openai_compatible",
    api_base: "https://api.deepseek.com",
    model: "deepseek-chat",
    note: "DeepSeek 官方 OpenAI 兼容接口，后端会自动拼接 /v1/chat/completions。"
  },
  dashscope: {
    provider: "openai_compatible",
    api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
    note: "阿里云百炼 OpenAI 兼容模式。"
  },
  siliconflow: {
    provider: "openai_compatible",
    api_base: "https://api.siliconflow.cn/v1",
    model: "Qwen/Qwen2.5-7B-Instruct",
    note: "SiliconFlow OpenAI 兼容接口，模型名可按控制台替换。"
  },
  moonshot: {
    provider: "openai_compatible",
    api_base: "https://api.moonshot.cn/v1",
    model: "moonshot-v1-8k",
    note: "Moonshot/Kimi OpenAI 兼容接口。"
  },
  ollama: {
    provider: "ollama",
    api_base: "http://127.0.0.1:11434",
    model: "qwen2.5:7b",
    note: "本地 Ollama，需先运行 ollama serve 并拉取模型。"
  },
  mock: {
    provider: "mock",
    api_base: "",
    model: "",
    note: "仅用于无 Key 演示流程，不是真实智能面试官。"
  }
};

const fallbackCatalog = {
  directions: [
    { id: "backend", name: "Java 后端", summary: "数据库、缓存、并发、分布式基础。" },
    { id: "ai_application", name: "AI 应用开发", summary: "LLM、Prompt、RAG、Agent、模型网关和语音应用。" }
  ],
  difficulties: [{ id: "campus", name: "普通校招", summary: "基础、项目、算法均衡。" }],
  modes: [{ id: "comprehensive", name: "综合模拟", summary: "完整流程。" }],
  interviewer_styles: [{ id: "small_company_basic", name: "中小厂基础型", summary: "真实一面节奏。" }],
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
  voiceConfig: null,
  providerConfig: loadProviderConfig()
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const elements = {
  direction: $("#direction"),
  difficulty: $("#difficulty"),
  mode: $("#mode"),
  interviewerStyle: $("#interviewer-style"),
  voiceProfile: $("#voice-profile"),
  candidateName: $("#candidate-name"),
  resume: $("#resume"),
  voiceOutput: $("#voice-output"),
  llmProvider: $("#llm-provider"),
  llmTemplate: $("#llm-template"),
  llmApiBase: $("#llm-api-base"),
  llmModel: $("#llm-model"),
  llmApiKey: $("#llm-api-key"),
  llmTemperature: $("#llm-temperature"),
  llmAllowFallback: $("#llm-allow-fallback"),
  voiceMode: $("#voice-mode"),
  voiceModeHelp: $("#voice-mode-help"),
  localVoicePaths: $("#local-voice-paths"),
  localVadModel: $("#local-vad-model"),
  localAsrModelDir: $("#local-asr-model-dir"),
  localTtsModelDir: $("#local-tts-model-dir"),
  localCosyvoicePath: $("#local-cosyvoice-path"),
  voiceApiFields: $$(".voice-api-field"),
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
  saveLocalVoiceConfig: $("#save-local-voice-config"),
  testLlmConfig: $("#test-llm-config"),
  testAsrConfig: $("#test-asr-config"),
  testTtsConfig: $("#test-tts-config"),
  testVoiceConfig: $("#test-voice-config"),
  clearProviderConfig: $("#clear-provider-config"),
  setupForm: $("#setup-form"),
  runtimeStatus: $("#runtime-status"),
  setupChecklist: $("#setup-checklist"),
  resumePanel: $("#resume-panel"),
  resumeFile: $("#resume-file"),
  sessionTitle: $("#session-title"),
  conversation: $("#conversation"),
  answerForm: $("#answer-form"),
  answer: $("#answer"),
  sendButton: $("#send-button"),
  listenButton: $("#listen-button"),
  reportButton: $("#report-button"),
  coverageButton: $("#coverage-button"),
  reviewItemsButton: $("#review-items-button"),
  historyButton: $("#history-button"),
  importResumeButton: $("#import-resume-button"),
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
    state.voiceConfig = await fetchJson(`${API_BASE}/v1/voice/config`, { timeoutMs: 3000 });
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
  fillSelect(elements.interviewerStyle, state.catalog.interviewer_styles || fallbackCatalog.interviewer_styles);
  fillSelect(elements.voiceProfile, state.catalog.voice_profiles || [], "id", "name");
  fillLocalVoiceForm(state.voiceConfig);
  fillProviderForm(state.providerConfig);
  wireEvents();
  renderSetupChecklist();
  if (state.backendReady) refreshReadiness();
}

function wireEvents() {
  elements.setupForm.addEventListener("submit", safeHandler(startInterview));
  elements.answerForm.addEventListener("submit", safeHandler(submitAnswer));
  elements.reportButton.addEventListener("click", safeHandler(generateReport));
  elements.coverageButton.addEventListener("click", safeHandler(loadQuestionCoverage));
  elements.reviewItemsButton.addEventListener("click", safeHandler(loadReviewItems));
  elements.listenButton.addEventListener("click", safeHandler(handleVoiceInput));
  elements.saveProviderConfig.addEventListener("click", safeHandler(saveProviderConfig));
  elements.saveLocalVoiceConfig.addEventListener("click", safeHandler(() => saveLocalVoiceConfig()));
  elements.testLlmConfig.addEventListener("click", safeHandler(testLlmConfig));
  elements.testAsrConfig.addEventListener("click", safeHandler(testAsrConfig));
  elements.testTtsConfig.addEventListener("click", safeHandler(testTtsConfig));
  elements.testVoiceConfig.addEventListener("click", safeHandler(testVoiceConfig));
  elements.clearProviderConfig.addEventListener("click", clearProviderConfig);
  elements.llmTemplate.addEventListener("change", applyLlmTemplate);
  elements.voiceMode.addEventListener("change", () => {
    applyVoiceMode(elements.voiceMode.value);
    renderSetupChecklist();
  });
  [elements.localVadModel, elements.localAsrModelDir, elements.localTtsModelDir, elements.localCosyvoicePath].forEach((input) => {
    input.addEventListener("input", () => {
      if (elements.voiceMode.value === "local") syncLocalPathsToProviderFields();
      renderSetupChecklist();
    });
  });
  elements.importResumeButton.addEventListener("click", safeHandler(importResumeFile));
  elements.analyzeResumeButton.addEventListener("click", safeHandler(analyzeResume));
  elements.historyButton.addEventListener("click", safeHandler(loadHistory));
  providerInputs().forEach((input) => {
    input.addEventListener("input", renderSetupChecklist);
    input.addEventListener("change", renderSetupChecklist);
  });
  [elements.direction, elements.difficulty, elements.mode, elements.interviewerStyle, elements.voiceProfile].forEach((input) => {
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
    ${renderMiniList("个人贡献", result.contributions)}
    ${renderMiniList("模糊/易被质疑表述", result.vague_claims)}
    ${renderMiniList("风险", result.risks)}
    ${renderResumeProjectCards(result.project_cards || [])}
    ${renderResumeQuestionList("指标来源追问", result.metric_questions)}
    ${renderResumeQuestionList("技术选型追问", result.tech_choice_questions)}
    ${renderResumeQuestionList("故障复盘追问", result.incident_questions)}
  `;
}

async function importResumeFile() {
  ensureBackend();
  const file = elements.resumeFile.files?.[0];
  if (!file) {
    throw new Error("请先选择 .txt、.md、.pdf 或 .docx 简历文件。");
  }
  const body = new FormData();
  body.append("file", file);
  elements.importResumeButton.disabled = true;
  setStatus(`正在本地解析简历文件：${file.name}`);
  try {
    const response = await authedFetch(`${API_BASE}/v1/resume/extract`, {
      method: "POST",
      body
    });
    if (!response.ok) throw new Error(await response.text());
    const payload = await response.json();
    elements.resume.value = payload.text;
    renderSetupChecklist();
    setStatus(`已导入 ${payload.filename}，提取 ${payload.chars} 个字符。`);
    await analyzeResume();
  } finally {
    elements.importResumeButton.disabled = false;
  }
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
          <button id="import-history-button" class="secondary" type="button">导入历史</button>
          <button id="clear-history-button" class="secondary danger-action" type="button">清空历史</button>
        </div>
      </div>
      <p class="muted-text">还没有本地面试记录。完成一轮面试后，这里会显示报告和复练入口。</p>
    `;
    $("#export-history-button")?.addEventListener("click", safeHandler(exportHistory));
    $("#import-history-button")?.addEventListener("click", safeHandler(importHistory));
    $("#clear-history-button")?.addEventListener("click", safeHandler(clearHistory));
    return;
  }
  elements.report.innerHTML = `
    <div class="section-heading">
      <h3>历史记录</h3>
      <div class="inline-actions">
        <button id="export-history-button" class="secondary" type="button">导出历史</button>
        <button id="import-history-button" class="secondary" type="button">导入历史</button>
        <button id="clear-history-button" class="secondary danger-action" type="button">清空历史</button>
      </div>
    </div>
    <div class="history-list">
      ${interviews.map((item) => {
        const config = item.config || {};
        const summary = [
          catalogName("directions", config.direction_id),
          catalogName("difficulties", config.difficulty_id),
          catalogName("modes", config.mode_id),
          catalogName("interviewer_styles", config.interviewer_style_id)
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
              <button class="secondary" type="button" data-history-md="${escapeHtml(item.id)}">导出 MD</button>
              <button class="secondary" type="button" data-history-review="${escapeHtml(item.id)}">入错题本</button>
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
  elements.report.querySelectorAll("[data-history-md]").forEach((button) => {
    button.addEventListener("click", safeHandler(() => exportReportMarkdown(button.dataset.historyMd)));
  });
  elements.report.querySelectorAll("[data-history-review]").forEach((button) => {
    button.addEventListener("click", safeHandler(() => createReviewItems(button.dataset.historyReview)));
  });
  $("#export-history-button")?.addEventListener("click", safeHandler(exportHistory));
  $("#import-history-button")?.addEventListener("click", safeHandler(importHistory));
  $("#clear-history-button")?.addEventListener("click", safeHandler(clearHistory));
}

async function loadQuestionCoverage() {
  ensureBackend();
  const directionId = elements.direction.value || "backend";
  const payload = await fetchJson(`${API_BASE}/v1/questions/coverage?direction_id=${encodeURIComponent(directionId)}`);
  renderQuestionCoverage(payload);
  setStatus(`题库覆盖：${selectedName(elements.direction)} ${payload.total} 道，优先补红色和黄色主题。`);
}

function renderQuestionCoverage(payload) {
  elements.report.hidden = false;
  elements.report.innerHTML = `
    <div class="section-heading">
      <h3>${escapeHtml(selectedName(elements.direction) || "当前方向")}题库覆盖</h3>
      <span class="muted-text">${escapeHtml(String(payload.total || 0))} 道题</span>
    </div>
    <div class="coverage-grid">
      ${(payload.topics || []).map((item) => `
        <article class="coverage-item ${escapeHtml(item.status || "warn")}">
          <div class="turn-review-title">
            <strong>${escapeHtml(item.topic)}</strong>
            <span>${escapeHtml(String(item.count || 0))} 题</span>
          </div>
          <p>${escapeHtml(item.next_action || "")}</p>
          <div class="tags">
            <span class="tag">追问 ${escapeHtml(String(item.with_followups || 0))}</span>
            <span class="tag">评分点 ${escapeHtml(String(item.with_rubric || 0))}</span>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

async function loadReviewItems() {
  ensureBackend();
  const payload = await fetchJson(`${API_BASE}/v1/review-items`);
  renderReviewItems(payload.items || []);
  setStatus(`错题本：${payload.items.length} 条。`);
}

function renderReviewItems(items) {
  elements.report.hidden = false;
  elements.report.innerHTML = `
    <div class="section-heading">
      <h3>错题本</h3>
      <div class="inline-actions">
        <button id="clear-review-items-button" class="secondary danger-action" type="button">清空错题</button>
      </div>
    </div>
    ${items.length ? `
      <div class="turn-review">
        ${items.map((item) => `
          <article class="turn-review-item">
            <div class="turn-review-title">
              <strong>${escapeHtml(item.topic || "interview")}</strong>
              <span>${escapeHtml(statusLabel(item.status))} / ${escapeHtml(String(item.score || 0))} 分</span>
            </div>
            <p>${escapeHtml(shortText(item.question || "", 180))}</p>
            ${(item.gaps || []).length ? `<div class="tags">${item.gaps.slice(0, 3).map((gap) => `<span class="tag">${escapeHtml(gap)}</span>`).join("")}</div>` : ""}
            ${renderGuideList("重答建议", item.rewrite_advice)}
            <div class="history-actions review-actions">
              <button class="secondary" type="button" data-review-status="${escapeHtml(item.id)}" data-status="todo">待复习</button>
              <button class="secondary" type="button" data-review-status="${escapeHtml(item.id)}" data-status="practicing">复练中</button>
              <button class="secondary" type="button" data-review-status="${escapeHtml(item.id)}" data-status="mastered">已掌握</button>
              <button class="secondary danger-action" type="button" data-review-delete="${escapeHtml(item.id)}">删除</button>
            </div>
          </article>
        `).join("")}
      </div>
    ` : `<p class="muted-text">还没有错题。先在历史里点击“入错题本”，或生成报告后加入。</p>`}
  `;
  elements.report.querySelectorAll("[data-review-status]").forEach((button) => {
    button.addEventListener("click", safeHandler(() => updateReviewStatus(button.dataset.reviewStatus, button.dataset.status)));
  });
  elements.report.querySelectorAll("[data-review-delete]").forEach((button) => {
    button.addEventListener("click", safeHandler(() => deleteReviewItem(button.dataset.reviewDelete)));
  });
  $("#clear-review-items-button")?.addEventListener("click", safeHandler(clearReviewItems));
}

async function updateReviewStatus(itemId, status) {
  await patchJson(`${API_BASE}/v1/review-items/${itemId}`, { status });
  await loadReviewItems();
}

async function deleteReviewItem(itemId) {
  await deleteJson(`${API_BASE}/v1/review-items/${itemId}`);
  await loadReviewItems();
}

async function clearReviewItems() {
  const ok = window.confirm("确认清空全部错题本？不会删除面试历史。");
  if (!ok) return;
  const payload = await deleteJson(`${API_BASE}/v1/review-items`);
  setStatus(`已清空 ${payload.deleted || 0} 条错题。`);
  await loadReviewItems();
}

async function createReviewItems(sessionId) {
  const payload = await postJson(`${API_BASE}/v1/interviews/${sessionId}/review-items`, {});
  setStatus(`已加入 ${payload.created || 0} 条错题/复练项。`);
  await loadReviewItems();
}

async function exportReportMarkdown(sessionId) {
  const response = await authedFetch(`${API_BASE}/v1/interviews/${sessionId}/report.md`);
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `openinterview-report-${sessionId.slice(0, 8)}.md`;
  downloadBlob(blob, filename);
  setStatus("Markdown 报告已导出。");
}

async function exportHistory() {
  ensureBackend();
  const response = await authedFetch(`${API_BASE}/v1/interviews/export`);
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const filename = disposition.match(/filename="([^"]+)"/)?.[1] || `openinterview-history-${Date.now()}.json`;
  downloadBlob(blob, filename);
  setStatus("历史记录已导出为 JSON 文件。");
}

async function importHistory() {
  ensureBackend();
  const file = await pickJsonFile();
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  setStatus(`正在导入历史：${file.name}`);
  const response = await authedFetch(`${API_BASE}/v1/interviews/import`, {
    method: "POST",
    body
  });
  if (!response.ok) throw new Error(await response.text());
  const payload = await response.json();
  const imported = payload.imported || {};
  state.sessionId = null;
  state.realtimeSessionId = null;
  elements.reportButton.disabled = true;
  await loadHistory();
  setStatus(
    `历史导入完成：${imported.interviews || 0} 场面试，${imported.turns || 0} 条回答，${imported.review_items || 0} 条错题。`
  );
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

function pickJsonFile() {
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json,application/json";
    input.addEventListener("change", () => {
      resolve(input.files?.[0] || null);
      input.remove();
    });
    input.addEventListener("cancel", () => {
      resolve(null);
      input.remove();
    });
    input.style.display = "none";
    document.body.appendChild(input);
    input.click();
  });
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
    ${renderStudyGuides(report.study_guides || [])}
  `;
  setStatus("已打开历史复练题。");
}

function readConfig() {
  return {
    direction_id: elements.direction.value,
    difficulty_id: elements.difficulty.value,
    mode_id: elements.mode.value,
    interviewer_style_id: elements.interviewerStyle.value || "small_company_basic",
    candidate_name: elements.candidateName.value.trim() || null,
    resume_text: elements.resume.value.trim() || null,
    duration_minutes: 30,
    language: "zh-CN",
    provider_config: readProviderConfig()
  };
}

function readProviderConfig() {
  const voiceMode = elements.voiceMode?.value || detectVoiceMode({
    asr: { provider: elements.asrProvider.value },
    tts: { provider: elements.ttsProvider.value }
  });
  const localVoice = readLocalVoiceForm();
  const asrModel = voiceMode === "local" ? localVoice.asr_model_dir : elements.asrModel.value.trim();
  const ttsModel = voiceMode === "local" ? localVoice.tts_model_dir : elements.ttsModel.value.trim();
  return {
    llm: {
      provider: elements.llmProvider.value,
      api_base: elements.llmApiBase.value.trim(),
      model: elements.llmModel.value.trim(),
      api_key: elements.llmApiKey.value.trim(),
      temperature: Number(elements.llmTemperature.value || 0.4),
      timeout_seconds: 45,
      allow_fallback: elements.llmAllowFallback.checked
    },
    asr: {
      provider: elements.asrProvider.value,
      api_base: elements.asrApiBase.value.trim(),
      model: asrModel,
      api_key: elements.asrApiKey.value.trim(),
      language: "zh-CN",
      timeout_seconds: 60,
      device: "auto"
    },
    tts: {
      provider: elements.ttsProvider.value,
      api_base: elements.ttsApiBase.value.trim(),
      model: ttsModel,
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
    if (state.readiness?.voice_config) {
      state.voiceConfig = {
        ...(state.voiceConfig || {}),
        ...state.readiness.voice_config
      };
      fillLocalVoiceForm(state.voiceConfig);
    }
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
      const diagnostic = result.diagnostic;
      const hint = diagnostic?.hint ? `建议：${diagnostic.hint}` : "";
      const category = diagnostic?.category ? `类型：${diagnostic.category}。` : "";
      throw new Error(`${result.message || "LLM 连接测试失败。"} ${category}${hint}`);
    }
    setStatus(`${result.message}${result.sample ? ` 返回：${result.sample}` : ""}`);
  } finally {
    elements.testLlmConfig.disabled = false;
    renderSetupChecklist();
  }
}

async function testAsrConfig() {
  ensureBackend();
  if (elements.voiceMode.value === "local") {
    syncLocalPathsToProviderFields();
  }
  const config = readProviderConfig();
  if (config.asr.provider === "disabled") {
    throw new Error("ASR 已关闭。需要语音输入时请先选择 Browser、Local SenseVoice 或 API ASR。");
  }
  elements.testAsrConfig.disabled = true;
  try {
    if (config.asr.provider === "sensevoice") {
      const missing = localVoiceMissingFields(["asr_model_dir"]);
      if (missing.length) throw new Error(`本地 ASR 配置缺少 ${missing.join("、")}。`);
      await saveLocalVoiceConfig({ quiet: true });
    }
    if (config.asr.provider === "browser") {
      assertBrowserAsrSupported();
      await assertMicrophoneAvailable();
      setStatus("浏览器 ASR 环境可用。真实识别会在点击“语音输入”后开始。");
      return;
    }
    if (config.asr.provider === "sensevoice") {
      const smoke = await fetchJson(`${API_BASE}/v1/readiness/smoke?include_voice=true&voice_check=asr`, { timeoutMs: 30000 });
      const asr = smoke.checks?.asr;
      if (!asr?.ok) throw new Error(asr?.error || "Local SenseVoice 自检失败。");
      setStatus(`Local SenseVoice 自检通过。${asr.text_chars ? `转写返回 ${asr.text_chars} 个字符。` : ""}`);
      await refreshReadiness();
      return;
    }
    const missing = providerMissingFields(config.asr);
    if (missing.length) throw new Error(`API ASR 配置缺少 ${missing.join("、")}。`);
    await assertMicrophoneAvailable();
    setStatus("API ASR 配置和麦克风权限正常。实际转写需要点击面试中的“语音输入”录制一段回答。");
  } finally {
    elements.testAsrConfig.disabled = false;
    renderSetupChecklist();
  }
}

async function testTtsConfig() {
  ensureBackend();
  if (elements.voiceMode.value === "local") {
    syncLocalPathsToProviderFields();
  }
  const config = readProviderConfig();
  if (config.tts.provider === "disabled") {
    throw new Error("TTS 已关闭。需要语音播报时请先选择 Browser、Local CosyVoice 或 API TTS。");
  }
  elements.testTtsConfig.disabled = true;
  try {
    if (config.tts.provider === "cosyvoice") {
      const missing = localVoiceMissingFields(["tts_model_dir", "cosyvoice_path"]);
      if (missing.length) throw new Error(`本地 TTS 配置缺少 ${missing.join("、")}。`);
      await saveLocalVoiceConfig({ quiet: true });
    }
    if (config.tts.provider === "browser") {
      speakWithBrowser("OpenInterview 语音播报测试。");
      setStatus("浏览器 TTS 已触发。如果没有声音，请检查系统音量或浏览器自动播放权限。");
      return;
    }
    const missing = config.tts.provider === "cosyvoice" ? [] : providerMissingFields(config.tts);
    if (missing.length) throw new Error(`API TTS 配置缺少 ${missing.join("、")}。`);
    await speakWithServer("OpenInterview 语音播报测试。", config);
    setStatus("TTS 测试通过，已播放测试语音。");
  } finally {
    elements.testTtsConfig.disabled = false;
    renderSetupChecklist();
  }
}

async function testVoiceConfig() {
  ensureBackend();
  elements.testVoiceConfig.disabled = true;
  setStatus("正在执行语音自检。");
  try {
    if (elements.voiceMode.value === "local") {
      const missing = localVoiceMissingFields(["vad_model", "asr_model_dir", "tts_model_dir", "cosyvoice_path"]);
      if (missing.length) throw new Error(`本地语音配置缺少 ${missing.join("、")}。`);
      await saveLocalVoiceConfig({ quiet: true });
    }
    const config = readProviderConfig();
    const browserAsr = Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
    const browserTts = Boolean(window.speechSynthesis);
    const microphone = navigator.mediaDevices?.getUserMedia ? "可请求" : "不可用";
    let localVoice = "未检查";
    if (config.asr.provider === "sensevoice" || config.tts.provider === "cosyvoice") {
      const smoke = await fetchJson(`${API_BASE}/v1/readiness/smoke?include_voice=true`, { timeoutMs: 30000 });
      localVoice = smoke.ok ? "本地语音自检通过" : `本地语音自检失败：${voiceSmokeError(smoke)}`;
      await refreshReadiness();
    }
    setStatus(`语音自检：浏览器 ASR ${browserAsr ? "可用" : "不可用"}；浏览器 TTS ${browserTts ? "可用" : "不可用"}；麦克风 ${microphone}；${localVoice}。`);
  } finally {
    elements.testVoiceConfig.disabled = false;
    renderSetupChecklist();
  }
}

function localVoiceMissingFields(required) {
  const config = readLocalVoiceForm();
  const labels = {
    vad_model: "VAD ONNX 路径",
    asr_model_dir: "SenseVoice 模型目录",
    tts_model_dir: "CosyVoice 模型目录",
    cosyvoice_path: "CosyVoice runtime 路径"
  };
  return required.filter((key) => !config[key]).map((key) => labels[key] || key);
}

function providerMissingFields(settings) {
  const missing = [];
  if (!settings.api_base) missing.push("API Base");
  if (!settings.model) missing.push("Model");
  if (!settings.api_key) missing.push("API Key");
  return missing;
}

function assertBrowserAsrSupported() {
  if (!(window.SpeechRecognition || window.webkitSpeechRecognition)) {
    throw new Error("当前浏览器不支持内置 ASR。建议使用 Chrome/Edge，或切换到 Local SenseVoice/API ASR。");
  }
}

async function assertMicrophoneAvailable() {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("当前浏览器或页面环境不支持麦克风访问。建议使用 http://127.0.0.1 本地地址打开。");
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (error) {
    throw new Error(microphoneErrorMessage(error));
  } finally {
    stream?.getTracks().forEach((track) => track.stop());
  }
}

function microphoneErrorMessage(error) {
  const name = error?.name || "";
  if (name === "NotAllowedError" || name === "PermissionDeniedError") {
    return "麦克风权限被拒绝。请在浏览器地址栏权限设置里允许麦克风，然后重试。";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "没有检测到可用麦克风。请连接麦克风或检查系统输入设备。";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "麦克风被其他应用占用或系统暂时不可读。请关闭占用麦克风的软件后重试。";
  }
  if (name === "SecurityError") {
    return "浏览器安全策略阻止麦克风访问。请使用本地 http://127.0.0.1 或可信来源打开页面。";
  }
  return `麦克风启动失败：${error?.message || String(error)}`;
}

function voiceSmokeError(smoke) {
  const failed = Object.entries(smoke.checks || {}).find(([, item]) => !item.ok);
  if (!failed) return "未知错误";
  return `${failed[0]} ${failed[1].error || "未通过"}`;
}

function applyLlmTemplate() {
  const template = llmTemplates[elements.llmTemplate.value];
  if (!template) return;
  elements.llmProvider.value = template.provider;
  elements.llmApiBase.value = template.api_base;
  elements.llmModel.value = template.model;
  if (template.provider === "mock" || template.provider === "ollama") {
    elements.llmApiKey.value = "";
  }
  renderSetupChecklist();
  setStatus(`已应用 LLM 模板：${template.note}`);
}

function detectVoiceMode(config = readProviderConfig()) {
  const asrProvider = config.asr.provider;
  const ttsProvider = config.tts.provider;
  if (asrProvider === "disabled" && ttsProvider === "disabled") return "disabled";
  if (asrProvider === "sensevoice" || ttsProvider === "cosyvoice") return "local";
  if (asrProvider === "openai_compatible" || ttsProvider === "openai_compatible") return "api";
  return "browser";
}

function applyVoiceMode(mode, options = {}) {
  const nextMode = mode || "browser";
  elements.voiceMode.value = nextMode;
  if (nextMode === "browser") {
    elements.asrProvider.value = "browser";
    elements.ttsProvider.value = "browser";
  } else if (nextMode === "api") {
    elements.asrProvider.value = "openai_compatible";
    elements.ttsProvider.value = "openai_compatible";
  } else if (nextMode === "local") {
    elements.asrProvider.value = "sensevoice";
    elements.ttsProvider.value = "cosyvoice";
    syncLocalPathsToProviderFields();
  } else {
    elements.asrProvider.value = "disabled";
    elements.ttsProvider.value = "disabled";
  }
  updateVoiceModeUi();
  if (!options.silent) {
    setStatus(voiceModeStatus(nextMode));
  }
}

function updateVoiceModeUi() {
  const mode = elements.voiceMode.value || "browser";
  const showApi = mode === "api";
  const showLocal = mode === "local";
  elements.voiceApiFields.forEach((node) => {
    node.hidden = !showApi;
  });
  elements.localVoicePaths.hidden = !showLocal;
  elements.saveLocalVoiceConfig.hidden = !showLocal;
  elements.voiceModeHelp.textContent = voiceModeHelpText(mode);
}

function voiceModeHelpText(mode) {
  if (mode === "api") return "语音 API 的 Key 只保存在当前浏览器，不写入后端配置文件。";
  if (mode === "local") return "本地路径会写入 configs/voice-models.local.yaml，文件已被 git 忽略。";
  if (mode === "disabled") return "关闭后仍可正常使用文本面试。";
  return "最快跑通方式：浏览器负责麦克风识别和播报，不需要下载语音模型。";
}

function voiceModeStatus(mode) {
  if (mode === "api") return "已切到云端语音 API。请填写 ASR/TTS 的 URL、模型名和 Key，然后分别测试。";
  if (mode === "local") return "已切到本地语音模型。填写模型目录后保存本地路径，再执行语音自检。";
  if (mode === "disabled") return "语音已关闭，文本面试不受影响。";
  return "已切到浏览器语音。通常无需额外配置，只需允许麦克风权限。";
}

function fillLocalVoiceForm(config) {
  if (!config) return;
  elements.localVadModel.value = config.vad_model || "";
  elements.localAsrModelDir.value = config.asr_model_dir || "";
  elements.localTtsModelDir.value = config.tts_model_dir || "";
  elements.localCosyvoicePath.value = config.cosyvoice_path || "";
  if (elements.voiceMode.value === "local") syncLocalPathsToProviderFields();
}

function readLocalVoiceForm() {
  return {
    vad_model: elements.localVadModel.value.trim(),
    asr_model_dir: elements.localAsrModelDir.value.trim(),
    tts_model_dir: elements.localTtsModelDir.value.trim(),
    cosyvoice_path: elements.localCosyvoicePath.value.trim()
  };
}

function syncLocalPathsToProviderFields() {
  const local = readLocalVoiceForm();
  elements.asrModel.value = local.asr_model_dir;
  elements.ttsModel.value = local.tts_model_dir;
}

async function saveLocalVoiceConfig({ quiet = false } = {}) {
  ensureBackend();
  const config = readLocalVoiceForm();
  elements.saveLocalVoiceConfig.disabled = true;
  try {
    state.voiceConfig = await postJson(`${API_BASE}/v1/voice/config`, config);
    fillLocalVoiceForm(state.voiceConfig);
    syncLocalPathsToProviderFields();
    await refreshReadiness();
    if (!quiet) {
      setStatus(`本地语音路径已保存：${state.voiceConfig.editable_models_config || "local config"}。`);
    }
  } finally {
    elements.saveLocalVoiceConfig.disabled = false;
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
      detail: `${selectedName(elements.mode) || "默认模式"} / ${selectedName(elements.interviewerStyle) || "默认风格"}`
    },
    asrChecklistItem(config.asr),
    ttsChecklistItem(config.tts),
    resumeChecklistItem()
  ];
  if (elements.voiceMode.value === "local") {
    items.splice(4, 0, localVoiceChecklistItem());
  }
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
    status: missing.length ? "bad" : llm.allow_fallback ? "warn" : "ok",
    detail: missing.length
      ? `缺少 ${missing.join("、")}`
      : llm.allow_fallback
        ? `${llm.model} 已配置，但真实调用失败时会回退到 Mock`
        : `${llm.model} 已配置，失败时不会静默回退`
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
    const modelPath = state.readiness?.voice_config?.asr_model_dir || asr.model || "未填写";
    return {
      label: "语音输入",
      status: ok ? "ok" : "warn",
      detail: ok ? `Local SenseVoice 已就绪：${modelPath}` : `Local SenseVoice 未就绪：${modelPath}`
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
    const modelPath = state.readiness?.voice_config?.tts_model_dir || tts.model || "未填写";
    return {
      label: "语音播报",
      status: state.readiness?.ready_for_local_voice ? "ok" : "warn",
      detail: state.readiness?.ready_for_local_voice ? `Local CosyVoice 已就绪：${modelPath}` : `Local CosyVoice 未就绪：${modelPath}`
    };
  }
  const ready = Boolean(tts.api_base && tts.model && tts.api_key);
  return {
    label: "语音播报",
    status: ready ? "ok" : "warn",
    detail: ready ? "API TTS 已配置" : "API TTS 缺少 URL、模型名或 Key"
  };
}

function localVoiceChecklistItem() {
  const missing = localVoiceMissingFields(["vad_model", "asr_model_dir", "tts_model_dir", "cosyvoice_path"]);
  if (missing.length) {
    return {
      label: "本地语音路径",
      status: "warn",
      detail: `缺少 ${missing.join("、")}`
    };
  }
  const configPath = state.readiness?.voice_config?.editable_models_config || state.voiceConfig?.editable_models_config || "configs/voice-models.local.yaml";
  return {
    label: "本地语音路径",
    status: "ok",
    detail: `将保存到 ${configPath}`
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
    elements.llmAllowFallback,
    elements.voiceMode,
    elements.localVadModel,
    elements.localAsrModelDir,
    elements.localTtsModelDir,
    elements.localCosyvoicePath,
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
  elements.llmAllowFallback.checked = Boolean(config.llm.allow_fallback);
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
  applyVoiceMode(detectVoiceMode(config), { silent: true });
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

async function saveProviderConfig() {
  if (elements.voiceMode.value === "local") {
    syncLocalPathsToProviderFields();
    await saveLocalVoiceConfig({ quiet: true });
  }
  state.providerConfig = readProviderConfig();
  localStorage.setItem(PROVIDER_CONFIG_KEY, JSON.stringify(state.providerConfig));
  renderSetupChecklist();
  const localNote = elements.voiceMode.value === "local" ? "本地语音路径已写入本机 YAML。" : "";
  setStatus(`模型配置已保存到本机浏览器。${localNote}这个项目默认仅本地个人使用，请不要把页面暴露到公网。`);
}

function clearProviderConfig() {
  state.providerConfig = structuredClone(defaultProviderConfig);
  localStorage.removeItem(PROVIDER_CONFIG_KEY);
  fillProviderForm(state.providerConfig);
  applyVoiceMode("browser", { silent: true });
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
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("当前浏览器不支持录音。请改用文本回答，或使用 Chrome/Edge 打开本地页面。");
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
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("当前浏览器不支持麦克风录音。请改用普通文本回答。");
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (error) {
    throw new Error(microphoneErrorMessage(error));
  }
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
  socket.onerror = () => setStatus("实时语音通道异常。可切换到普通录音或文本回答。");
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
    elements.sendButton.disabled = true;
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
    setStatus(`实时语音错误：${message.error}。可切换到普通录音或文本回答。`);
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
  const url = URL.createObjectURL(blob);
  state.currentAudio = new Audio(url);
  state.currentAudio.onended = () => {
    URL.revokeObjectURL(url);
    state.currentAudio = null;
    elements.sendButton.disabled = false;
  };
  state.currentAudio.onerror = () => {
    URL.revokeObjectURL(url);
    state.currentAudio = null;
    elements.sendButton.disabled = false;
    setStatus("语音播放失败，请检查浏览器音频权限或音频格式。");
  };
  state.currentAudio.play().catch((error) => {
    URL.revokeObjectURL(url);
    state.currentAudio = null;
    elements.sendButton.disabled = false;
    setStatus(`语音播放失败：${error.message}`);
  });
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
    setStatus("当前浏览器不支持内置语音输入。建议使用 Chrome/Edge，或切换到文本回答。");
    return;
  }
  const recognition = new Recognition();
  recognition.lang = "zh-CN";
  recognition.interimResults = false;
  recognition.onstart = () => {
    elements.listenButton.disabled = true;
    setStatus("浏览器正在听写。请说出你的回答。");
  };
  recognition.onresult = (event) => {
    elements.answer.value = [elements.answer.value.trim(), event.results[0][0].transcript].filter(Boolean).join("\n");
  };
  recognition.onerror = (event) => setStatus(`浏览器语音输入失败：${browserRecognitionErrorMessage(event)}。可以继续使用文本回答。`);
  recognition.onend = () => {
    elements.listenButton.disabled = !canUseVoiceInput();
    setStatus(elements.answer.value.trim() ? "浏览器语音输入完成。" : "浏览器语音输入结束，未收到可用文本。");
  };
  try {
    recognition.start();
  } catch (error) {
    elements.listenButton.disabled = !canUseVoiceInput();
    setStatus(`浏览器语音输入启动失败：${error.message}`);
  }
}

async function toggleServerRecording(config) {
  if (state.mediaRecorder?.state === "recording") {
    state.mediaRecorder.stop();
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (error) {
    throw new Error(microphoneErrorMessage(error));
  }
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
    } finally {
      elements.sendButton.disabled = false;
      elements.listenButton.disabled = !canUseVoiceInput();
    }
  };
  state.mediaRecorder.start();
  elements.listenButton.textContent = "停止录音";
  elements.sendButton.disabled = true;
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
  if (!window.speechSynthesis) {
    setStatus("当前浏览器不支持语音播报。");
    return;
  }
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "zh-CN";
  utterance.onerror = (event) => setStatus(`浏览器语音播报失败：${event.error || "未知错误"}`);
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
  if (state.currentAudio) {
    state.currentAudio.pause();
    state.currentAudio = null;
  }
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  state.currentAudio = audio;
  audio.onended = () => {
    URL.revokeObjectURL(url);
    if (state.currentAudio === audio) state.currentAudio = null;
  };
  audio.onerror = () => {
    URL.revokeObjectURL(url);
    if (state.currentAudio === audio) state.currentAudio = null;
  };
  await audio.play();
}

function canUseVoiceInput() {
  const config = readProviderConfig();
  return Boolean(
    config.asr.provider !== "disabled" &&
      (navigator.mediaDevices || window.SpeechRecognition || window.webkitSpeechRecognition)
  );
}

function browserRecognitionErrorMessage(event) {
  const code = event?.error || "";
  if (code === "not-allowed") return "麦克风权限被拒绝";
  if (code === "no-speech") return "没有检测到语音";
  if (code === "audio-capture") return "没有可用麦克风";
  if (code === "network") return "浏览器语音服务网络不可用";
  return code || "未知错误";
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
    ${renderStudyGuides(report.study_guides || [])}
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

function renderStudyGuides(guides) {
  if (!guides.length) return "";
  return `
    <h3>题目学习卡</h3>
    <div class="study-guides">
      ${guides.map((guide) => `
        <article class="study-guide">
          <div class="turn-review-title">
            <strong>${escapeHtml(guide.topic || "interview")}</strong>
            <span>${escapeHtml(guide.focus || "")}</span>
          </div>
          <p class="guide-question">${escapeHtml(shortText(guide.question || "", 180))}</p>
          ${renderGuideTags("关联知识点", guide.related_knowledge)}
          <div class="guide-block">
            <b>参考答案</b>
            <p>${escapeHtml(guide.reference_answer || "")}</p>
          </div>
          ${renderGuideList("常见错误", guide.common_mistakes)}
          ${renderGuideList("面试官追问点", guide.interviewer_followups)}
          <div class="answer-compare">
            <div>
              <b>低分回答</b>
              <p>${escapeHtml(guide.low_score_answer || "")}</p>
            </div>
            <div>
              <b>高分回答</b>
              <p>${escapeHtml(guide.high_score_answer || "")}</p>
            </div>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderGuideTags(title, items = []) {
  if (!Array.isArray(items) || !items.length) return "";
  return `
    <div class="guide-block">
      <b>${escapeHtml(title)}</b>
      <div class="tags">${items.map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}</div>
    </div>
  `;
}

function renderGuideList(title, items = []) {
  if (!Array.isArray(items) || !items.length) return "";
  return `
    <div class="guide-block">
      <b>${escapeHtml(title)}</b>
      <ul class="compact-list">
        ${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
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
        const hits = turn.rubric_hits || [];
        const title = meta.topic || meta.id || `第 ${index + 1} 题`;
        return `
          <div class="turn-review-item">
            <div class="turn-review-title">
              <strong>${escapeHtml(title)}</strong>
              <span>${escapeHtml(String(turn.score || 0))} 分</span>
            </div>
            <p>${escapeHtml(shortText(turn.question, 120))}</p>
            ${hits.length ? `<div class="tags">${hits.slice(0, 3).map((hit) => `<span class="tag hit-tag">${escapeHtml(hit)}</span>`).join("")}</div>` : ""}
            ${gaps.length ? `<div class="tags">${gaps.slice(0, 3).map((gap) => `<span class="tag">${escapeHtml(gap)}</span>`).join("")}</div>` : ""}
            ${renderGuideList("评分证据", turn.score_evidence)}
            ${renderGuideList("重答建议", turn.rewrite_advice)}
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

function renderResumeProjectCards(cards = []) {
  if (!Array.isArray(cards) || !cards.length) return "";
  return `
    <div class="resume-cards">
      ${cards.map((card) => `
        <article class="resume-card">
          <b>${escapeHtml(card.name || "项目卡片")}</b>
          <p>${escapeHtml(card.summary || "")}</p>
          ${renderGuideTags("技术栈", card.tech_stack)}
          ${renderGuideList("个人贡献信号", card.contribution_signals)}
          ${renderGuideList("指标信号", card.metrics)}
          ${renderGuideList("易被质疑表述", card.vague_claims)}
          ${renderGuideList("项目拷打问题", card.followup_questions)}
        </article>
      `).join("")}
    </div>
  `;
}

function renderResumeQuestionList(title, items = []) {
  if (!Array.isArray(items) || !items.length) return "";
  return renderGuideList(title, items);
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

async function patchJson(url, body) {
  const response = await authedFetch(url, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify(body)
  });
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

function statusLabel(status) {
  return ({
    todo: "待复习",
    practicing: "复练中",
    mastered: "已掌握",
    ignored: "已忽略"
  })[status] || status || "待复习";
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
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
