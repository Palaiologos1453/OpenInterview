from __future__ import annotations


TOPICS_BY_DIRECTION = {
    "backend": [
        "java-basis",
        "java-collection",
        "java-concurrency",
        "jvm",
        "spring",
        "mybatis",
        "mysql",
        "redis",
        "message-queue",
        "distributed-system",
        "system-design",
    ],
    "ai_application": [
        "llm-basics",
        "llm-api",
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
        "llm-gateway",
        "llm-evaluation",
        "ai-architecture",
        "voice-agent",
    ],
}


def question_coverage(questions: list[dict], direction_id: str = "backend") -> dict:
    scoped_questions = [
        item for item in questions
        if direction_id in item.get("directions", []) and item.get("type") != "coding"
    ]
    ordered_topics = TOPICS_BY_DIRECTION.get(direction_id, [])
    topic_counts = {topic: 0 for topic in ordered_topics}
    topic_quality = {topic: {"with_followups": 0, "with_rubric": 0} for topic in ordered_topics}
    difficulty_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}

    for item in scoped_questions:
        topic = str(item.get("topic") or "other")
        if topic not in topic_counts:
            topic_counts[topic] = 0
            topic_quality[topic] = {"with_followups": 0, "with_rubric": 0}
        topic_counts[topic] += 1
        if item.get("followups"):
            topic_quality[topic]["with_followups"] += 1
        if item.get("rubric"):
            topic_quality[topic]["with_rubric"] += 1
        difficulty = str(item.get("difficulty") or "unknown")
        difficulty_counts[difficulty] = difficulty_counts.get(difficulty, 0) + 1
        question_type = str(item.get("type") or "unknown")
        type_counts[question_type] = type_counts.get(question_type, 0) + 1

    topics = []
    for topic, count in sorted(topic_counts.items(), key=lambda item: _topic_sort_key(item[0], ordered_topics)):
        quality = topic_quality.get(topic, {"with_followups": 0, "with_rubric": 0})
        topics.append(
            {
                "topic": topic,
                "count": count,
                "with_followups": quality["with_followups"],
                "with_rubric": quality["with_rubric"],
                "status": _coverage_status(count, direction_id, topic, ordered_topics),
                "next_action": _next_action(topic, count, quality, direction_id, ordered_topics),
            }
        )

    return {
        "direction_id": direction_id,
        "total": len(scoped_questions),
        "topics": topics,
        "difficulty_counts": difficulty_counts,
        "type_counts": type_counts,
        "gaps": [item for item in topics if item["status"] != "ok"],
    }


def _coverage_target(direction_id: str, topic: str, ordered_topics: list[str]) -> tuple[int, int]:
    if ordered_topics and topic not in ordered_topics:
        return 1, 3
    if direction_id == "ai_application":
        return 3, 5
    return 5, 10


def _coverage_status(
    count: int,
    direction_id: str,
    topic: str,
    ordered_topics: list[str],
) -> str:
    warn_threshold, ok_threshold = _coverage_target(direction_id, topic, ordered_topics)
    if count >= ok_threshold:
        return "ok"
    if count >= warn_threshold:
        return "warn"
    return "bad"


def _next_action(
    topic: str,
    count: int,
    quality: dict,
    direction_id: str,
    ordered_topics: list[str],
) -> str:
    warn_threshold, ok_threshold = _coverage_target(direction_id, topic, ordered_topics)
    if count < warn_threshold:
        return f"{topic} 题量不足，优先补到 {warn_threshold} 道以上。"
    if quality.get("with_followups", 0) < count:
        return f"{topic} 还有题目缺追问。"
    if quality.get("with_rubric", 0) < count:
        return f"{topic} 还有题目缺评分点。"
    if count < ok_threshold:
        return f"{topic} 可继续补场景题，目标 {ok_threshold} 道。"
    return "覆盖较好，后续按用户反馈微调。"


def _topic_sort_key(topic: str, ordered_topics: list[str]) -> tuple[int, str]:
    try:
        return ordered_topics.index(topic), topic
    except ValueError:
        return len(ordered_topics), topic
