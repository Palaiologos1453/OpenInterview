# Engineering Hardening Notes

这份文档记录 OpenInterview 作为本地优先工具的三条工程化改造线：评分可评测、本地数据可靠、本地环境可诊断。

## Scoring Evaluation

评分评测集位于 `apps/api/eval/scoring_seed.yaml`。文件包含模板 profile 样本和真实场景样本，覆盖 Java 后端项目深挖、AI 应用评测、RAG、Agent 工具风险和本地优先隐私边界。

运行：

```powershell
python .\scripts\evaluate_scoring.py --output apps/api/eval/scoring-report.md --json-output apps/api/eval/scoring-report.json
```

脚本会输出：

- 样本数。
- 规则评分和人工期望分的 MAE。
- 分数误差在阈值内的比例。
- 缺失评分点 precision/recall。
- Top 误判案例，方便继续调评分规则。

当前重点关注关键词堆砌、自信但错误、答非所问、模板废话、指标口径缺失和项目贡献边界不清。详细方法见 [Scoring Evaluation](scoring-evaluation.md)。评测集是可审阅 seed，不声称代表真实用户分布。

## Local Reliability

API 层不再直接使用裸 `dict` 管理面试会话，而是通过 `SQLiteBackedSessionStore` 访问会话。当前实现保留进程内热缓存，但会在缓存 miss 时从 SQLite 恢复历史 turn，并重新计算下一题。这个设计服务于本地可靠性：API 重启、前端刷新或临时中断后，用户历史回答不丢。

`TurnRequest` 支持可选 `request_id`。客户端重试同一个 turn 时，服务端会根据 `(interview_id, request_id)` 返回首次保存的 payload，避免重复推进面试状态。

本地可靠性覆盖：

- SQLite schema 轻量迁移。
- 重复提交幂等。
- 进程内会话缓存 miss 后从本地 SQLite 恢复。
- 历史 JSON 导出/导入用于本地备份。
- realtime session store 使用线程安全内存实现，符合单机本地使用边界。

## Local Diagnostics

`Trace.span` 会自动把耗时写入 runtime metrics。JSON 指标和 Prometheus 风格文本分别由下面接口暴露，用于本地排障和性能观察：

```text
GET /v1/metrics
GET /v1/metrics/prometheus
GET /v1/local/diagnostics
```

已覆盖的关键指标和诊断：

- `interview.start`、`interview.turn`、`interview.report` 等核心链路耗时。
- `vad.detect`、`asr.transcribe`、`realtime.*` 语音链路耗时。
- LLM 调用成功率、延迟和错误分类。
- SQLite 中持久化的 trace 聚合。
- 本地 data 目录可写性、SQLite integrity_check、schema 版本、历史导出能力和评分评测集可用性。

错误分类包括 auth、model_or_endpoint、quota_or_rate_limit、timeout、network、response_shape、tls、validation、conflict、not_implemented 和 unknown。
