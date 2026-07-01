# OpenInterview Scoring Evaluation

- Cases: 100
- Score MAE: 12.45
- Within +/-12 rate: 0.6
- Gap precision: 0.789
- Gap recall: 0.85
- Misjudgments: 40

## Top Misjudgments

### backend-system-design-keyword-stuffing

- Expected score: 45.0
- Actual score: 82.5
- Score error: 37.5
- Expected gaps: 能澄清用户规模、读写比例、延迟目标和一致性要求, 能拆分接入层、会话状态、题库、评分和报告模块,  Redis/Postgres、消息队列、幂等和重试设计, 监控、限流、降级、故障恢复和压测验证
- Actual gaps: none
- Note: 关键词堆砌不应高分。

### backend-project-truth-keyword-stuffing

- Expected score: 45.0
- Actual score: 79.9
- Score error: 34.9
- Expected gaps: 讲清业务背景和目标, 说明个人贡献和关键技术方案, 给出指标结果、验证方式和复盘, 能解释技术选型依据、故障风险和项目真实性
- Actual gaps: none
- Note: 关键词堆砌不应高分。

### backend-thread-process-keyword-stuffing

- Expected score: 45.0
- Actual score: 78.5
- Score error: 33.5
- Expected gaps: 进程资源隔离、线程共享进程资源、协程用户态调度, 上下文切换成本、通信方式和故障隔离, 能结合 IO 密集、CPU 密集和异步服务场景选型, 线程池、阻塞调用和上下文传递风险
- Actual gaps: none
- Note: 关键词堆砌不应高分。

### ai-evaluation-keyword-stuffing

- Expected score: 45.0
- Actual score: 78.5
- Score error: 33.5
- Expected gaps: 说明业务目标、基线和评测集来源, 覆盖准确率、召回率、幻觉率、延迟和成本指标, 分析误判案例、人工复核和灰度策略, 能解释 Prompt、RAG、模型选择和监控迭代
- Actual gaps: none
- Note: 关键词堆砌不应高分。

### ai-agent-tools-keyword-stuffing

- Expected score: 45.0
- Actual score: 77.6
- Score error: 32.6
- Expected gaps: 工具调用会放大模型幻觉和越权风险, 参数 schema 校验、权限边界和最小授权, 审计日志、人工确认、回滚和幂等, 能结合高风险动作、沙箱和监控告警设计
- Actual gaps: none
- Note: 关键词堆砌不应高分。

### backend-cache-consistency-keyword-stuffing

- Expected score: 45.0
- Actual score: 76.0
- Score error: 31.0
- Expected gaps: 缓存穿透、击穿、雪崩和缓存数据库不一致, 先更新数据库再删缓存、延迟双删、订阅 binlog 等方,  TTL、互斥锁、降级、重试和幂等, 监控、告警和数据修复手段
- Actual gaps: none
- Note: 关键词堆砌不应高分。

### backend-observability-keyword-stuffing

- Expected score: 45.0
- Actual score: 74.7
- Score error: 29.7
- Expected gaps: 日志、指标、trace 分别解决什么问题, 延迟、错误率、吞吐、队列积压和资源使用指标, 能设计 traceId、结构化日志、采样和脱敏, 告警阈值、看板、SLO 和故障复盘
- Actual gaps: none
- Note: 关键词堆砌不应高分。

### backend-index-keyword-stuffing

- Expected score: 45.0
- Actual score: 74.3
- Score error: 29.3
- Expected gaps: 索引减少扫描行数和随机查找成本,  B+ 树叶子节点有序链表适合范围查询, 回表、覆盖索引、最左前缀和选择性等边界, 能结合 explain、慢查询或压测验证优化效果
- Actual gaps: none
- Note: 关键词堆砌不应高分。

### ai-token-sampling-keyword-stuffing

- Expected score: 45.0
- Actual score: 72.4
- Score error: 27.4
- Expected gaps:  token 数影响上下文长度、延迟和成本,  temperature、top_p 等采样参数影响随机, 上下文截断、幻觉、重复和格式漂移风险, 能结合评测集、日志和线上指标调参
- Actual gaps: none
- Note: 关键词堆砌不应高分。

### backend-cache-consistency-structured-mid

- Expected score: 70.0
- Actual score: 95
- Score error: 25.0
- Expected gaps: 监控、告警和数据修复手段
- Actual gaps: 监控、告警和数据修复手段
- Note: none

### backend-thread-process-structured-mid

- Expected score: 70.0
- Actual score: 95
- Score error: 25.0
- Expected gaps: 线程池、阻塞调用和上下文传递风险
- Actual gaps: 线程池、阻塞调用和上下文传递风险
- Note: none

### backend-system-design-structured-mid

- Expected score: 70.0
- Actual score: 95
- Score error: 25.0
- Expected gaps: 监控、限流、降级、故障恢复和压测验证
- Actual gaps: 监控、限流、降级、故障恢复和压测验证
- Note: none

### ai-token-sampling-structured-mid

- Expected score: 70.0
- Actual score: 95
- Score error: 25.0
- Expected gaps: 能结合评测集、日志和线上指标调参
- Actual gaps: 能结合评测集、日志和线上指标调参
- Note: none

### backend-observability-structured-mid

- Expected score: 70.0
- Actual score: 95
- Score error: 25.0
- Expected gaps: 告警阈值、看板、SLO 和故障复盘
- Actual gaps: 告警阈值、看板、SLO 和故障复盘
- Note: none

### backend-index-structured-mid

- Expected score: 70.0
- Actual score: 92.1
- Score error: 22.1
- Expected gaps: 能结合 explain、慢查询或压测验证优化效果
- Actual gaps: 能结合 explain、慢查询或压测验证优化效果
- Note: none
