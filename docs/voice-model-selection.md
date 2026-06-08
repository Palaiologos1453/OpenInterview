# Voice Model Selection

OpenInterview 的语音链路按系统工程优先级选择模型：中文校招准确率、英文技术词稳定性、实时延迟、可本地部署、开源可维护性、API 可替换。

## 推荐默认组合

| 模块 | 默认选择 | 作用 |
|---|---|---|
| VAD | Silero VAD | 端点检测、打断、降噪前置、减少无效 ASR 调用 |
| ASR | FunAudioLLM/SenseVoiceSmall | 中文校招主力 ASR，兼顾英文技术词 |
| ASR fallback | Systran/faster-whisper-large-v3 | 成熟 Whisper 生态兜底，适合长音频、时间戳和集成 |
| TTS | FunAudioLLM/Fun-CosyVoice3-0.5B-2512 | 面试官主声音，偏自然、可流式、支持中英 |
| TTS fallback | FunAudioLLM/CosyVoice2-0.5B | CosyVoice3 运行不稳定时的兼容后备 |
| TTS lightweight | onnx-community/Kokoro-82M-v1.0-ONNX | 低资源演示，不作为中文主声音 |

## 为什么 ASR 默认不是 Whisper

Whisper 生态成熟，但 OpenInterview 的主要用户是中文计算机校招候选人，回答里会混杂中文、英文缩写和技术词。SenseVoiceSmall 在中文/Cantonese 场景、低延迟和多任务标注上更适合作为默认 ASR。Whisper large-v3 仍保留为兜底，因为它的工具链、时间戳、批处理和社区集成更成熟。

## 为什么 TTS 默认不是 Piper

Piper 非常轻，适合离线设备和低成本 Demo，但校招模拟面试需要“像真实面试官”的语音质感、中文韵律和英文技术词可控性。默认 TTS 选 CosyVoice3，Piper/Kokoro 只作为轻量模式或低资源 fallback。

## 下载命令

```powershell
cd OpenInterview
python -m pip install huggingface_hub

huggingface-cli download FunAudioLLM/SenseVoiceSmall --local-dir models/asr/SenseVoiceSmall
huggingface-cli download Systran/faster-whisper-large-v3 --local-dir models/asr/faster-whisper-large-v3
huggingface-cli download FunAudioLLM/Fun-CosyVoice3-0.5B-2512 --local-dir models/tts/Fun-CosyVoice3-0.5B
huggingface-cli download FunAudioLLM/CosyVoice-ttsfrd --local-dir models/tts/CosyVoice-ttsfrd
huggingface-cli download FunAudioLLM/CosyVoice2-0.5B --local-dir models/tts/CosyVoice2-0.5B
huggingface-cli download onnx-community/Kokoro-82M-v1.0-ONNX --local-dir models/tts/Kokoro-82M-v1.0-ONNX
```

Silero VAD 当前默认读取本地 ONNX 文件：

```text
models/vad/silero-vad/silero_vad.onnx
```

如果没有该文件，后端会使用轻量能量检测兜底，适合 CI 和基础接口测试；真实实时语音建议配置 Silero ONNX。

## API fallback

本地模型之外，保留 OpenAI-compatible API 作为开发期 fallback：

- ASR：`gpt-4o-mini-transcribe`，高精度可切 `gpt-4o-transcribe`。
- TTS：`gpt-4o-mini-tts`。

公网部署时不要在前端长期保存 API key，应改为服务端密钥或用户级加密配置。

## 实时链路配置

默认端到端策略：

```text
microphone -> noise gate -> Silero VAD -> SenseVoiceSmall -> LLM -> CosyVoice3 -> streaming playback
```

关键参数建议：

- VAD 帧长：20-30 ms。
- 端点静音阈值：500-800 ms 起步。
- ASR 分段：单段 8-15 秒，长回答用增量合并。
- TTS：按句子或短分句流式合成，播放队列必须可取消。
- 打断：新的人声触发时取消当前 TTS、清空播放队列、保留 trace。

## 当前实现状态

- `SileroVAD`：已接入 `/v1/vad/detect`，MVP 输入要求 16kHz mono 16-bit WAV。
- `SenseVoiceASR`：已接入 provider `sensevoice`，运行时懒加载 `funasr`。
- `CosyVoiceTTS`：已接入 provider `cosyvoice`，通过子进程调用 CosyVoice runtime。
- Voice profiles：已支持 `configs/voice-profiles.example.yaml`。
- 浏览器前端：已支持本地/云端 ASR、TTS provider 和音色 profile 选择。

本机当前 Python 3.14 可运行核心 API 和 VAD 测试；ASR/TTS 建议单独使用 Python 3.10 voice runtime。

本地路径覆盖优先级：

1. 环境变量：`OPENINTERVIEW_VAD_MODEL`、`OPENINTERVIEW_ASR_MODEL_DIR`、`OPENINTERVIEW_TTS_MODEL_DIR`
2. `configs/voice-models.local.yaml`
3. 默认 `models/` 路径

详细配置教程见 [Voice Setup](voice-setup.md)。
