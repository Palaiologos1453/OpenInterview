from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JAVAGUIDE_ROOT = Path("D:/JavaGuide")
DEFAULT_OUTPUT = PROJECT_ROOT / "apps/api/openinterview_api/questions/javaguide_generated.yaml"


@dataclass(frozen=True)
class SourceSpec:
    path: str
    direction: str
    topic: str
    max_items: int = 10


SOURCE_SPECS = [
    SourceSpec("docs/java/basis/java-basic-questions-01.md", "backend", "java-basis", 16),
    SourceSpec("docs/java/basis/java-basic-questions-02.md", "backend", "java-basis", 14),
    SourceSpec("docs/java/basis/java-basic-questions-03.md", "backend", "java-basis", 14),
    SourceSpec("docs/java/basis/generics-and-wildcards.md", "backend", "java-basis", 6),
    SourceSpec("docs/java/basis/reflection.md", "backend", "java-basis", 6),
    SourceSpec("docs/java/basis/proxy.md", "backend", "java-basis", 6),
    SourceSpec("docs/java/collection/java-collection-questions-01.md", "backend", "java-collection", 14),
    SourceSpec("docs/java/collection/java-collection-questions-02.md", "backend", "java-collection", 14),
    SourceSpec("docs/java/collection/hashmap-source-code.md", "backend", "java-collection", 8),
    SourceSpec("docs/java/collection/concurrent-hash-map-source-code.md", "backend", "java-collection", 8),
    SourceSpec("docs/java/concurrent/java-concurrent-questions-01.md", "backend", "java-concurrency", 16),
    SourceSpec("docs/java/concurrent/java-concurrent-questions-02.md", "backend", "java-concurrency", 16),
    SourceSpec("docs/java/concurrent/java-concurrent-questions-03.md", "backend", "java-concurrency", 12),
    SourceSpec("docs/java/concurrent/aqs.md", "backend", "java-concurrency", 8),
    SourceSpec("docs/java/concurrent/java-thread-pool-summary.md", "backend", "java-concurrency", 8),
    SourceSpec("docs/java/jvm/memory-area.md", "backend", "jvm", 10),
    SourceSpec("docs/java/jvm/class-loading-process.md", "backend", "jvm", 8),
    SourceSpec("docs/java/jvm/classloader.md", "backend", "jvm", 8),
    SourceSpec("docs/java/jvm/jvm-garbage-collection.md", "backend", "jvm", 14),
    SourceSpec("docs/java/jvm/jdk-monitoring-and-troubleshooting-tools.md", "backend", "jvm", 8),
    SourceSpec("docs/system-design/framework/spring/spring-knowledge-and-questions-summary.md", "backend", "spring", 24),
    SourceSpec("docs/system-design/framework/spring/springboot-knowledge-and-questions-summary.md", "backend", "spring", 18),
    SourceSpec("docs/system-design/framework/spring/spring-transaction.md", "backend", "spring", 8),
    SourceSpec("docs/system-design/framework/spring/spring-boot-auto-assembly-principles.md", "backend", "spring", 8),
    SourceSpec("docs/system-design/framework/mybatis/mybatis-interview.md", "backend", "mybatis", 24),
    SourceSpec("docs/database/mysql/mysql-questions-01.md", "backend", "mysql", 28),
    SourceSpec("docs/database/mysql/mysql-index.md", "backend", "mysql", 12),
    SourceSpec("docs/database/mysql/mysql-logs.md", "backend", "mysql", 10),
    SourceSpec("docs/database/mysql/innodb-implementation-of-mvcc.md", "backend", "mysql", 8),
    SourceSpec("docs/database/redis/redis-questions-01.md", "backend", "redis", 20),
    SourceSpec("docs/database/redis/redis-questions-02.md", "backend", "redis", 16),
    SourceSpec("docs/database/redis/redis-data-structures-01.md", "backend", "redis", 10),
    SourceSpec("docs/database/redis/redis-persistence.md", "backend", "redis", 8),
    SourceSpec("docs/database/redis/cache-basics.md", "backend", "cache", 12),
    SourceSpec("docs/database/redis/3-commonly-used-cache-read-and-write-strategies.md", "backend", "cache", 8),
    SourceSpec("docs/database/redis/redis-common-blocking-problems-summary.md", "backend", "cache", 8),
    SourceSpec("docs/high-performance/message-queue/message-queue.md", "backend", "message-queue", 12),
    SourceSpec("docs/high-performance/message-queue/kafka-questions-01.md", "backend", "message-queue", 14),
    SourceSpec("docs/high-performance/message-queue/rocketmq-questions.md", "backend", "message-queue", 10),
    SourceSpec("docs/high-performance/message-queue/rabbitmq-questions.md", "backend", "message-queue", 10),
    SourceSpec("docs/distributed-system/distributed-system-interview-questions.md", "backend", "distributed-system", 12),
    SourceSpec("docs/distributed-system/distributed-lock.md", "backend", "distributed-system", 8),
    SourceSpec("docs/distributed-system/distributed-transaction.md", "backend", "distributed-system", 8),
    SourceSpec("docs/distributed-system/protocol/cap-and-base-theorem.md", "backend", "distributed-system", 8),
    SourceSpec("docs/distributed-system/protocol/raft-algorithm.md", "backend", "distributed-system", 6),
    SourceSpec("docs/cs-basics/network/other-network-questions.md", "backend", "computer-network", 16),
    SourceSpec("docs/cs-basics/network/other-network-questions2.md", "backend", "computer-network", 16),
    SourceSpec("docs/cs-basics/network/tcp-connection-and-disconnection.md", "backend", "computer-network", 8),
    SourceSpec("docs/cs-basics/operating-system/operating-system-basic-questions-01.md", "backend", "operating-system", 16),
    SourceSpec("docs/cs-basics/operating-system/operating-system-basic-questions-02.md", "backend", "operating-system", 16),
    SourceSpec("docs/system-design/security/basis-of-authority-certification.md", "backend", "security", 8),
    SourceSpec("docs/system-design/security/jwt-intro.md", "backend", "security", 8),
    SourceSpec("docs/system-design/security/data-validation.md", "backend", "security", 8),
    SourceSpec("docs/high-availability/high-availability-interview-questions.md", "backend", "high-availability", 14),
    SourceSpec("docs/high-availability/high-availability-system-interview-questions.md", "backend", "high-availability", 16),
    SourceSpec("docs/high-availability/fallback-and-circuit-breaker.md", "backend", "high-availability", 8),
    SourceSpec("docs/high-availability/timeout-and-retry.md", "backend", "high-availability", 8),
    SourceSpec("docs/high-performance/high-performance-interview-questions.md", "backend", "high-performance", 14),
    SourceSpec("docs/high-performance/high-performance-system-interview-questions.md", "backend", "high-performance", 16),
    SourceSpec("docs/high-performance/sql-optimization.md", "backend", "high-performance", 8),
    SourceSpec("docs/ai/llm-basis/llm-operation-mechanism.md", "ai_application", "llm-basics", 12),
    SourceSpec("docs/ai/llm-basis/llm-api-engineering.md", "ai_application", "llm-api", 14),
    SourceSpec("docs/ai/llm-basis/structured-output-function-calling.md", "ai_application", "structured-output", 12),
    SourceSpec("docs/ai/llm-basis/llm-evaluation.md", "ai_application", "llm-evaluation", 12),
    SourceSpec("docs/ai/agent/prompt-engineering.md", "ai_application", "prompt-engineering", 12),
    SourceSpec("docs/ai/agent/context-engineering.md", "ai_application", "context-engineering", 12),
    SourceSpec("docs/ai/agent/agent-basis.md", "ai_application", "agent", 16),
    SourceSpec("docs/ai/agent/agent-memory.md", "ai_application", "agent-memory", 12),
    SourceSpec("docs/ai/agent/mcp.md", "ai_application", "mcp", 12),
    SourceSpec("docs/ai/agent/workflow-graph-loop.md", "ai_application", "workflow", 12),
    SourceSpec("docs/ai/rag/rag-basis.md", "ai_application", "rag", 14),
    SourceSpec("docs/ai/rag/rag-document-processing.md", "ai_application", "rag-document", 12),
    SourceSpec("docs/ai/rag/rag-vector-store.md", "ai_application", "vector-store", 12),
    SourceSpec("docs/ai/rag/rag-optimization.md", "ai_application", "rag-evaluation", 12),
    SourceSpec("docs/ai/system-design/llm-gateway.md", "ai_application", "llm-gateway", 12),
    SourceSpec("docs/ai/system-design/ai-application-architecture.md", "ai_application", "ai-architecture", 14),
    SourceSpec("docs/ai/system-design/ai-voice.md", "ai_application", "voice-agent", 12),
]


SYSTEM_DESIGN_SCENARIOS = [
    (
        "short-url-system",
        "docs/zhuanlan/back-end-interview-high-frequency-system-design-and-scenario-questions.md",
        "设计一个短链系统。请说明短码生成、重定向链路、存储模型、防刷、统计和过期清理方案。",
        ["短码冲突如何处理？", "热点短链怎么缓存和限流？", "统计 PV/UV 时如何避免影响跳转延迟？"],
    ),
    (
        "flash-sale-system",
        "docs/zhuanlan/back-end-interview-high-frequency-system-design-and-scenario-questions.md",
        "设计一个秒杀系统。请从库存扣减、限流削峰、队列异步、幂等、防超卖和降级兜底展开。",
        ["库存放 Redis 还是数据库？", "消息重复消费如何保证幂等？", "如何验证没有超卖和漏单？"],
    ),
    (
        "lottery-system",
        "docs/zhuanlan/back-end-interview-high-frequency-system-design-and-scenario-questions.md",
        "设计一个抽奖系统。请说明奖池建模、概率计算、库存一致性、风控和中奖结果落库方案。",
        ["概率调整如何审计？", "高并发下奖品库存怎么扣？", "如何防止刷奖和重复领取？"],
    ),
    (
        "third-party-login",
        "docs/zhuanlan/back-end-interview-high-frequency-system-design-and-scenario-questions.md",
        "设计一个第三方授权登录系统。请说明 OAuth 流程、账号绑定、Token 存储、回调安全和风控策略。",
        ["state 参数解决什么问题？", "多个第三方账号如何绑定同一个用户？", "Token 泄露怎么发现和止损？"],
    ),
    (
        "notification-push",
        "docs/system-design/web-real-time-message-push.md",
        "设计一个站内通知/实时消息推送系统。请比较短轮询、长轮询、SSE、WebSocket 和消息队列方案。",
        ["离线消息如何补偿？", "WebSocket 连接数上来后如何扩展？", "如何处理重复推送和顺序问题？"],
    ),
    (
        "order-high-performance",
        "docs/high-performance/high-performance-system-interview-questions.md",
        "设计一个高性能订单系统。请说明下单链路、库存/价格校验、异步化、缓存、分库分表和压测验证。",
        ["下单强一致和最终一致怎么取舍？", "主从延迟会影响哪些读？", "如何定位链路瓶颈？"],
    ),
    (
        "payment-idempotency",
        "docs/high-availability/high-availability-system-interview-questions.md",
        "设计一个支付接口的幂等方案。请说明幂等键、状态机、去重表、超时重试和对账补偿。",
        ["幂等和防重有什么区别？", "处理中状态卡住怎么办？", "如何处理第三方支付回调乱序？"],
    ),
    (
        "rate-limiting-platform",
        "docs/high-availability/high-availability-system-interview-questions.md",
        "设计一个限流能力。请说明固定窗口、滑动窗口、令牌桶、漏桶，以及单机/分布式限流的取舍。",
        ["限流维度怎么选？", "Redis 限流失败时如何兜底？", "怎么避免误伤核心用户？"],
    ),
    (
        "resilience-governance",
        "docs/high-availability/high-availability-system-interview-questions.md",
        "设计一个服务治理里的超时、重试、熔断、降级和隔离方案，要求说明调用链风险和观测指标。",
        ["重试为什么会放大故障？", "线程池隔离和信号量隔离怎么选？", "降级结果如何对用户透明？"],
    ),
    (
        "large-data-dedup",
        "docs/zhuanlan/back-end-interview-high-frequency-system-design-and-scenario-questions.md",
        "设计一个海量数据去重方案。请比较 HashSet、Bitmap、布隆过滤器、外部排序和分片处理。",
        ["布隆过滤器误判如何影响业务？", "内存放不下时怎么拆分？", "如何验证去重准确率？"],
    ),
    (
        "delayed-task",
        "docs/database/redis/redis-delayed-task.md",
        "设计一个延时任务系统。请比较数据库轮询、Redis ZSet、消息队列延时消息和时间轮方案。",
        ["任务执行失败如何重试？", "延迟精度和吞吐怎么权衡？", "如何避免任务重复执行？"],
    ),
    (
        "permission-system",
        "docs/system-design/security/design-of-authority-system.md",
        "设计一个后台权限系统。请说明 RBAC 模型、菜单/接口权限、数据权限、审计和权限缓存失效。",
        ["角色继承会带来什么复杂度？", "数据权限如何下推到查询层？", "权限变更后如何及时生效？"],
    ),
]


STOP_TITLES = {
    "参考",
    "参考资料",
    "相关文章推荐",
    "文章推荐",
    "推荐阅读",
    "相关阅读",
    "总结",
    "小结",
    "结语",
    "目录",
    "前言",
    "后记",
    "todo",
    "readme",
    "介绍",
    "内容概览",
    "内容预览",
    "适合人群",
    "基本语法",
    "变量",
    "方法",
    "集合概述",
    "集合框架底层数据结构总结",
    "hashmap 简介",
    "底层数据结构分析",
    "源码分析",
    "存储结构",
}

STOP_PATTERNS = [
    "版权",
    "公众号",
    "面试官真正想考什么",
    "答题框架",
    "复习建议",
    "推荐复习顺序",
    "面试突击版推荐",
    "核心要点回顾",
    "常见扣分点",
    "基础概念与常识",
    "面向对象基础",
    "mysql 基础",
    "高可用基础",
    "高性能基础",
    "基础架构",
    "基础概念",
    "基础知识",
    "实战",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate OpenInterview questions from JavaGuide headings.")
    parser.add_argument("--javaguide-root", type=Path, default=DEFAULT_JAVAGUIDE_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    questions = generate_questions(args.javaguide_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump({"questions": questions}, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(f"Generated {len(questions)} questions -> {args.output}")


def generate_questions(javaguide_root: Path) -> list[dict]:
    existing: set[str] = set()
    questions: list[dict] = []
    for spec in SOURCE_SPECS:
        path = javaguide_root / spec.path
        if not path.exists():
            print(f"Skip missing source: {path}")
            continue
        headings = extract_headings(path)
        selected = headings[: spec.max_items]
        for index, title in enumerate(selected, start=1):
            question_id = make_id(spec, index, existing)
            existing.add(question_id)
            questions.append(build_question(question_id, spec, title))
    questions.extend(system_design_questions(existing))
    return questions


def system_design_questions(existing: set[str]) -> list[dict]:
    questions = []
    spec = SourceSpec("", "backend", "system-design", len(SYSTEM_DESIGN_SCENARIOS))
    for slug, source_path, prompt, followups in SYSTEM_DESIGN_SCENARIOS:
        question_id = f"jg-backend-system-design-{slug}"
        if question_id in existing:
            continue
        existing.add(question_id)
        questions.append(
            {
                "id": question_id,
                "directions": ["backend"],
                "difficulty": "bigtech",
                "topic": "system-design",
                "type": "scenario",
                "source": "JavaGuide",
                "source_path": source_path,
                "source_license": "Apache-2.0",
                "source_usage": "scenario-adapted",
                "prompt": prompt,
                "followups": followups,
                "rubric": rubric_for(spec.topic),
                "tags": ["system-design", slug],
            }
        )
    return questions


def extract_headings(path: Path) -> list[str]:
    headings: list[str] = []
    seen: set[str] = set()
    in_fence = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{2,3})\s+(.+)$", stripped)
        if not match:
            continue
        title = clean_title(match.group(2))
        if not usable_title(title):
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        headings.append(title)
    return headings


def clean_title(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^[\d.、\s]+", "", text)
    text = re.sub(r"^[#*\-：:\s]+", "", text)
    text = text.replace("⭐️", "").replace("⭐", "").replace("🔥", "")
    text = text.replace("？", "?")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" #*`")


def usable_title(title: str) -> bool:
    normalized = title.strip().lower()
    if not normalized or normalized in STOP_TITLES:
        return False
    if len(title) < 4 or len(title) > 80:
        return False
    if any(pattern.lower() in normalized for pattern in STOP_PATTERNS):
        return False
    if re.fullmatch(r"[a-z0-9._/-]+", normalized):
        return False
    return True


def make_id(spec: SourceSpec, index: int, existing: set[str]) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", Path(spec.path).stem.lower()).strip("-")
    base = f"jg-{spec.direction.replace('_', '-')}-{spec.topic}-{stem}-{index:03d}"
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def build_question(question_id: str, spec: SourceSpec, title: str) -> dict:
    return {
        "id": question_id,
        "directions": [spec.direction],
        "difficulty": difficulty_for(title, spec.topic),
        "topic": spec.topic,
        "type": question_type_for(title, spec.topic),
        "source": "JavaGuide",
        "source_path": spec.path,
        "source_license": "Apache-2.0",
        "source_usage": "heading-adapted",
        "prompt": prompt_for(title, spec),
        "followups": followups_for(spec.topic),
        "rubric": rubric_for(spec.topic),
        "tags": tags_for(spec, title),
    }


def prompt_for(title: str, spec: SourceSpec) -> str:
    normalized_title = title.rstrip("?？")
    if spec.direction == "ai_application":
        if spec.topic in {"ai-architecture", "llm-gateway", "rag", "agent", "workflow", "voice-agent"}:
            return (
                f"如果要在真实 AI 应用项目中处理「{normalized_title}」这个问题，"
                "你会如何设计方案，并说明延迟、成本、效果、稳定性和安全边界？"
            )
        return (
            f"请围绕「{normalized_title}」做一次 AI 应用开发面试回答，"
            "说明核心机制、工程落地方式、评测指标和常见失败场景。"
        )
    if spec.topic in {
        "cache",
        "message-queue",
        "distributed-system",
        "system-design",
        "high-availability",
        "high-performance",
        "security",
    }:
        return (
            f"如果在 Java 后端项目中遇到与「{normalized_title}」相关的问题，"
            "你会如何分析根因、设计方案、权衡风险并验证效果？"
        )
    return (
        f"请解释「{normalized_title}」，要求讲清核心概念、底层机制、适用场景、"
        "常见误区，以及它在 Java 后端项目中的落地方式。"
    )


def difficulty_for(title: str, topic: str) -> str:
    hard_keywords = [
        "源码",
        "原理",
        "架构",
        "事务",
        "隔离",
        "mvcc",
        "aop",
        "循环依赖",
        "垃圾回收",
        "类加载",
        "aqs",
        "cas",
        "cap",
        "base",
        "raft",
        "paxos",
        "一致性",
        "分布式",
        "评测",
        "网关",
        "agent",
        "memory",
    ]
    lowered = title.lower()
    if topic in {"system-design", "distributed-system", "llm-gateway", "ai-architecture"}:
        return "bigtech"
    if any(keyword in lowered or keyword in title for keyword in hard_keywords):
        return "bigtech"
    return "campus"


def question_type_for(title: str, topic: str) -> str:
    scenario_topics = {
        "cache",
        "message-queue",
        "distributed-system",
        "system-design",
        "high-availability",
        "high-performance",
        "security",
        "rag",
        "agent",
        "workflow",
        "llm-gateway",
        "ai-architecture",
        "voice-agent",
    }
    if topic in scenario_topics:
        return "scenario"
    if any(word in title for word in ["如何", "怎么", "设计", "优化", "排查", "选择", "故障"]):
        return "scenario"
    return "fundamentals"


def followups_for(topic: str) -> list[str]:
    mapping = {
        "java-basis": ["这个机制解决了什么问题？", "它和相近概念有什么区别？", "项目里用错会带来什么风险？"],
        "java-collection": ["底层数据结构如何影响性能？", "并发场景下是否安全？", "扩容、遍历或删除时有什么坑？"],
        "java-concurrency": ["线程安全边界在哪里？", "阻塞、超时和取消怎么处理？", "如何用日志或指标定位并发问题？"],
        "jvm": ["线上怎么观察这个问题？", "哪些 JVM 参数或工具能辅助定位？", "调优时如何避免只凭经验改参数？"],
        "spring": ["Spring 在这个点上做了哪些自动化？", "代理、生命周期或事务边界有什么坑？", "线上出问题怎么排查？"],
        "mybatis": ["这个点和 SQL 安全或性能有什么关系？", "动态 SQL、缓存或插件会带来什么边界？", "如何定位映射错误？"],
        "mysql": ["索引、锁或事务在这里会产生什么影响？", "如何用执行计划和慢 SQL 验证判断？", "数据量变大后方案是否还成立？"],
        "redis": ["数据结构或持久化机制如何影响这个问题？", "集群和故障恢复场景下有什么变化？", "如何监控命中率、延迟和内存？"],
        "cache": ["如何区分缓存穿透、击穿和雪崩？", "一致性和性能之间怎么取舍？", "降级、限流和预热怎么配合？"],
        "message-queue": ["如何保证重试、幂等和顺序？", "积压或重复消费怎么排查？", "为什么不直接同步调用？"],
        "distributed-system": ["一致性、可用性和延迟怎么权衡？", "网络分区或节点故障时会怎样？", "如何设计监控和补偿机制？"],
        "computer-network": ["TCP/HTTP 的边界条件是什么？", "线上延迟或连接异常怎么定位？", "网关、负载均衡和客户端超时如何配合？"],
        "operating-system": ["进程、线程或内存模型在这里如何体现？", "系统资源耗尽时会出现什么现象？", "后端服务如何做隔离和限流？"],
        "security": ["攻击面在哪里？", "认证、授权和审计怎么设计？", "如何避免把安全只做在前端？"],
        "system-design": ["先澄清哪些业务和容量约束？", "核心模块和数据流如何拆？", "如何验证可用性、扩展性和降级方案？"],
        "high-availability": ["失败场景如何发现和隔离？", "超时、重试、熔断和降级怎么配合？", "如何避免恢复动作造成二次故障？"],
        "high-performance": ["瓶颈怎么量化？", "缓存、异步、索引和批处理如何取舍？", "优化后如何证明收益？"],
        "llm-basics": ["这个机制如何影响延迟和成本？", "长上下文或并发下会有什么边界？", "如何用指标验证理解是否正确？"],
        "llm-api": ["超时、重试和取消怎么设计？", "不同模型服务商返回差异怎么兼容？", "调用日志需要脱敏记录哪些字段？"],
        "prompt-engineering": ["如何避免 Prompt 只靠经验调参？", "版本、变量和灰度怎么管理？", "怎么评测 Prompt 改动是否变好？"],
        "structured-output": ["结构化输出失败如何兜底？", "Schema 版本变化怎么兼容？", "工具调用参数如何校验和授权？"],
        "rag": ["召回、重排和生成分别怎么评测？", "检索不到或检索错了怎么兜底？", "长上下文和 RAG 怎么取舍？"],
        "rag-document": ["切分粒度如何确定？", "表格、图片和标题层级怎么处理？", "文档更新后如何保证索引一致？"],
        "vector-store": ["向量维度、相似度和过滤条件怎么选？", "冷热数据和权限过滤怎么做？", "如何监控召回质量？"],
        "rag-evaluation": ["离线集怎么构造？", "引用命中率和答案正确率怎么区分？", "线上负反馈如何回流？"],
        "agent": ["工具调用失败怎么办？", "如何限制 Agent 的权限和循环次数？", "什么时候不用 Agent 而用 Workflow？"],
        "agent-memory": ["短期记忆和长期记忆如何区分？", "如何避免记忆污染？", "用户隐私和删除权怎么处理？"],
        "context-engineering": ["上下文预算如何分配？", "过期、重复和冲突信息怎么治理？", "如何证明模型使用了证据？"],
        "mcp": ["MCP Server 的权限边界是什么？", "工具 schema 变更如何兼容？", "如何做审计和超时控制？"],
        "workflow": ["节点失败如何重试或补偿？", "状态如何持久化和回放？", "Workflow 和 Agent 的边界是什么？"],
        "llm-gateway": ["模型路由依据是什么？", "成本、限流和 fallback 如何设计？", "如何避免降级影响答案质量？"],
        "llm-evaluation": ["评测集如何防止污染？", "自动评测和人工评审怎么结合？", "如何把评测接入发布流程？"],
        "ai-architecture": ["同步、流式和异步怎么选？", "Prompt、RAG、Memory 和 Tool 如何分层？", "如何做观测、回放和灰度？"],
        "voice-agent": ["ASR、LLM、TTS 的延迟预算怎么拆？", "打断、静音和噪声怎么处理？", "语音链路如何做端到端评测？"],
    }
    return mapping.get(topic, ["这个点解决什么问题？", "真实项目里有什么边界？", "如何验证方案有效？"])


def rubric_for(topic: str) -> list[str]:
    context = "AI 应用工程" if topic.startswith("llm") or topic in {
        "prompt-engineering",
        "structured-output",
        "rag",
        "rag-document",
        "vector-store",
        "rag-evaluation",
        "agent",
        "agent-memory",
        "context-engineering",
        "mcp",
        "workflow",
        "ai-architecture",
        "voice-agent",
    } else "Java 后端工程"
    return [
        "能先给出准确结论或定义，而不是只堆关键词。",
        "能讲清核心机制、关键流程和与相近方案的区别。",
        f"能结合{context}场景说明适用边界、风险和常见误区。",
        "能给出可验证的排查、测试、监控或评测方法。",
    ]


def tags_for(spec: SourceSpec, title: str) -> list[str]:
    tokens = [spec.topic, Path(spec.path).stem]
    for item in re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{1,}", title):
        if len(item) <= 24:
            tokens.append(item)
    return list(dict.fromkeys(tokens))[:6]


if __name__ == "__main__":
    main()
