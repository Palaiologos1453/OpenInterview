# OpenInterview

OpenInterview 是一个面向 Java 后端和 AI 应用开发校招/实习准备的本地 AI 模拟面试工具。

项目定位很明确：每个人把项目拉到自己的电脑上，启动本地 API 和静态前端，填写自己的模型 URL、模型名和 API Key，然后开始练习。它默认不是公网 SaaS，不要求上传简历、语音或 API Key 到第三方服务端。

新用户可以先看 [Quickstart](docs/quickstart.md)。

当前公开入口先开放 Java 后端和 AI 应用开发。前端、测开、数据、算法、SRE、嵌入式等方向没有在目录里开放，避免题库深度不足时给用户错误预期；后续等题库质量跟上再恢复多方向入口。

## 一键启动

Windows PowerShell：

```powershell
cd OpenInterview
.\scripts\start-local.ps1
```

脚本会自动做这些事：

- 找可用的本地端口，避免 `8000` 或 `5173` 被占用。
- 检查 Python 版本、pip、端口和启动健康状态。
- 创建/复用 `apps/api/.venv`。
- 安装 API 依赖。
- 启动 FastAPI 后端和静态前端。
- 打印最终访问地址，例如：

```text
http://127.0.0.1:5173/?api=http://127.0.0.1:8000
```

如果项目根目录存在 `voice_venv`，脚本会自动用它启动 API，以便本地 SenseVoice/CosyVoice 可用。如果你只想使用轻量文本环境，可以加：

```powershell
.\scripts\start-local.ps1 -NoVoicePython
```

启动失败时脚本会打印常见修复建议和日志路径。大多数问题集中在 Python 未安装、版本低于 3.10、PowerShell 执行策略、依赖安装失败或端口被占用。

## 首次使用

1. 打开脚本打印的前端地址。
2. 在左侧“模型配置（本机保存）”里填写 LLM：
   - Provider 模板：可选 OpenAI、DeepSeek、阿里云百炼 DashScope、SiliconFlow、Moonshot/Kimi、Ollama
   - Provider：`openai_compatible`
   - API Base：例如 `https://api.openai.com/v1`，或其他兼容 `/v1/chat/completions` 的地址
   - Model：你的模型名
   - API Key：你的 key
3. 点击“测试 LLM”，确认模型能返回。
4. 选择方向、难度、模式和面试官风格，开始面试。

LLM 测试失败时会显示错误类型和修复建议，例如 Key 错、模型不存在、Base URL 不匹配、额度不足、超时或返回格式不兼容。

ASR/TTS 默认走浏览器能力，文本面试不依赖本地语音。建议第一次先只跑文本。需要语音时，可在配置区点击“测试 ASR”“测试 TTS”或“语音自检”确认浏览器/本地语音环境。完整模型配置教程见 [Voice Setup](docs/voice-setup.md)。

## 面试模式

- `综合评估`：自我介绍、项目、八股基础、场景/系统设计、反问。
- `单纯八股`：集中刷计算机基础和方向知识点，适合配合 JavaGuide 查漏补缺。
- `简历拷打`：自动拆项目卡片，围绕个人贡献、虚假/模糊表述、指标来源、技术选型、故障风险和复盘连续追问。
- `系统设计专项`：训练需求澄清、模块拆分、容量估算、架构取舍和验证方案。

## 面试官风格

- `中小厂基础型`：按真实一面节奏平衡基础、项目和工程常识。
- `八股连环追问型`：围绕当前方向高频知识点连续追问原理、边界和误区。
- `项目真实性拷打型`：验证简历项目是否真做过，重点追个人贡献、指标来源、选型依据和故障复盘。
- `系统设计型`：把场景题推向需求澄清、容量估算、模块拆分、可用性和风险兜底。

模式决定面试流程，风格决定追问口径。比如可以用 `单纯八股 + 八股连环追问型` 查漏补缺，也可以用 `简历拷打 + 项目真实性拷打型` 专门压测项目真实性。

报告会生成复练题、推荐回答结构、示例答案和题目学习卡。学习卡包含参考答案、常见错误、面试官追问点、低分回答 vs 高分回答、关联知识点。逐题复盘还会展示命中评分点、缺失评分点、评分证据和重答建议，方便把一次模拟沉淀成后续复习清单。

## 简历导入

支持直接粘贴文本，也支持本地导入：

- `.txt`
- `.md`
- `.docx`
- `.pdf`

文件只会发送到本机 API 做文本提取，不会上传公网服务。扫描版图片 PDF 可能无法提取文字，建议先复制成文本。

## 历史和报告

面试历史保存在本机 SQLite：

```text
data/openinterview.sqlite
```

前端“历史”入口支持：

- 打开历史报告。
- 只看复练题。
- 导出单次 Markdown 报告。
- 将低分题和缺口加入错题本。
- 导出历史为 JSON。
- 清空全部面试历史。

清空历史只删除面试记录、报告、转写和 trace，不会清空浏览器里的模型配置。

## 错题本和题库覆盖

前端顶部提供：

- `错题本`：集中查看待复习题、重答建议和缺失评分点，可标记待复习、复练中、已掌握。
- `题库覆盖`：按当前方向主题统计题量、追问覆盖和评分点覆盖，用来判断下一步该补哪些题。

历史记录里的“入错题本”会从报告中提取低分题、缺失评分点和重答建议，适合做长期复练。

## 数据和隐私

- 模型配置保存在当前浏览器 `localStorage`。
- 后端历史保存在本机 SQLite。
- API 默认绑定 `127.0.0.1`。
- 不建议把前端或 API 暴露到公网。
- 历史记录里的 API Key 会脱敏保存，重启后打开旧报告会优先使用缓存报告。

## 手动启动

后端：

```powershell
cd OpenInterview\apps\api
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m uvicorn openinterview_api.main:app --host 127.0.0.1 --port 8000
```

前端：

```powershell
cd OpenInterview\apps\web
python -m http.server 5173 --bind 127.0.0.1
```

访问：

```text
http://127.0.0.1:5173/?api=http://127.0.0.1:8000
```

## Provider

| 能力 | Provider | 默认 | 说明 |
|---|---|---:|---|
| LLM | `openai_compatible` | 是 | 调用 `/v1/chat/completions` |
| LLM | `ollama` | 否 | 调用本地 Ollama `/api/chat` |
| LLM | `mock` | 否 | 离线开发和测试用 |
| ASR | `browser` | 是 | 浏览器内置语音识别 |
| ASR | `openai_compatible` | 否 | 调用 `/v1/audio/transcriptions` |
| ASR | `sensevoice` | 否 | 本地 SenseVoice，可选重型 runtime |
| TTS | `browser` | 是 | 浏览器内置语音合成 |
| TTS | `openai_compatible` | 否 | 调用 `/v1/audio/speech` |
| TTS | `cosyvoice` | 否 | 本地 CosyVoice，可选重型 runtime |

## 本地语音增强

本地语音不是核心路径。只有当你希望离线 ASR/TTS 时，才需要下载和配置模型。

当前适配的本地模型路径：

- `models/vad/silero-vad/silero_vad.onnx`
- `models/asr/SenseVoiceSmall`
- `models/tts/Fun-CosyVoice3-0.5B`

使用 `/v1/readiness` 检查 ffmpeg、模型文件、FunASR、CosyVoice 和 CUDA 状态。使用 `/v1/readiness/smoke?include_voice=true` 可以做语音冒烟测试。

一键准备语音环境：

```powershell
.\scripts\setup-voice.ps1
```

如需同时下载推荐 ASR/TTS 模型：

```powershell
.\scripts\setup-voice.ps1 -DownloadModels
```

模型路径可以通过 `configs/voice-models.local.yaml` 或环境变量覆盖；音色可以通过 `configs/voice-profiles.local.yaml` 自定义。详细步骤见 [Voice Setup](docs/voice-setup.md)。

## API 摘要

- `GET /health`
- `GET /v1/catalog`
- `GET /v1/readiness`
- `POST /v1/providers/llm/test`
- `GET /v1/questions`
- `POST /v1/resume/analyze`
- `POST /v1/resume/extract`
- `GET /v1/questions/coverage`
- `GET /v1/interviews/{session_id}/report.md`
- `POST /v1/interviews/{session_id}/review-items`
- `GET /v1/review-items`
- `PATCH /v1/review-items/{item_id}`
- `POST /v1/interviews`
- `POST /v1/interviews/{session_id}/turn`
- `GET /v1/interviews/{session_id}/report`
- `GET /v1/interviews`
- `GET /v1/interviews/export`
- `DELETE /v1/interviews`
- `DELETE /v1/interviews/{session_id}`
- `GET /v1/metrics`
- `POST /v1/realtime/sessions`
- `POST /v1/realtime/sessions/{session_id}/events`
- `POST /v1/vad/detect`
- `POST /v1/asr/transcribe`
- `POST /v1/tts/speech`

## 升级和迁移

SQLite 会在 API 启动时自动做轻量迁移。当前迁移策略只做向后兼容字段补齐，例如给旧 `turns` 表补 `question_meta_json`。

升级前可以在前端导出历史 JSON。遇到无法恢复的本地测试数据，也可以在前端清空历史后重新开始。

## 开发验证

```powershell
cd OpenInterview
$env:PYTHONPATH="D:\OpenInterview\apps\api"
python -m unittest apps.api.tests.test_engine apps.api.tests.test_api
node --check apps/web/app.js
.\voice_venv\Scripts\python.exe -m ruff check apps\api\openinterview_api apps\api\tests
```

## 项目结构

```text
OpenInterview/
  apps/
    api/                 FastAPI 后端、面试编排器、模型适配器
    web/                 零构建静态前端
  configs/               provider 和语音配置样例
  data/                  本地 SQLite 数据
  docs/                  架构、路线图、模型接入说明
  scripts/               本地启动和工具脚本
```

## License

MIT
