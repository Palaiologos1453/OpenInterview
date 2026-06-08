from __future__ import annotations

from copy import deepcopy


DIRECTIONS = [
    {
        "id": "backend",
        "name": "后端开发",
        "summary": "Java/Go/Python 后端、数据库、缓存、并发、分布式基础。",
        "topics": [
            "语言基础",
            "操作系统",
            "计算机网络",
            "数据库",
            "缓存",
            "并发编程",
            "分布式基础",
            "算法",
        ],
        "project_focus": ["业务建模", "接口设计", "数据一致性", "性能优化", "故障排查"],
    },
    {
        "id": "frontend",
        "name": "前端开发",
        "summary": "JavaScript/TypeScript、浏览器、框架、工程化、性能优化。",
        "topics": [
            "JavaScript",
            "TypeScript",
            "浏览器原理",
            "React/Vue",
            "CSS",
            "前端工程化",
            "网络请求",
            "算法",
        ],
        "project_focus": ["组件设计", "状态管理", "性能优化", "异常监控", "工程化取舍"],
    },
    {
        "id": "algorithm",
        "name": "算法工程",
        "summary": "机器学习基础、深度学习、特征工程、模型评估和工程落地能力。",
        "topics": [
            "机器学习基础",
            "深度学习",
            "概率统计",
            "特征工程",
            "模型评估",
            "Python",
            "算法",
        ],
        "project_focus": ["数据处理", "指标选择", "过拟合处理", "消融实验", "线上效果"],
    },
    {
        "id": "test_dev",
        "name": "测试开发",
        "summary": "测试理论、自动化测试、质量平台、脚本能力、CI/CD。",
        "topics": [
            "测试理论",
            "自动化测试",
            "Python/Java",
            "接口测试",
            "性能测试",
            "CI/CD",
            "算法",
        ],
        "project_focus": ["测试策略", "覆盖率", "缺陷定位", "稳定性", "效率提升"],
    },
    {
        "id": "data_engineering",
        "name": "数据开发",
        "summary": "SQL、数仓、离线/实时计算、数据质量、调度系统。",
        "topics": [
            "SQL",
            "数据仓库",
            "Spark/Flink",
            "数据建模",
            "数据质量",
            "调度系统",
            "算法",
        ],
        "project_focus": ["指标口径", "链路延迟", "数据质量", "资源优化", "故障恢复"],
    },
    {
        "id": "ml_engineering",
        "name": "机器学习工程",
        "summary": "模型训练、推理服务、MLOps、向量检索、工程落地。",
        "topics": [
            "机器学习",
            "深度学习",
            "模型部署",
            "推理优化",
            "MLOps",
            "向量检索",
            "算法",
        ],
        "project_focus": ["训练数据", "推理延迟", "服务稳定性", "实验管理", "效果归因"],
    },
    {
        "id": "security",
        "name": "网络安全",
        "summary": "Web 安全、二进制基础、漏洞原理、安全开发、攻防思路。",
        "topics": [
            "Web 安全",
            "操作系统",
            "网络协议",
            "漏洞原理",
            "安全开发",
            "脚本能力",
            "算法",
        ],
        "project_focus": ["威胁建模", "漏洞复现", "风险评估", "修复方案", "自动化能力"],
    },
    {
        "id": "embedded",
        "name": "嵌入式开发",
        "summary": "C/C++、操作系统、驱动、通信协议、硬件调试。",
        "topics": [
            "C/C++",
            "操作系统",
            "计算机组成",
            "驱动基础",
            "通信协议",
            "调试工具",
            "算法",
        ],
        "project_focus": ["资源约束", "实时性", "硬件接口", "稳定性", "调试过程"],
    },
    {
        "id": "sre",
        "name": "SRE/运维开发",
        "summary": "Linux、网络、监控、自动化、稳定性、故障复盘。",
        "topics": [
            "Linux",
            "计算机网络",
            "脚本开发",
            "监控告警",
            "容器",
            "稳定性",
            "算法",
        ],
        "project_focus": ["可观测性", "自动化", "容量评估", "故障定位", "应急预案"],
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
