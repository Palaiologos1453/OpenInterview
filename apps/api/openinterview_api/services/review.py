from __future__ import annotations

import hashlib


def review_items_from_report(report: dict) -> list[dict]:
    items: list[dict] = []
    for turn in report.get("turns") or []:
        meta = turn.get("question_meta") or {}
        gaps = list(turn.get("rubric_gaps") or [])
        score = float(turn.get("score") or 0)
        if meta.get("phase") == "closing":
            continue
        if score >= 75 and not gaps:
            continue
        question = str(turn.get("question") or "").split("\n", 1)[0]
        question_id = meta.get("parent_id") or meta.get("id")
        item_id = _review_item_id(report.get("session_id"), question_id, question)
        items.append(
            {
                "id": item_id,
                "interview_id": report.get("session_id"),
                "question_id": question_id,
                "topic": meta.get("topic") or meta.get("phase") or "interview",
                "question": question,
                "answer": turn.get("answer") or "",
                "score": score,
                "gaps": gaps,
                "rewrite_advice": list(turn.get("rewrite_advice") or []),
                "status": "todo",
                "attempts": [
                    {
                        "answer": turn.get("answer") or "",
                        "score": score,
                        "gaps": gaps,
                        "created_from": "report",
                    }
                ],
            }
        )
    return items[:20]


def report_to_markdown(report: dict) -> str:
    lines = [
        f"# OpenInterview 面试报告 {report.get('overall_score', 0)} / 100",
        "",
        f"- 方向：{report.get('direction', '')}",
        f"- 难度：{report.get('difficulty', '')}",
        f"- Session：{report.get('session_id', '')}",
        "",
    ]
    if report.get("ai_summary"):
        lines.extend(["## 总结", "", str(report["ai_summary"]), ""])
    lines.extend(["## 维度评分", ""])
    for item in report.get("dimensions") or []:
        lines.append(f"- {item.get('name')}: {item.get('score')}，{item.get('advice', '')}")
    lines.extend(["", "## 改进建议", ""])
    for item in report.get("improvements") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## 复习计划", ""])
    for item in report.get("review_plan") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## 复练题", ""])
    for drill in report.get("practice_drills") or []:
        lines.extend([
            f"### {drill.get('topic', 'practice')} - {drill.get('focus', '')}",
            "",
            str(drill.get("prompt") or ""),
            "",
        ])
    lines.extend(["## 题目学习卡", ""])
    for guide in report.get("study_guides") or []:
        lines.extend([
            f"### {guide.get('topic', 'interview')}",
            "",
            f"题目：{guide.get('question', '')}",
            "",
            f"参考答案：{guide.get('reference_answer', '')}",
            "",
            "常见错误：",
        ])
        for item in guide.get("common_mistakes") or []:
            lines.append(f"- {item}")
        lines.extend(["", "面试官追问点："])
        for item in guide.get("interviewer_followups") or []:
            lines.append(f"- {item}")
        lines.extend(["", f"低分回答：{guide.get('low_score_answer', '')}", ""])
        lines.extend([f"高分回答：{guide.get('high_score_answer', '')}", ""])
    lines.extend(["## 逐题复盘", ""])
    for index, turn in enumerate(report.get("turns") or [], start=1):
        meta = turn.get("question_meta") or {}
        lines.extend([
            f"### 第 {index} 题：{meta.get('topic') or meta.get('id') or 'interview'}",
            "",
            f"题目：{turn.get('question', '')}",
            "",
            f"回答：{turn.get('answer', '')}",
            "",
            f"分数：{turn.get('score', 0)}",
            "",
            f"反馈：{turn.get('feedback', '')}",
            "",
            "评分证据：",
        ])
        for item in turn.get("score_evidence") or []:
            lines.append(f"- {item}")
        lines.extend(["", "重答建议："])
        for item in turn.get("rewrite_advice") or []:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _review_item_id(session_id: str | None, question_id: str | None, question: str) -> str:
    raw = f"{session_id or ''}:{question_id or ''}:{question}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]
