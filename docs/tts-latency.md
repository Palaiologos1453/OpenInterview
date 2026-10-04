# 本地 TTS 延迟优化与实测

2026-09-29，在 Windows / RTX 5080 Laptop GPU 16GB / PyTorch
`2.13.0.dev20260603+cu132` / Fun-CosyVoice3-0.5B-2512 上验证。
CosyVoice runtime 版本为 `074ca6d`，旧 worker 来自本项目 `dcfd82a`。

## 发现的问题与修复

1. **模型流式输出被重新攒成完整文件。** 原 worker 虽然传了 `stream=True`，
   仍然先收齐 tensor、拼接、写 WAV，再通知父进程。现在每个 PCM chunk 都立即通过
   worker JSON 协议送出，HTTP 与 WebSocket 都可以边生成边播放。
2. **普通播报等待完整响应。** 新增 `POST /v1/tts/speech/stream`，返回 NDJSON，
   浏览器使用 `ReadableStream` 逐行读取；本地 CosyVoice 的开场、测试播报、文本回答后的
   播报均走这个入口。云端 provider 保留原有文件接口，尚未优化其首包延迟。
3. **音频尾部被提前切掉。** 服务端发送 `done` 时，浏览器可能还排着数秒 PCM。
   现在以最后一个 `AudioBufferSourceNode.onended` 为播放结束依据；取消时停止所有已排队音源。
4. **取消消息无法及时处理。** WebSocket 原先在接收循环内等待整轮 ASR/TTS。
   现在将轮次放入独立异步任务，接收循环继续处理取消，并丢弃取消后的音频。
5. **重复预处理与首块变大。** 缓存参考音频特征，按路径、文件版本与提示文本区分，最多保存
   8 份；每次请求恢复模型初始化时的 `token_hop_len`，避免上游在上一轮增大的块大小拖慢下一轮。
6. **worker 容易挂起或重复加载。** 持续排空 stderr、隔离 stdout 日志、显式使用 UTF-8、
   校验请求 ID、增加 180 秒启动/请求截止时间、退出时清理子进程。失败的半段音频不会自动重播。
   10 月 3 日进一步优化：流被提前关闭时后台排空当前请求，保留 GPU 模型；后续请求等旧请求
   完成后复用 worker。协议出错或超时才废弃 worker。播放能立即打断，但当前模型推理仍需完成。
7. **本地 WAV 被标为 MP3。** 旧文件接口的 CosyVoice 分支现在固定写 WAV 并返回 `audio/wav`。

已保存本地语音配置时，页面启动后会后台调用 `POST /v1/tts/warmup`；用户切到本地语音模式时
也会触发一次。预热会加载模型并做一次短句推理，不调用付费 provider。
预热把冷启动移到准备阶段，并不消除它；如果立即开始面试，首轮仍可能等待。

## 测量结果

固定文本：`请介绍你负责的项目，说明业务背景、个人贡献、技术方案和验证结果。`
固定 profile：`young_engineer`。每种热启动路径测 3 次。

| 路径 | 首份可播放数据中位数 | 范围 |
| --- | ---: | ---: |
| 旧 worker，等待完整 WAV | 4956 ms | 4760–5448 ms |
| 优化后 worker，首个原生 PCM chunk | 2246 ms | 2208–2308 ms |
| 优化后真实 loopback HTTP，客户端收到首个 PCM chunk | 2312 ms | 2308–2423 ms |

worker 首份数据等待减少约 **55%**。优化后同一 worker 的完整文件路径中位数为 5708 ms，
说明这里改善的是开始播放的时间，**不能声称总推理时间更短**。
优化后流式总生成耗时约 5.54–6.10 秒，音频长度约 5.36–6.08 秒，RTF 约 1.00–1.04；
长句仍有跟不上播放或块间停顿的可能。

旧 worker 模型加载单独耗时 16.94 秒，首轮推理另需 7.98 秒。
优化版本的一次独立加载测得 35.18 秒，说明冷启动波动较大；
真实 HTTP 测试的整次预热耗时为 20.36 秒。热启动首块数据不包含这些时间。

原始记录：[tts-2026-09-29.json](benchmarks/tts-2026-09-29.json)。
这些是单机短文本、少量重复的链路测量，不是 p95 服务指标；
没有测量浏览器扬声器实际出声的物理延迟，也没有做音质盲测。
现在仍约 2.3 秒起播，**尚未达到亚秒级即时语音**。

## 复现与回归

安装正常的本地语音环境后，在项目根目录运行：

```powershell
python scripts/benchmark_tts.py --runs 3 --output logs/tts-benchmark.json
```

脚本启动真实 worker，先记录模型加载与首轮推理，再交替测完整文件、原生流式首块、
总生成时间、音频长度和 RTF；脚本退出会清理其子进程。
`--text` 可替换测试文本。要比较旧版本：

```powershell
git show dcfd82a:apps/api/openinterview_api/voice/cosyvoice_worker.py | Set-Content -Encoding utf8 logs/tts-baseline-worker.py
python scripts/benchmark_tts.py --batch-only --worker-script logs/tts-baseline-worker.py --output logs/tts-baseline.json
```

自动化回归不下载模型：

```powershell
$env:PYTHONPATH = "$PWD\apps\api"
python -m unittest discover -s apps/api/tests
node --test apps/web/tests/*.test.cjs
python -m ruff check apps/api/openinterview_api apps/api/tests scripts/benchmark_tts.py
node --check apps/web/app.js
```

覆盖首块先于后续生成、HTTP 完整性/错误结束、worker 请求复用/超时/日志隔离、
取消后不发音频、断线清理、参考音频缓存失效、浏览器排队播放与尾音保留。
另用真实 Uvicorn + HTTP 客户端 + 本机模型验证了 HTTP 逐块到达，数据库使用临时目录。

## 上游依据与后续瓶颈

- [官方 CosyVoice 推理接口](https://github.com/FunAudioLLM/CosyVoice/blob/main/cosyvoice/cli/cosyvoice.py)：
  `inference_zero_shot` / `inference_instruct2` 逐块 yield，`add_zero_shot_spk` 可缓存参考特征。
- [官方流式模型实现](https://github.com/FunAudioLLM/CosyVoice/blob/main/cosyvoice/cli/model.py)：
  `token_hop_len`、lookahead 和逐块声码器决定模型侧首包与吞吐取舍。
- [官方项目与加速说明](https://github.com/FunAudioLLM/CosyVoice)：
  本地 runtime 的 `CosyVoice3` 提供 TensorRT / vLLM 可选加载参数。本轮未启用或验证这些后端。

要继续压到亚秒级，应在兼容的 CUDA/runtime 环境中分别评测 LLM token 生成和 flow/vocoder 加速，
同时测首块、RTF、音质与长句稳定性。直接把不兼容的 token 块大小调小或只报 HTTP 响应头到达时间，
都不能证明实际体验达到了即时水准。

### CosyVoice vLLM / TensorRT 实验开关

OpenInterview 的 CosyVoice worker 支持通过环境变量开启官方拆分后端：

```powershell
$env:OPENINTERVIEW_COSYVOICE_LOAD_VLLM = "1"
$env:OPENINTERVIEW_COSYVOICE_LOAD_TRT = "1"
```

这两个开关默认关闭。它们要求 `voice_venv` 中安装与当前 CosyVoice 兼容的 vLLM，
并准备好 TensorRT 运行时和对应 engine；缺少 vLLM 时 worker 会明确报告
`ModuleNotFoundError: No module named 'vllm'`，不会静默退回并误报加速成功。
