# OpenInterview Scoring Evaluation

- Cases: 109
- Score MAE: 9.29
- Within +/-12 rate: 0.67
- Gap precision: 0.894
- Gap recall: 0.972
- Misjudgments: 37

## Breakdown

- all: cases=109, MAE=9.29, gap_recall=0.972
- project: cases=27, MAE=10.44, gap_recall=0.94
- system_design: cases=31, MAE=9.36, gap_recall=1.0
- fundamentals: cases=51, MAE=8.63, gap_recall=0.972
- realistic: cases=9, MAE=8.22, gap_recall=0.683

## Top Misjudgments

### ai-evaluation-missing-validation

- Expected score: 72.0
- Actual score: 34.2
- Score error: 37.8
- Expected gaps: 能解释 Prompt、RAG、模型选择和监控迭代
- Actual gaps: 说明业务目标、基线和评测集来源, 覆盖准确率、召回率、幻觉率、延迟和成本指标, 能解释 Prompt、RAG、模型选择和监控迭代
- Note: none

### backend-observability-missing-validation

- Expected score: 72.0
- Actual score: 42.6
- Score error: 29.4
- Expected gaps: 告警阈值、看板、SLO 和故障复盘
- Actual gaps: 日志、指标、trace 分别解决什么问题, 延迟、错误率、吞吐、队列积压和资源使用指标, 告警阈值、看板、SLO 和故障复盘
- Note: none

### real-ai-rag-eval-vague

- Expected score: 44.0
- Actual score: 25
- Score error: 19.0
- Expected gaps: 说明业务目标、基线和评测集来源, 覆盖召回率、答案正确率、引用准确率、幻觉率、延迟和成本, 分析误判案例、人工复核和灰度策略, 能解释切分、召回、Rerank、Prompt 和监控迭代
- Actual gaps: 说明业务目标、基线和评测集来源, 覆盖召回率、答案正确率、引用准确率、幻觉率、延迟和成本, 分析误判案例、人工复核和灰度策略
- Note: none

### real-backend-cache-project-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps: 区分个人贡献和团队成果, 说明技术选型、替代方案和取舍, 给出指标口径、验证方式、故障风险和复盘
- Actual gaps: 讲清业务背景、瓶颈和目标, 说明技术选型、替代方案和取舍, 给出指标口径、验证方式、故障风险和复盘
- Note: 典型包装式项目回答。

### backend-index-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps:  B+ 树叶子节点有序链表适合范围查询, 回表、覆盖索引、最左前缀和选择性等边界, 能结合 explain、慢查询或压测验证优化效果
- Actual gaps: 索引减少扫描行数和随机查找成本,  B+ 树叶子节点有序链表适合范围查询, 回表、覆盖索引、最左前缀和选择性等边界, 能结合 explain、慢查询或压测验证优化效果
- Note: none

### backend-cache-consistency-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps: 先更新数据库再删缓存、延迟双删、订阅 binlog 等方,  TTL、互斥锁、降级、重试和幂等, 监控、告警和数据修复手段
- Actual gaps: 缓存穿透、击穿、雪崩和缓存数据库不一致, 先更新数据库再删缓存、延迟双删、订阅 binlog 等方,  TTL、互斥锁、降级、重试和幂等, 监控、告警和数据修复手段
- Note: none

### backend-thread-process-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps: 上下文切换成本、通信方式和故障隔离, 能结合 IO 密集、CPU 密集和异步服务场景选型, 线程池、阻塞调用和上下文传递风险
- Actual gaps: 进程资源隔离、线程共享进程资源、协程用户态调度, 上下文切换成本、通信方式和故障隔离, 能结合 IO 密集、CPU 密集和异步服务场景选型, 线程池、阻塞调用和上下文传递风险
- Note: none

### backend-project-truth-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps: 说明个人贡献和关键技术方案, 给出指标结果、验证方式和复盘, 能解释技术选型依据、故障风险和项目真实性
- Actual gaps: 讲清业务背景和目标, 说明个人贡献和关键技术方案, 给出指标结果、验证方式和复盘, 能解释技术选型依据、故障风险和项目真实性
- Note: none

### backend-system-design-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps: 能拆分接入层、会话状态、题库、评分和报告模块,  Redis/Postgres、消息队列、幂等和重试设计, 监控、限流、降级、故障恢复和压测验证
- Actual gaps: 能澄清用户规模、读写比例、延迟目标和一致性要求, 能拆分接入层、会话状态、题库、评分和报告模块,  Redis/Postgres、消息队列、幂等和重试设计, 监控、限流、降级、故障恢复和压测验证
- Note: none

### ai-token-sampling-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps:  temperature、top_p 等采样参数影响随机, 上下文截断、幻觉、重复和格式漂移风险, 能结合评测集、日志和线上指标调参
- Actual gaps:  token 数影响上下文长度、延迟和成本,  temperature、top_p 等采样参数影响随机, 上下文截断、幻觉、重复和格式漂移风险, 能结合评测集、日志和线上指标调参
- Note: none

### ai-rag-pipeline-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps: 向量召回、关键词召回和 Rerank 的作用, 上下文组装、引用、去重和 token 预算, 离线评测、线上反馈和失败案例分析
- Actual gaps: 文档切分粒度、元数据和召回召准权衡, 向量召回、关键词召回和 Rerank 的作用, 上下文组装、引用、去重和 token 预算, 离线评测、线上反馈和失败案例分析
- Note: none

### ai-agent-tools-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps: 参数 schema 校验、权限边界和最小授权, 审计日志、人工确认、回滚和幂等, 能结合高风险动作、沙箱和监控告警设计
- Actual gaps: 工具调用会放大模型幻觉和越权风险, 参数 schema 校验、权限边界和最小授权, 审计日志、人工确认、回滚和幂等, 能结合高风险动作、沙箱和监控告警设计
- Note: none

### ai-evaluation-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps: 覆盖准确率、召回率、幻觉率、延迟和成本指标, 分析误判案例、人工复核和灰度策略, 能解释 Prompt、RAG、模型选择和监控迭代
- Actual gaps: 说明业务目标、基线和评测集来源, 覆盖准确率、召回率、幻觉率、延迟和成本指标, 分析误判案例、人工复核和灰度策略, 能解释 Prompt、RAG、模型选择和监控迭代
- Note: none

### backend-observability-vague

- Expected score: 42.0
- Actual score: 25
- Score error: 17.0
- Expected gaps: 延迟、错误率、吞吐、队列积压和资源使用指标, 能设计 traceId、结构化日志、采样和脱敏, 告警阈值、看板、SLO 和故障复盘
- Actual gaps: 日志、指标、trace 分别解决什么问题, 延迟、错误率、吞吐、队列积压和资源使用指标, 能设计 traceId、结构化日志、采样和脱敏, 告警阈值、看板、SLO 和故障复盘
- Note: none

### backend-index-wrong-confident

- Expected score: 38.0
- Actual score: 25
- Score error: 13.0
- Expected gaps:  B+ 树叶子节点有序链表适合范围查询, 回表、覆盖索引、最左前缀和选择性等边界, 能结合 explain、慢查询或压测验证优化效果
- Actual gaps: 索引减少扫描行数和随机查找成本,  B+ 树叶子节点有序链表适合范围查询, 回表、覆盖索引、最左前缀和选择性等边界, 能结合 explain、慢查询或压测验证优化效果
- Note: 自信但错误，规则评分容易因语气和关键词虚高。
