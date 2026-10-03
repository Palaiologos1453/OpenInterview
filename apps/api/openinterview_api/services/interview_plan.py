"""Small, local interview plans used by the semantic director.

The plan is deterministic and contains no provider data. It is persisted with
the interview so a restored session can continue without rebuilding a prompt
from the complete transcript.
"""
from __future__ import annotations

from copy import deepcopy


_FLOW = {
    "comprehensive": ["self_intro", "project", "fundamentals", "system_design", "fundamentals", "closing"],
    "fundamentals": ["fundamentals", "fundamentals", "fundamentals", "closing"],
    "project_deep_dive": ["project", "project", "project", "project", "closing"],
    "system_design_intro": ["project", "system_design", "system_design", "fundamentals", "closing"],
}

_OBJECTIVES = {
    "self_intro": ("建立候选人背景基线", ["技术栈", "项目经历", "个人亮点"]),
    "project": ("验证项目经历和个人贡献", ["职责边界", "关键约束", "方案取舍", "效果验证"]),
    "fundamentals": ("验证基础知识的理解和迁移", ["概念", "机制", "前提边界", "场景应用"]),
    "system_design": ("验证系统设计与工程权衡", ["模块拆分", "数据与状态", "性能容量", "可靠性"]),
    "closing": ("完成面试收尾", ["候选人反问", "面试体验"]),
}


def build_plan(mode_id: str = "comprehensive", direction_id: str = "backend") -> list[dict]:
    """Build a compact outline; it is intentionally independent of the LLM."""
    phases = _FLOW.get(mode_id, _FLOW["comprehensive"])
    plan = []
    for index, phase in enumerate(phases):
        objective, key_points = _OBJECTIVES.get(phase, (phase, []))
        plan.append({
            "stage_index": index,
            "phase": phase,
            "objective": objective,
            "key_points": list(key_points),
            "direction": direction_id,
            "max_depth": 4,
        })
    return plan


def compact_plan(plan: list[dict], stage_index: int, depth: int) -> dict:
    """Return only the active and immediately upcoming stage.

    The complete plan remains in local session state. Replaying all stages on
    every turn added prompt tokens without helping the current decision.
    """
    if not plan:
        return {"current": {}, "next": None, "depth": depth}
    index = min(stage_index, len(plan) - 1)

    def view(item: dict) -> dict:
        return {
            "phase": item.get("phase"),
            "goal": item.get("objective"),
            "keys": item.get("key_points", []),
        }

    return {
        "current": view(plan[index]),
        "next": view(plan[index + 1]) if index + 1 < len(plan) else None,
        "depth": depth,
    }


def compact_key_points(state: dict, field: str, limit: int = 4) -> list[dict]:
    """Return local findings without replaying raw answers or evidence quotes."""
    result = []
    for finding in state.get(field, [])[-limit:]:
        result.append({
            "target": finding.get("target"),
            "status": finding.get("status"),
            "observation": str(finding.get("observation") or "")[:120],
            "project": finding.get("project"),
        })
    return result


def clone_plan(plan: list[dict] | None, mode_id: str, direction_id: str) -> list[dict]:
    return deepcopy(plan) if plan else build_plan(mode_id, direction_id)
