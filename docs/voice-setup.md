# Voice Setup

OpenInterview 的语音能力是可选增强。文本面试只需要 LLM；语音输入和播报可以按自己的机器条件选择。

## 推荐路线

| 路线 | 适合谁 | 配置 |
|---|---|---|
| 浏览器语音 | 第一次使用、只想快速跑通 | ASR=`browser`，TTS=`browser` |
| 本地离线语音 | 想离线 ASR/TTS，机器有独显或能接受较慢 CPU 推理 | ASR=`sensevoice`，TTS=`cosyvoice` |
| 云端语音 API | 不想下载大模型，但能接受服务商计费 | ASR/TTS=`openai_compatible` |

第一次使用建议保持浏览器语音或直接文本面试。确认主流程可用后，再配置本地离线语音。

## 浏览器语音

前端默认配置：

- ASR Provider：`Browser`
- TTS Provider：`Browser`

点击配置区的 `测试 ASR` 和 `测试 TTS`。浏览器 ASR 通常建议使用 Chrome 或 Edge；如果提示麦克风权限被拒绝，在地址栏权限设置里允许麦克风。

## 本地离线语音

本地推荐组合：

- VAD：Silero VAD
- ASR：FunAudioLLM/SenseVoiceSmall
- TTS：FunAudioLLM/Fun-CosyVoice3-0.5B-2512
- TTS runtime：CosyVoice，默认检测 `D:\CosyVoice`

### 1. 准备语音环境

在项目根目录运行：

```powershell
.\scripts\setup-voice.ps1
```

这个脚本会：

- 创建或复用 `voice_venv`
- 安装 API 包和 `apps/api/requirements-voice.txt`
- 安装 `huggingface_hub`
- 检查 `D:\CosyVoice`、ffmpeg、模型路径和 CUDA 状态

如果希望脚本顺便下载 ASR/TTS 模型：

```powershell
.\scripts\setup-voice.ps1 -DownloadModels
```

脚本会从 `silero-vad` 包复制 VAD ONNX，并下载 SenseVoiceSmall 和 CosyVoice3。ASR/TTS 模型较大，下载失败时可以手动下载到下面的默认路径。

### 2. 默认模型路径

```text
models/vad/silero-vad/silero_vad.onnx
models/asr/SenseVoiceSmall/model.pt
models/tts/Fun-CosyVoice3-0.5B/llm.pt
models/tts/Fun-CosyVoice3-0.5B/flow.pt
```

CosyVoice runtime 默认路径：

```text
D:\CosyVoice
```

如果 CosyVoice 不在这个位置，设置环境变量：

```powershell
$env:OPENINTERVIEW_COSYVOICE_PATH = "E:\AI\CosyVoice"
```

### 3. 自定义模型路径

最简单的方式是复制本地配置模板：

```powershell
Copy-Item configs\voice-models.local.example.yaml configs\voice-models.local.yaml
```

然后编辑 `configs/voice-models.local.yaml`：

```yaml
vad:
  default:
    local_file: E:/models/silero-vad/silero_vad.onnx

asr:
  default:
    local_dir: E:/models/SenseVoiceSmall

tts:
  default:
    local_dir: E:/models/Fun-CosyVoice3-0.5B
```

也可以用环境变量覆盖：

```powershell
$env:OPENINTERVIEW_VAD_MODEL = "E:\models\silero-vad\silero_vad.onnx"
$env:OPENINTERVIEW_ASR_MODEL_DIR = "E:\models\SenseVoiceSmall"
$env:OPENINTERVIEW_TTS_MODEL_DIR = "E:\models\Fun-CosyVoice3-0.5B"
$env:OPENINTERVIEW_COSYVOICE_PATH = "E:\AI\CosyVoice"
```

优先级：

1. 环境变量
2. `configs/voice-models.local.yaml`
3. 默认 `models/` 路径

### 4. 自定义音色

复制模板：

```powershell
Copy-Item configs\voice-profiles.local.example.yaml configs\voice-profiles.local.yaml
```

参考音频放到 `voices/`，例如：

```text
voices/custom_interviewer.wav
```

然后编辑 `configs/voice-profiles.local.yaml`：

```yaml
voice_profiles:
  - id: custom_interviewer
    name: 自定义面试官
    persona: 本地克隆音色
    gender: unknown
    style: natural, technical
    provider: cosyvoice
    mode: zero_shot
    reference_audio: voices/custom_interviewer.wav
    reference_text: 你好，我是今天的技术面试官，我们会围绕你的项目和基础知识做一些追问。
```

启动后前端的“面试官音色”下拉框会读取 local 配置。`configs/voice-profiles.local.yaml` 和 `voices/*.wav` 默认不提交到 git。

### 5. 启动和自检

`start-local.ps1` 会自动识别 `voice_venv`：

```powershell
.\scripts\start-local.ps1
```

如果你只想用轻量 API 环境，不加载语音环境：

```powershell
.\scripts\start-local.ps1 -NoVoicePython
```

打开前端后：

1. ASR Provider 选 `Local SenseVoice`
2. TTS Provider 选 `Local CosyVoice`
3. 点击 `测试 ASR`
4. 点击 `测试 TTS`
5. 点击 `语音自检`

后端接口也可以直接检查：

```powershell
$env:PYTHONPATH = "$PWD\apps\api"
.\voice_venv\Scripts\python.exe -c "from openinterview_api.services.readiness import readiness_report; import json; print(json.dumps(readiness_report(), ensure_ascii=False, indent=2))"
```

完整 ASR/TTS smoke：

```powershell
$env:PYTHONPATH = "$PWD\apps\api"
.\voice_venv\Scripts\python.exe -c "from openinterview_api.services.readiness import readiness_smoke_report; import json; print(json.dumps(readiness_smoke_report(include_voice=True), ensure_ascii=False, indent=2))"
```

## 云端语音 API

如果使用 OpenAI-compatible ASR/TTS：

- ASR Provider：`OpenAI Compatible`
- ASR API Base：兼容 `/v1/audio/transcriptions`
- ASR Model：例如 `gpt-4o-mini-transcribe`
- TTS Provider：`OpenAI Compatible`
- TTS API Base：兼容 `/v1/audio/speech`
- TTS Model：例如 `gpt-4o-mini-tts`
- TTS Voice：服务商支持的 voice 名称

填好后点击 `测试 ASR` 和 `测试 TTS`。

## 常见问题

### `funasr is required`

当前 API 进程没有使用 `voice_venv`，或 `voice_venv` 没装语音依赖。运行：

```powershell
.\scripts\setup-voice.ps1
.\scripts\start-local.ps1
```

### `CosyVoice runtime not found`

安装 CosyVoice runtime，并设置：

```powershell
$env:OPENINTERVIEW_COSYVOICE_PATH = "D:\CosyVoice"
```

### `ffmpeg is required`

把 ffmpeg 放到 `tools/ffmpeg/.../bin/ffmpeg.exe`，或加入系统 `PATH`。

### GitHub CI 不下载本地大模型

这是预期行为。CI 只验证接口和轻量兜底逻辑；真实本地语音通过 `voice_venv`、模型目录和前端“语音自检”验证。
