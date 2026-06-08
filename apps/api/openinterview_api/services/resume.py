from __future__ import annotations

import re
from dataclasses import asdict, dataclass


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
    "JVM",
    "Spring Boot",
    "Spring Cloud",
    "MyBatis",
    "Kafka",
    "RabbitMQ",
    "Nginx",
    "Elasticsearch",
    "Dubbo",
]


PROJECT_PATTERNS = [
    re.compile(r"(项目|Project)[:：]?\s*(?P<name>[^。\n]{2,40})"),
    re.compile(r"(?P<name>[^。\n]{2,40})(项目|系统|平台|应用)"),
]

CONTRIBUTION_PATTERNS = [
    r"负责[^。\n；;]{2,48}",
    r"主导[^。\n；;]{2,48}",
    r"独立[^。\n；;]{2,48}",
    r"参与[^。\n；;]{2,48}",
    r"设计[^。\n；;]{2,48}",
    r"实现[^。\n；;]{2,48}",
    r"优化[^。\n；;]{2,48}",
]

METRIC_PATTERN = re.compile(
    r"[^。\n；;]{0,20}(?:\d+(?:\.\d+)?%|\d+(?:\.\d+)?ms|\d+(?:\.\d+)?秒|\d+(?:\.\d+)?万|\d+(?:\.\d+)?QPS|\d+(?:\.\d+)?qps)[^。\n；;]{0,24}"
)

VAGUE_PATTERN = re.compile(
    r"(?:熟悉|了解|精通|掌握|高并发|高可用|海量|大幅|显著|极大|完善|优化了|提升了|降低了)[^。\n；;]{0,28}"
)

TECH_CHOICE_PATTERN = re.compile(
    r"[^。\n；;]{0,18}(?:选型|方案|架构|使用|采用|引入|基于|替代|对比|取舍)[^。\n；;]{2,42}"
)

INCIDENT_PATTERN = re.compile(
    r"[^。\n；;]{0,18}(?:故障|事故|线上|报警|告警|回滚|降级|限流|熔断|复盘|排查|压测|异常)[^。\n；;]{0,42}"
)


@dataclass
class ResumeAnalysis:
    tech_stack: list[str]
    projects: list[str]
    internships: list[str]
    highlights: list[str]
    risks: list[str]
    project_cards: list[dict]
    contributions: list[str]
    vague_claims: list[str]
    metric_questions: list[str]
    tech_choice_questions: list[str]
    incident_questions: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def analyze_resume(text: str) -> ResumeAnalysis:
    normalized = text.strip()
    tech_stack = _extract_tech_stack(normalized)
    projects = _extract_projects(normalized)
    internships = _extract_internships(normalized)
    highlights = _extract_highlights(normalized)
    contributions = _extract_contributions(normalized)
    vague_claims = _extract_vague_claims(normalized)
    project_cards = _extract_project_cards(normalized, projects, tech_stack)
    metric_questions = _metric_questions(normalized, project_cards)
    tech_choice_questions = _tech_choice_questions(normalized, project_cards)
    incident_questions = _incident_questions(normalized, project_cards)
    risks = _extract_risks(normalized, tech_stack, projects, vague_claims, contributions)
    return ResumeAnalysis(
        tech_stack=tech_stack,
        projects=projects,
        internships=internships,
        highlights=highlights,
        risks=risks,
        project_cards=project_cards,
        contributions=contributions,
        vague_claims=vague_claims,
        metric_questions=metric_questions,
        tech_choice_questions=tech_choice_questions,
        incident_questions=incident_questions,
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
            name = re.split(r"[，,；;：:]", name, maxsplit=1)[0].strip()
            if name in {"项目", "系统", "平台", "应用", "Project"}:
                continue
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


def _extract_contributions(text: str) -> list[str]:
    return _unique_matches(text, CONTRIBUTION_PATTERNS, limit=10)


def _extract_vague_claims(text: str) -> list[str]:
    claims = []
    for match in VAGUE_PATTERN.finditer(text):
        item = match.group(0).strip(" ，。；;")
        if len(item) >= 3 and item not in claims:
            claims.append(item)
    return claims[:10]


def _extract_project_cards(text: str, projects: list[str], tech_stack: list[str]) -> list[dict]:
    lines = [line.strip(" -•\t") for line in text.splitlines() if line.strip()]
    if not lines and text:
        lines = [part.strip() for part in re.split(r"[。；;]", text) if part.strip()]

    cards: list[dict] = []
    used_names: set[str] = set()
    for name in projects[:5]:
        if name in used_names:
            continue
        used_names.add(name)
        context = _project_context(name, lines, text)
        card_tech = [item for item in tech_stack if item.lower() in context.lower()]
        contributions = _extract_contributions(context)
        metrics = _extract_metrics(context)
        vague_claims = _extract_vague_claims(context)
        tech_choices = _extract_tech_choices(context)
        incidents = _extract_incidents(context)
        cards.append(
            {
                "name": name,
                "summary": _shorten(context or name, 160),
                "tech_stack": card_tech[:8],
                "contribution_signals": contributions[:5],
                "metrics": metrics[:5],
                "vague_claims": vague_claims[:5],
                "tech_choices": tech_choices[:5],
                "incident_signals": incidents[:5],
                "followup_questions": _project_card_questions(
                    name,
                    contributions,
                    metrics,
                    vague_claims,
                    tech_choices,
                    incidents,
                ),
            }
        )

    if cards:
        return cards

    context = _shorten(text, 260)
    if not context:
        return []
    return [
        {
            "name": "未命名项目",
            "summary": context,
            "tech_stack": tech_stack[:8],
            "contribution_signals": _extract_contributions(text)[:5],
            "metrics": _extract_metrics(text)[:5],
            "vague_claims": _extract_vague_claims(text)[:5],
            "tech_choices": _extract_tech_choices(text)[:5],
            "incident_signals": _extract_incidents(text)[:5],
            "followup_questions": _project_card_questions(
                "这个项目",
                _extract_contributions(text),
                _extract_metrics(text),
                _extract_vague_claims(text),
                _extract_tech_choices(text),
                _extract_incidents(text),
            ),
        }
    ]


def _project_context(name: str, lines: list[str], text: str) -> str:
    related = [line for line in lines if name in line]
    if related:
        return "；".join(related[:3])
    index = text.find(name)
    if index < 0:
        return ""
    start = max(0, index - 80)
    end = min(len(text), index + 260)
    return text[start:end].strip()


def _extract_metrics(text: str) -> list[str]:
    metrics = []
    for match in METRIC_PATTERN.finditer(text):
        item = match.group(0).strip(" ，。；;")
        if item and item not in metrics:
            metrics.append(item)
    return metrics[:8]


def _extract_tech_choices(text: str) -> list[str]:
    choices = []
    for match in TECH_CHOICE_PATTERN.finditer(text):
        item = match.group(0).strip(" ，。；;")
        if item and item not in choices:
            choices.append(item)
    return choices[:8]


def _extract_incidents(text: str) -> list[str]:
    incidents = []
    for match in INCIDENT_PATTERN.finditer(text):
        item = match.group(0).strip(" ，。；;")
        if item and item not in incidents:
            incidents.append(item)
    return incidents[:8]


def _metric_questions(text: str, cards: list[dict]) -> list[str]:
    metrics = _extract_metrics(text)
    questions = [
        f"{card['name']} 的核心指标来自哪里？统计口径、基线和上线后对比数据分别是什么？"
        for card in cards[:3]
        if not card.get("metrics")
    ]
    questions.extend(f"简历里写到「{item}」，这个数值的采集方式、时间窗口和对照组是什么？" for item in metrics[:4])
    return _dedupe(questions)[:6]


def _tech_choice_questions(text: str, cards: list[dict]) -> list[str]:
    choices = _extract_tech_choices(text)
    questions = [
        f"{card['name']} 为什么选择当前技术方案？当时比较过哪些替代方案，分别放弃的原因是什么？"
        for card in cards[:3]
        if not card.get("tech_choices")
    ]
    questions.extend(f"关于「{item}」，选型依据是什么？成本、复杂度和稳定性怎么权衡？" for item in choices[:4])
    return _dedupe(questions)[:6]


def _incident_questions(text: str, cards: list[dict]) -> list[str]:
    incidents = _extract_incidents(text)
    questions = [
        f"{card['name']} 上线后出现过什么故障、性能问题或负反馈？你负责了哪些排查和复盘动作？"
        for card in cards[:3]
        if not card.get("incident_signals")
    ]
    questions.extend(f"简历里提到「{item}」，当时根因、恢复动作、长期改进分别是什么？" for item in incidents[:4])
    return _dedupe(questions)[:6]


def _project_card_questions(
    name: str,
    contributions: list[str],
    metrics: list[str],
    vague_claims: list[str],
    tech_choices: list[str],
    incidents: list[str],
) -> list[str]:
    questions = [
        f"{name} 里哪些工作是你独立完成的？请区分团队成果和个人贡献。",
        f"{name} 的技术选型依据是什么？有没有更简单或更稳的替代方案？",
        f"{name} 的核心指标怎么采集？上线前后的基线和对照组是什么？",
        f"{name} 出过哪些故障或边界问题？你怎么排查、恢复和复盘？",
    ]
    if contributions:
        questions.insert(0, f"你写到「{contributions[0]}」，具体设计、编码、联调和上线各做了什么？")
    if metrics:
        questions.insert(0, f"你写到「{metrics[0]}」，数据来源和统计口径是什么？")
    if vague_claims:
        questions.insert(0, f"你写到「{vague_claims[0]}」，能不能用可验证的事实替代这个表述？")
    if tech_choices:
        questions.insert(0, f"你写到「{tech_choices[0]}」，为什么这个方案比替代方案更合适？")
    if incidents:
        questions.insert(0, f"你写到「{incidents[0]}」，故障根因和长期改进是什么？")
    return _dedupe(questions)[:6]


def _extract_risks(
    text: str,
    tech_stack: list[str],
    projects: list[str],
    vague_claims: list[str],
    contributions: list[str],
) -> list[str]:
    risks = []
    if len(text) < 120:
        risks.append("简历内容偏短，项目深挖问题会缺少上下文。")
    if not tech_stack:
        risks.append("未识别到明确技术栈，建议补充语言、框架、数据库或工具。")
    if not projects:
        risks.append("未识别到明确项目名称，建议用项目名 + 背景 + 个人贡献组织。")
    if not re.search(r"\d+%|\d+ms|\d+秒|\d+万|\d+QPS|\d+qps", text):
        risks.append("缺少可量化结果，真实面试中容易被追问效果如何证明。")
    if vague_claims:
        risks.append("存在较模糊或容易被质疑的表述，需要补事实、口径和证据。")
    if projects and not contributions:
        risks.append("识别到项目但个人贡献不够明确，简历拷打时容易被追问“你到底做了什么”。")
    return risks


def _unique_matches(text: str, patterns: list[str], limit: int) -> list[str]:
    items: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            item = match.group(0).strip(" ，。；;")
            if item and item not in items:
                items.append(item)
    return items[:limit]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _shorten(text: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."
