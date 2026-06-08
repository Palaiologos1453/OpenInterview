from __future__ import annotations

from copy import deepcopy


DIRECTIONS = [
    {
        "id": "backend",
        "name": "Java 后端",
        "summary": "Java 后端、JVM、Spring、数据库、缓存、并发和分布式基础。",
        "topics": [
            "Java 基础",
            "JVM",
            "Spring",
            "操作系统",
            "计算机网络",
            "数据库",
            "缓存",
            "并发编程",
            "分布式基础",
            "系统设计",
        ],
        "project_focus": ["个人贡献", "技术选型", "接口设计", "数据一致性", "性能优化", "故障复盘"],
    },
]


DIFFICULTIES = [
    {
        "id": "internship",
        "name": "实习面试",
        "summary": "重基础、轻工程深度，追问较少。",
        "pressure": 1,
        "expectation": "能讲清基础概念，有一个可讨论的课程或项目经历。",
    },
    {
        "id": "campus",
        "name": "普通校招",
        "summary": "基础、项目、算法均衡考察。",
        "pressure": 2,
        "expectation": "能围绕项目讲清方案、取舍和问题定位。",
    },
    {
        "id": "bigtech",
        "name": "大厂校招",
        "summary": "更重追问、边界条件、复杂度和工程细节。",
        "pressure": 3,
        "expectation": "回答需要体现原理理解、工程落地和自我复盘。",
    },
    {
        "id": "top_tier",
        "name": "头部冲刺",
        "summary": "高压多轮追问，包含开放问题和系统设计入门。",
        "pressure": 4,
        "expectation": "能主动澄清问题、讨论约束、给出取舍和验证方案。",
    },
]


MODES = [
    {
        "id": "comprehensive",
        "name": "综合评估",
        "summary": "按真实中小厂技术面节奏，覆盖自我介绍、项目、八股基础、场景题和反问。",
    },
    {
        "id": "fundamentals",
        "name": "单纯八股",
        "summary": "只围绕计算机基础和方向知识点连续追问，适合刷 JavaGuide 后查漏补缺。",
    },
    {
        "id": "project_deep_dive",
        "name": "简历拷打",
        "summary": "围绕简历项目追问个人贡献、方案取舍、指标结果、故障风险和复盘。",
    },
    {
        "id": "system_design_intro",
        "name": "系统设计专项",
        "summary": "训练需求澄清、模块拆分、容量估算、架构取舍和验证方案。",
    },
]


RUBRIC = [
    {
        "id": "cs_fundamentals",
        "name": "计算机基础",
        "description": "概念准确性、原理理解、边界条件和常见误区。",
    },
    {
        "id": "project_depth",
        "name": "项目深度",
        "description": "是否讲清业务目标、个人贡献、技术方案、指标和复盘。",
    },
    {
        "id": "communication",
        "name": "表达沟通",
        "description": "结构化表达、澄清问题、结论先行和互动节奏。",
    },
    {
        "id": "role_fit",
        "name": "岗位匹配",
        "description": "技术栈、项目经历和岗位方向的一致性。",
    },
]


def get_catalog() -> dict:
    return {
        "directions": deepcopy(DIRECTIONS),
        "difficulties": deepcopy(DIFFICULTIES),
        "modes": deepcopy(MODES),
        "rubric": deepcopy(RUBRIC),
    }


def find_direction(direction_id: str) -> dict:
    return _find_by_id(DIRECTIONS, direction_id, "direction")


def find_difficulty(difficulty_id: str) -> dict:
    return _find_by_id(DIFFICULTIES, difficulty_id, "difficulty")


def find_mode(mode_id: str) -> dict:
    return _find_by_id(MODES, mode_id, "mode")


def _find_by_id(items: list[dict], item_id: str, label: str) -> dict:
    for item in items:
        if item["id"] == item_id:
            return deepcopy(item)
    raise ValueError(f"Unknown {label}: {item_id}")
