# Quickstart

OpenInterview 默认是本地个人工具。当前公开入口开放 Java 后端和 AI 应用开发方向；第一次使用建议只跑文本面试，语音作为后续增强。

## 1. 准备环境

- Windows PowerShell
- Python 3.10+
- Node.js 仅用于开发检查；运行静态前端不强依赖 Node

## 2. 一键启动

在项目根目录运行：

```powershell
.\scripts\start-local.ps1
```

脚本会自动：

- 选择空闲本地端口
- 检查 Python 3.10+、pip、端口和服务健康状态
- 创建 `apps/api/.venv`
- 安装 API 依赖
- 启动 API 和 Web
- 打印最终访问地址

打开脚本输出的 URL，例如：

```text
http://127.0.0.1:5173/?api=http://127.0.0.1:8000
```

## 3. 配置 LLM

左侧展开“模型配置（本机保存）”，填写：

- Provider 模板：先选你使用的服务商，例如 DeepSeek、DashScope、SiliconFlow、Moonshot/Kimi、OpenAI 或 Ollama
- Provider：`openai_compatible`
- API Base：兼容 OpenAI `/v1/chat/completions` 的地址
- Model：模型名
- API Key：你的 key

点击“测试 LLM”。成功后再开始面试。

测试失败时看状态栏里的“建议”。常见原因是 Key 错、模型名不存在、Base URL 少了 `/v1` 或兼容模式路径、账号额度不足、网络超时。

## 4. 开始练习

推荐顺序：

1. `单纯八股`：先查漏补缺。
2. `简历拷打`：粘贴项目经历后练追问。
3. `综合评估`：模拟完整中小厂技术面。

可以再按训练目标选择面试官风格：

- `中小厂基础型`：适合第一次跑通完整流程。
- `八股连环追问型`：适合刷 JavaGuide 后检查当前方向的原理、边界和误区。
- `项目真实性拷打型`：适合压测简历项目、指标来源和个人贡献。
- `系统设计型`：适合练场景题、容量估算、架构取舍和风险兜底。

报告里会给出逐题复盘、复练题、推荐回答结构、示例答案和题目学习卡。学习卡包含参考答案、常见错误、面试官追问点、低分回答 vs 高分回答、关联知识点。

`简历拷打` 会先拆项目卡片，再追问个人贡献、模糊表述、指标来源、技术选型依据、故障和复盘。你可以直接粘贴文本，也可以导入 `.txt`、`.md`、`.docx`、`.pdf` 简历文件。文件只在本机 API 做文本提取，不上传公网。

顶部的 `题库覆盖` 可以查看当前方向各主题题量和追问/评分点覆盖。`错题本` 用来集中复练报告里的低分题和缺失点。

## 5. 管理历史

点击“历史”：

- “报告”：打开某次完整报告。
- “复练题”：只看练习项和示例答案。
- “导出 MD”：下载单次 Markdown 报告。
- “入错题本”：把低分题和缺失评分点加入错题本。
- “导出历史”：下载 JSON。
- “清空历史”：删除本机面试历史，不影响模型配置。

## 常见问题

### 端口被占用

`start-local.ps1` 会自动换端口。使用脚本打印的 URL 即可。

### LLM 测试失败

检查三项：

- API Base 是否包含正确的 `/v1` 前缀或兼容路径。
- Model 是否是服务商实际支持的模型名。
- API Key 是否有效。

### 本地语音启动失败

先把“语音配置向导”切到 `浏览器语音` 或 `关闭语音`，完成文本面试。配置区的“测试 ASR”“测试 TTS”和“语音自检”可以快速判断浏览器、本地 SenseVoice/CosyVoice 是否可用。SenseVoice/CosyVoice 属于重型可选增强，不是首次使用必需项。

准备本地离线语音环境：

```powershell
.\scripts\setup-voice.ps1
```

如果要让脚本同时下载推荐模型：

```powershell
.\scripts\setup-voice.ps1 -DownloadModels
```

下载完成后在页面向导里选择 `本地模型`，填写 VAD、SenseVoice、CosyVoice 模型目录和 CosyVoice runtime 路径，点击“保存本地语音路径”再自检。完整模型路径、自定义音色和 API 语音配置见 [Voice Setup](voice-setup.md)。

### PowerShell 脚本无法运行

在 PowerShell 里执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后重新运行 `.\scripts\start-local.ps1`。
