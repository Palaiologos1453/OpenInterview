# Voice Setup

OpenInterview 的语音能力是可选增强。文本面试只需要 LLM；语音输入和播报可以按自己的机器条件选择。

## 推荐路线

| 路线 | 适合谁 | 配置 |
|---|---|---|
| 浏览器语音 | 第一次使用、只想快速跑通 | ASR=`browser`，TTS=`browser` |
| 本地离线语音 | 想离线 ASR/TTS，机器有独显或能接受较慢 CPU 推理 | ASR=`sensevoice`，TTS=`cosyvoice` |
| 云端语音 API | 不想下载大模型，但能接受服务商计费 | ASR/TTS=`openai_compatible` |

第一次使用建议保持浏览器语音或直接文本面试。确认主流程可用后，再配置本地离线语音。

## 页面向导配置

展开左侧“模型配置（本机保存）”，在“语音配置向导”里选一种模式：

- `浏览器语音`：不需要填写模型路径或 API Key，点击 `测试 ASR` / `测试 TTS` 即可。
- `云端 API`：填写 ASR/TTS 的 API Base、Model、API Key 和 TTS Voice。Key 只保存在当前浏览器 localStorage，不写入后端配置文件。
- `本地模型`：填写 VAD ONNX、SenseVoice 模型目录、CosyVoice 模型目录、CosyVoice runtime 路径，点击 `保存本地语音路径`，再点 `语音自检`。
- `关闭语音`：只使用文本面试。

本地模型路径会写入 `configs/voice-models.local.yaml`，该文件默认被 git 忽略。日常使用不需要手动编辑 YAML 或设置环境变量。

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

如果 CosyVoice 不在这个位置，优先在页面向导里填写 `CosyVoice runtime 路径`。

### 3. 自定义模型路径

推荐直接在页面向导填写并保存。需要手动维护配置时，也可以复制本地配置模板：

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
    runtime_path: E:/AI/CosyVoice
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

1. 语音模式选 `本地模型`
2. 填写 VAD、SenseVoice、CosyVoice 模型和 runtime 路径
3. 点击 `保存本地语音路径`
4. 点击 `测试 ASR`
5. 点击 `测试 TTS`
6. 点击 `语音自检`

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

- 语音模式：`云端 API`
- ASR API Base：兼容 `/v1/audio/transcriptions`
- ASR Model：例如 `gpt-4o-mini-transcribe`
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

安装 CosyVoice runtime，在页面向导的 `CosyVoice runtime 路径` 填写实际目录，例如 `D:\CosyVoice`，保存后重新 `语音自检`。高级用法也可以设置 `OPENINTERVIEW_COSYVOICE_PATH`。

### `ffmpeg is required`

把 ffmpeg 放到 `tools/ffmpeg/.../bin/ffmpeg.exe`，或加入系统 `PATH`。

### GitHub CI 不下载本地大模型

这是预期行为。CI 只验证接口和轻量兜底逻辑；真实本地语音通过 `voice_venv`、模型目录和前端“语音自检”验证。
