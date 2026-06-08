from __future__ import annotations


JAVA_BACKEND_TOPICS = [
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
]


def question_coverage(questions: list[dict]) -> dict:
    backend_questions = [
        item for item in questions
        if "backend" in item.get("directions", []) and item.get("type") != "coding"
    ]
    topic_counts = {topic: 0 for topic in JAVA_BACKEND_TOPICS}
    topic_quality = {topic: {"with_followups": 0, "with_rubric": 0} for topic in JAVA_BACKEND_TOPICS}
    difficulty_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}

    for item in backend_questions:
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
    for topic, count in sorted(topic_counts.items(), key=lambda item: _topic_sort_key(item[0])):
        quality = topic_quality.get(topic, {"with_followups": 0, "with_rubric": 0})
        topics.append(
            {
                "topic": topic,
                "count": count,
                "with_followups": quality["with_followups"],
                "with_rubric": quality["with_rubric"],
                "status": _coverage_status(count),
                "next_action": _next_action(topic, count, quality),
            }
        )

    return {
        "total": len(backend_questions),
        "topics": topics,
        "difficulty_counts": difficulty_counts,
        "type_counts": type_counts,
        "gaps": [item for item in topics if item["status"] != "ok"],
    }


def _coverage_status(count: int) -> str:
    if count >= 10:
        return "ok"
    if count >= 5:
        return "warn"
    return "bad"


def _next_action(topic: str, count: int, quality: dict) -> str:
    if count < 5:
        return f"{topic} 题量不足，优先补到 5 道以上。"
    if quality.get("with_followups", 0) < count:
        return f"{topic} 还有题目缺追问。"
    if quality.get("with_rubric", 0) < count:
        return f"{topic} 还有题目缺评分点。"
    if count < 10:
        return f"{topic} 可继续补场景题，目标 10 道。"
    return "覆盖较好，后续按用户反馈微调。"


def _topic_sort_key(topic: str) -> tuple[int, str]:
    try:
        return JAVA_BACKEND_TOPICS.index(topic), topic
    except ValueError:
        return len(JAVA_BACKEND_TOPICS), topic
