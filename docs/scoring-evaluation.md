# Scoring Evaluation

OpenInterview 的评分不是只看一次演示效果，而是用固定评测集持续检查规则评分是否接近人工判断。

## Dataset

评测数据位于 `apps/api/eval/scoring_seed.yaml`，当前共 109 条样本，分两类：

- 模板 profile 样本：覆盖空泛回答、概念回答、结构化中分、强回答、自信但错误、关键词堆砌等模式。
- 真实场景样本：参考常见 Java 后端和 AI 应用面经中的追问方式，覆盖项目个人贡献、指标口径、技术选型、故障复盘、RAG 评测、Agent 工具风险和本地优先隐私边界。

真实场景样本参考公开面经中的高频追问模式，重点模拟面试官常问的问题：

- 这个项目是不是你本人做的？
- 指标从哪里来，统计窗口和基线是什么？
- 为什么选这个方案，替代方案为什么没选？
- 线上出过什么问题，怎么恢复和复盘？
- RAG/Agent 项目怎么评测，误判怎么处理？

## Metrics

运行：

```powershell
python .\scripts\evaluate_scoring.py --output apps/api/eval/scoring-report.md --json-output apps/api/eval/scoring-report.json
```

当前 CI 门禁：

- `score_mae <= 10.0`
- `gap_recall >= 0.9`

报告会输出整体指标、按题型分组指标、真实场景样本指标和 Top 误判案例。

## Current Result

当前报告见 `apps/api/eval/scoring-report.md`。最近一次结果：

- Cases: 109
- Score MAE: 9.29
- Gap recall: 0.972
- Keyword-stuffing 高分误判已被压低，不再因为堆术语直接高分。

## Limitations

当前样本仍是可审阅 seed，不等价于真实用户分布。后续更严谨的方式是采集真实模拟面试回答，做双人标注和仲裁标注，再比较规则评分、人工标注和可选 LLM judge 的一致性。
