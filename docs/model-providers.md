# Model Providers

OpenInterview 的模型接入分为 LLM、ASR 和 TTS 三类。它们应保持独立配置，避免供应商锁定。

## LLM

用途：

- 生成面试问题。
- 根据回答生成追问。
- 按 rubric 评分并解释。
- 生成复习计划。

建议 provider：

- API：OpenAI、Qwen、DeepSeek、Claude、Gemini。
- 本地：Ollama、vLLM、llama.cpp。

当前已实现：

- `mock`：离线 deterministic 引擎。
- `openai_compatible`：调用 `{api_base}/chat/completions` 或 `{api_base}/v1/chat/completions`。
- `ollama`：调用 `{api_base}/api/chat`。

正式默认是 `openai_compatible`，但 `api_base`、`model`、`api_key` 全部留空。配置缺失时仍可开始文本面试，面试题和追问来自本地题库与规则引擎。

真实 LLM 只用于可选报告总结。服务商报错、网络超时或返回空内容时，后端会回退到本地总结，不影响正在进行的面试轮次。

## ASR

用途：

- 候选人口语回答转写。
- 技术词热词纠错。
- 后续支持语速、停顿、表达流畅度分析。

建议 provider：

- API：OpenAI、Google、Azure、AWS、Deepgram。
- 本地：faster-whisper、Whisper.cpp、Vosk。

当前已实现：

- `browser`：前端浏览器内置语音识别。
- `openai_compatible`：后端调用 `{api_base}/audio/transcriptions` 或 `{api_base}/v1/audio/transcriptions`。
- `sensevoice`：后端调用本地 `models/asr/SenseVoiceSmall`，需要 Python 3.10 voice runtime。

## TTS

用途：

- 面试官语音播报。
- 后续支持不同面试官风格和语速。

建议 provider：

- API：OpenAI、ElevenLabs、Azure、Google、AWS。
- 本地：Piper、Coqui/XTTS。

当前已实现：

- `browser`：前端浏览器内置语音合成。
- `openai_compatible`：后端调用 `{api_base}/audio/speech` 或 `{api_base}/v1/audio/speech`。
- `cosyvoice`：后端调用本地 `models/tts/Fun-CosyVoice3-0.5B`，需要 Python 3.10 voice runtime 和 CosyVoice 官方代码。

## 前端保存

前端模型配置保存到浏览器 `localStorage` 的 `openinterview_provider_config`。这适合本地开发和个人使用。公网部署时，应禁用浏览器保存 API key，改成服务端密钥管理或用户级加密配置。
