# Local Usage Checklist

OpenInterview 默认是本地个人工具。这个清单用于确认“拉取到本机后能稳定使用”，不是公网生产部署清单。

## Core Text Interview

启动后端和前端后检查：

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/v1/readiness
```

核心文本面试只要求：

- API 能启动，`/health` 返回 `status = ok`
- `/v1/catalog` 能返回方向、难度和模式
- 前端可以填写 LLM `API Base`、`Model`、`API Key`
- ASR/TTS 保持默认 `browser` 或 `disabled`
- 面试记录能写入本地 `data/openinterview.sqlite`

## Optional Local Voice

本地 SenseVoice/CosyVoice 不是首次使用必需项。只有需要离线语音时再检查：

- `ffmpeg.ok = true`
- `funasr.ok = true`
- `cosyvoice.ok = true`
- `cuda.ok = true`，如果要 GPU 本地语音

模型路径：

- VAD: `models/vad/silero-vad/silero_vad.onnx`
- ASR: `models/asr/SenseVoiceSmall`
- TTS: `models/tts/Fun-CosyVoice3-0.5B`

## Local Security Boundary

- 不要把 API 或前端暴露到公网。
- API Key 保存在本机浏览器 `localStorage`，适合个人本地使用。
- 面试记录保存在本地 SQLite；需要清空时删除 `data/openinterview.sqlite`。
- 当前认证只适合作为本地边界，不是公网多用户认证系统。
