# LiveKit 本地实时面试

更新：现在可选择[云端语义追问 + 本地语音](cloud-semantic-interview.md)。该模式的简历和最终回答会发送给用户配置的云端模型。
下文“无需云端、全部本地”的描述仅适用于“离线规则练习”；语音模型与 LiveKit 传输仍在本机。

本实现使用 **LiveKit Server 1.13.7 / Agents 1.8.3 / 浏览器 SDK 2.22.3**。
Server、Agent、SenseVoice、CosyVoice、题库和 SQLite 均在本机。
前端 SDK 已随项目保存，不使用 CDN。无需 LiveKit Cloud、云端推理账户或 API Key。
依赖安装和首次下载 Server 需要联网，下载完成后不依赖云端语音服务。

## 启动

先按 [Voice Setup](voice-setup.md) 准备 `voice_venv`、SenseVoiceSmall、CosyVoice3 及其 runtime。
当前安装脚本针对 Windows x64：

```powershell
.\scripts\setup-livekit.ps1
.\scripts\start-livekit.ps1
```

打开 **http://127.0.0.1:5180**，选择方向和模式，点击“开始本地面试”。
麦克风权限通过后会预热本地 ASR/TTS。直接回答，停顿后自动提交；面试官说话期间仍可插话。
“暂停麦克风”适合长时间思考。结束通话后可查看报告，历史仍保存在原本的本地 SQLite。

停止：

```powershell
.\scripts\stop-livekit.ps1
```

启动脚本使用隐藏后台进程，并记录 PID 与启动时间；停止脚本只结束这次启动的进程树。
日志在 `logs/livekit/`。端口冲突会明确失败；已有程序不会被自动结束。
API 默认用 `8010`，避免占用原项目的 `8000`，页面用 `5180`，可通过 `-ApiPort` / `-WebPort` 修改。
媒体 Server 的信令端口 `7880`、TCP `7881`、UDP `7882`。

## 环境隔离与本地数据

- Agent 与小型页面服务使用 **`apps/livekit/.venv`**。
- ASR/TTS/API 使用 **`voice_venv`**。不要将 `requirements-livekit.txt` 安装到这个环境：
  LiveKit 与旧 Gradio / grpcio-tools 的 protobuf、aiofiles 约束冲突。
- Server 二进制放在 `tools/livekit/1.13.7/`，安装时检查固定 SHA-256。
- 随机生成的本机凭据在 `configs/livekit.local.json` / `.yaml`，均已被 Git 忽略。
  浏览器只获得限定房间、有效期两小时的参与者 token，不会获得 Server 密钥。
- Agent 只允许 HTTP/WS loopback 服务地址；后端连接强制本地 SenseVoice / CosyVoice。
- Agent 禁用 OTEL SDK，不启用云端降噪、在线推理、远程 MCP 或原始音频录制。
- 信令和 HTTP 页面绑定 `127.0.0.1`；Windows WebRTC 媒体 socket 会使用本机网卡。
  没有配置公网 STUN/TURN 或云中转。将媒体强制绑定唯一 loopback 接口在本机 SDK 上导致 ICE 失败，
  因此保留经过实测可用的默认媒体接口选择。此配置用于本机，不是公网部署配置。

## 实现边界

链路：浏览器 WebRTC → 本机 LiveKit → Silero VAD → 本机 API / SenseVoice →
现有 `CampusInterviewEngine` → 本机 API / CosyVoice PCM → WebRTC 播放。

这是本地 **级联语音工作流**，没有新增本地 LLM。提问和评分继续由已有规则引擎驱动。
不应将其描述为已经具有 GPT Voice 的语义理解或原生语音模型能力。

SenseVoice 本身仍是批量识别模型，**不是逐 token 流式 ASR**。现在在前 20 秒回答中每约 1.2 秒
对累计语音做一次限频快照识别，实时展示可修正转录；结束时仍以完整语段重新识别为准。
最多一个快照请求在途，慢请求期间跳过新的快照，不累积 GPU 任务。
两次快照预测到相同追问时，可预备一份音频；最终提交后题目和轮次完全匹配才播放。
完整设计、开关与对照结果见 [本地语音流水线](voice-pipeline.md)。
VAD 停顿阈值约 0.8 秒，仍可能把思考停顿当成回答结束。首版只允许一个活动面试。
插话使用本地 VAD；扬声器回声、误打断、技术词识别和长时间对话还需要真实人声评测。
浏览器请求回声消除/降噪，但具体效果取决于设备，推荐耳机。
关闭了 SDK 的 AEC 启动丢弃窗口，避免立即插话时回答开头被替换成静音。

TTS 适配器收到 PCM 就输出 20ms 帧。语音先只读主问题，附加的“追问方向”留在屏幕，避免一次
读多个追问让旧合成持续占用 GPU。主问题只发送一次，避免每个句子重复触发模型处理。
打断后立即停止播放，后台排空旧合成结果以保留模型；新的合成可能等待旧请求完成。
这不是模型计算层的即时抢占。语音 worker 出错或超时仍会重新加载。

## 验证

轻量回归：

```powershell
.\apps\livekit\.venv\Scripts\python.exe -m unittest discover -s apps/livekit/tests -v
```

覆盖：仅允许本机 URL、强制本地 ASR、PCM 先于合成结束输出、流截断错误、稳定的回答请求 ID。
原 API 和前端的 TTS 回归也继续运行。

真实端到端验证使用单独数据库，避免污染个人历史：

```powershell
.\scripts\start-livekit.ps1 -DatabasePath "$PWD\logs\livekit-test.sqlite"
.\apps\livekit\.venv\Scripts\python.exe scripts/smoke_livekit.py
.\scripts\stop-livekit.ps1
```

脚本用本地 TTS 生成候选人音频，作为真实 WebRTC track 发布，确认 Agent 收音、识别、
写入一条面试回答、返回题目事件，并再次收到非静音音频。结果写入 `logs/livekit/smoke-result.json`。
测试录音属于合成语音冒烟，不等价于真人口音、噪声、长停顿或误打断测试。

本轮另用本机 Edge 无头浏览器验证了页面连接、麦克风发布、远端音频开始播放和断开流程，
无 JavaScript 错误，浏览器 HTTP 请求均为 loopback。这不证明实际扬声器音质。

延迟应区分预热、房间连接、结束说话到下一题文本、结束说话到实际出声。
本地 TTS 仍需秒级首块生成；安装 LiveKit 本身不保证亚秒级回应。

2026-10-03 的一次预热后合成语音冒烟：加入房间至首次收到面试官音频 5.40 秒；
候选人播完至下一题文本事件 2.00 秒，至下一题非静音音频 **5.45 秒**。
这里测量的是接收客户端拿到音频，不是物理扬声器出声；没有足够样本报告 P95。
完整回答开头已保留，但 Redis/MySQL 被识别为 `radis/myCql`，技术词识别仍需改进。
原始记录：[livekit-2026-10-03.json](benchmarks/livekit-2026-10-03.json)。
这组整轮指标与 [此前 TTS 单独首包测试](tts-latency.md) 的起止点不同，不能直接比较快慢。

## 后续优化

优先补真实录音与插话测试集，测 P50/P95 的实际出声延迟、误端点率、完整转录率和断音率。
再评估本地流式 ASR、中文语义端点与本地对话模型；对单卡上的模型并发和显存竞争做单独评测。
官方接口参考：[LiveKit Agents](https://github.com/livekit/agents)、
[自托管 Server](https://github.com/livekit/livekit)。实现与适配测试以锁定版本为准。
