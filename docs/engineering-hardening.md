# Engineering Hardening Notes

这份文档记录 OpenInterview 从本地 Demo 走向更可解释工程项目的三条改造线。

## Scoring Evaluation

评分评测集位于 `apps/api/eval/scoring_seed.yaml`。文件包含 10 个代表性题目和 10 个回答 profile，展开后形成 100 条带人工期望分数和缺失评分点的样本。

运行：

```powershell
python .\scripts\evaluate_scoring.py --output apps/api/eval/scoring-report.md --json-output apps/api/eval/scoring-report.json
```

脚本会输出：

- 样本数。
- 规则评分和人工期望分的 MAE。
- 分数误差在阈值内的比例。
- 缺失评分点 precision/recall。
- Top 误判案例，方便继续调评分规则或引入 LLM judge 对照。

当前评测集是可审阅 seed，不声称代表真实用户分布。后续更严谨的做法是加入真实模拟面试回答、人工双标注和仲裁标注。

## Session State

API 层不再直接使用裸 `dict` 管理面试会话，而是通过 `SQLiteBackedSessionStore` 访问会话。当前实现仍保留进程内热缓存，但会在缓存 miss 时从 SQLite 恢复历史 turn，并重新计算下一题。

`TurnRequest` 支持可选 `request_id`。客户端重试同一个 turn 时，服务端会根据 `(interview_id, request_id)` 返回首次保存的 payload，避免重复推进面试状态。

当前边界：

- 本地模式默认使用 SQLite-backed store。
- `SessionStore` 接口可以替换为 Redis/Postgres 实现。
- `RealtimeSessionStore` 已抽象，当前默认实现是线程安全的内存 store。

多实例部署时需要把面试 session 和 realtime session 都迁移到外部状态存储，并给 WebSocket 接入层加连接路由或共享状态。

## Metrics

`Trace.span` 会自动把耗时写入 runtime metrics。JSON 指标和 Prometheus 风格文本分别由下面接口暴露：

```text
GET /v1/metrics
GET /v1/metrics/prometheus
```

已覆盖的关键指标：

- `interview.start`、`interview.turn`、`interview.report` 等核心链路耗时。
- `vad.detect`、`asr.transcribe`、`realtime.*` 语音链路耗时。
- LLM 调用成功率、延迟和错误分类。
- SQLite 中持久化的 trace 聚合。

错误分类包括 auth、model_or_endpoint、quota_or_rate_limit、timeout、network、response_shape、tls、validation、conflict、not_implemented 和 unknown。
