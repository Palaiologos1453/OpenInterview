# OpenInterview Architecture

OpenInterview 采用可插拔的面试编排架构，核心目标是让校招面试逻辑独立于具体模型供应商。

## 运行链路

```text
Web client
  -> ASR adapter
  -> Interview orchestrator
  -> LLM adapter
  -> Evaluator / rubric
  -> TTS adapter
  -> Web client
```

MVP 中 ASR、LLM、TTS 均可使用 mock 或浏览器能力。个人本地真实使用时，建议先接入 LLM provider，ASR/TTS 保持浏览器默认或按需接入本地语音 runtime。

## 后端边界

- `catalog.py`：方向、难度、模式、评分维度。
- `interview_engine.py`：校招面试状态机、问题选择、基础评分和报告。
- `adapters/llm.py`：LLM provider 接口。
- `adapters/asr.py`：语音转文字 provider 接口。
- `adapters/tts.py`：文字转语音 provider 接口。
- `main.py`：FastAPI HTTP API。

## 为什么保留 mock 引擎

mock 引擎不是最终智能体，但它有三个作用：

- 离线可演示，贡献者不需要 API key。
- 单元测试可预测，不受模型随机性影响。
- 作为 LLM 输出的行为基线，防止面试流程失控。

## 后续本地可用性模块

- 简历解析：已支持文本抽取，后续补 PDF/DOCX。
- 题库系统：已支持 YAML 题库，后续补管理界面。
- 评分解释：已生成维度分和建议，后续补回答证据引用。
- 数据存储：已支持 SQLite 面试记录、turn、trace、报告和转写记录。
- 权限和隐私：已支持本地用户 token 创建和面试删除，后续补完整登录。

## Runtime Notes

本地 VAD 直接使用 `onnxruntime` 和已下载的 Silero ONNX。SenseVoice ASR 和 CosyVoice TTS 属于重型语音 runtime，建议使用 Python 3.10 独立环境安装 `apps/api/requirements-voice.txt` 和官方 CosyVoice 代码。

## Non-Goals For Now

按当前需求，OpenInterview 暂不实现部署形态：不新增 Dockerfile、docker-compose、GPU 容器脚本或公网部署模板。后续如果要发布托管版，再单独设计部署和密钥管理。

## Production Mode

本地正式模式由环境变量控制：

- `OPENINTERVIEW_ENV=production`
- `OPENINTERVIEW_REQUIRE_AUTH=true`
- `OPENINTERVIEW_CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173`

大模型面试官配置默认留空，前端必须由用户手动填写 API URL、模型名和 API Key。只有显式选择 `mock` 时才使用开发回退逻辑。
