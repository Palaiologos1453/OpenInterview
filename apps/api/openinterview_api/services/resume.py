from __future__ import annotations

import re
from dataclasses import dataclass, asdict


TECH_KEYWORDS = [
    "Java",
    "Go",
    "Python",
    "C++",
    "JavaScript",
    "TypeScript",
    "React",
    "Vue",
    "Spring",
    "MySQL",
    "PostgreSQL",
    "Redis",
    "MongoDB",
    "Docker",
    "Kubernetes",
    "Linux",
    "Spark",
    "Flink",
    "PyTorch",
    "TensorFlow",
    "LLM",
    "RAG",
    "HTTP",
    "TCP",
    "RPC",
]


PROJECT_PATTERNS = [
    re.compile(r"(项目|Project)[:：]?\s*(?P<name>[^。\n]{2,40})"),
    re.compile(r"(?P<name>[^。\n]{2,40})(项目|系统|平台|应用)"),
]


@dataclass
class ResumeAnalysis:
    tech_stack: list[str]
    projects: list[str]
    internships: list[str]
    highlights: list[str]
    risks: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def analyze_resume(text: str) -> ResumeAnalysis:
    normalized = text.strip()
    tech_stack = _extract_tech_stack(normalized)
    projects = _extract_projects(normalized)
    internships = _extract_internships(normalized)
    highlights = _extract_highlights(normalized)
    risks = _extract_risks(normalized, tech_stack, projects)
    return ResumeAnalysis(
        tech_stack=tech_stack,
        projects=projects,
        internships=internships,
        highlights=highlights,
        risks=risks,
    )


def _extract_tech_stack(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for keyword in TECH_KEYWORDS:
        if keyword.lower() in lowered:
            found.append(keyword)
    return found


def _extract_projects(text: str) -> list[str]:
    projects: list[str] = []
    for pattern in PROJECT_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group("name").strip(" ：:-")
            if 2 <= len(name) <= 40 and name not in projects:
                projects.append(name)
    return projects[:6]


def _extract_internships(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [line for line in lines if "实习" in line or "intern" in line.lower()][:5]


def _extract_highlights(text: str) -> list[str]:
    patterns = [
        r"降低[^。\n]{0,20}",
        r"提升[^。\n]{0,20}",
        r"优化[^。\n]{0,20}",
        r"负责[^。\n]{0,24}",
        r"主导[^。\n]{0,24}",
    ]
    highlights: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            item = match.group(0).strip()
            if item and item not in highlights:
                highlights.append(item)
    return highlights[:8]


def _extract_risks(text: str, tech_stack: list[str], projects: list[str]) -> list[str]:
    risks = []
    if len(text) < 120:
        risks.append("简历内容偏短，项目深挖问题会缺少上下文。")
    if not tech_stack:
        risks.append("未识别到明确技术栈，建议补充语言、框架、数据库或工具。")
    if not projects:
        risks.append("未识别到明确项目名称，建议用项目名 + 背景 + 个人贡献组织。")
    if not re.search(r"\d+%|\d+ms|\d+秒|\d+万|\d+QPS|\d+qps", text):
        risks.append("缺少可量化结果，真实面试中容易被追问效果如何证明。")
    return risks

