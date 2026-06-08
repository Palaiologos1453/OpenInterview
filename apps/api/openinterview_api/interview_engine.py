from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from uuid import uuid4

from .adapters.llm import build_llm_adapter, is_real_llm, llm_temperature
from .catalog import RUBRIC, find_difficulty, find_direction, find_mode
from .services.question_bank import default_question_bank
from .services.resume import analyze_resume


QUESTION_BANK = {
    "self_intro": [
        "请用 1 分钟做一个面向校招技术面试的自我介绍，重点放在技术栈、项目经历和你最想被追问的亮点上。",
    ],
    "project": [
        "选一个你最熟悉的项目，说明它解决了什么问题、你的职责是什么，以及最终效果如何衡量。",
        "这个项目里最难的技术点是什么？请讲清楚你当时有哪些方案、为什么选了最终方案。",
        "如果现在让你重做这个项目，你会优先改哪一处？为什么？",
    ],
    "fundamentals": {
        "backend": [
            "请解释数据库索引为什么能加速查询，并说明 B+ 树索引在范围查询上的优势。",
            "Redis 缓存和数据库之间可能出现哪些一致性问题？你会怎么降低风险？",
            "讲一下进程、线程和协程的区别，以及它们在后端服务中的适用场景。",
        ],
    },
    "system_design": [
        "如果让你设计一个校招刷题记录系统，你会如何拆分模块、设计核心表，并保证查询效率？",
        "如果要支持万人同时在线模拟面试，你会如何考虑会话状态、消息队列和服务扩缩容？",
    ],
    "closing": [
        "最后请你反问我一个问题，就像真实校招面试结尾一样。",
    ],
}


YAML_QUESTION_BANK = default_question_bank()


MODE_FLOW = {
    "comprehensive": [
        "self_intro",
        "project",
        "fundamentals",
        "system_design",
        "fundamentals",
        "closing",
    ],
    "fundamentals": ["fundamentals", "fundamentals", "fundamentals", "closing"],
    "project_deep_dive": ["project", "project", "project", "project", "closing"],
    "system_design_intro": ["project", "system_design", "system_design", "fundamentals", "closing"],
}


@dataclass
class InterviewConfig:
    direction_id: str
    difficulty_id: str
    mode_id: str = "comprehensive"
    candidate_name: str | None = None
    resume_text: str | None = None
    duration_minutes: int = 30
    language: str = "zh-CN"
    provider_config: dict | None = None


@dataclass
class Turn:
    question: str
    answer: str
    feedback: str
    tags: list[str]
    score: float
    question_meta: dict | None = None


@dataclass
class InterviewSession:
    config: InterviewConfig
    session_id: str = field(default_factory=lambda: str(uuid4()))
    turn_index: int = 0
    current_question: str = ""
    current_question_meta: dict | None = None
    history: list[Turn] = field(default_factory=list)
    provider_notice: str | None = None

    @property
    def direction(self) -> dict:
        return find_direction(self.config.direction_id)

    @property
    def difficulty(self) -> dict:
        return find_difficulty(self.config.difficulty_id)

    @property
    def mode(self) -> dict:
        return find_mode(self.config.mode_id)


class CampusInterviewEngine:
    """Deterministic MVP engine.

    The production path will replace question and feedback generation with LLM
    adapters, while keeping this engine as the auditable fallback and test oracle.
    """

    def start(self, config: InterviewConfig) -> dict:
        find_direction(config.direction_id)
        find_difficulty(config.difficulty_id)
        find_mode(config.mode_id)
        self._validate_provider_config(config)

        session = InterviewSession(config=config)
        session.current_question = self._select_question(session, step=0)
        opening = self._opening_message(session)
        return {
            "session": session,
            "payload": {
                "session_id": session.session_id,
                "opening_message": opening,
                "next_question": session.current_question,
                "rubric": RUBRIC,
                "provider_notice": session.provider_notice,
            },
        }

    def answer(self, session: InterviewSession, answer: str) -> dict:
        cleaned = answer.strip()
        feedback, score = self._feedback(session, cleaned)
        tags = self._focus_tags(session)
        session.history.append(
            Turn(
                question=session.current_question,
                answer=cleaned,
                feedback=feedback,
                tags=tags,
                score=score,
                question_meta=session.current_question_meta,
            )
        )
        session.turn_index += 1
        session.current_question = self._select_question(session, step=session.turn_index)

        return {
            "session_id": session.session_id,
            "turn_index": session.turn_index,
            "interviewer_message": feedback,
            "next_question": session.current_question,
            "focus_tags": tags,
            "is_finished": self._is_finished(session),
            "provider_notice": session.provider_notice,
        }

    def report(self, session: InterviewSession) -> dict:
        scored_turns = [
            turn for turn in session.history
            if (turn.question_meta or {}).get("phase") != "closing"
        ]
        if not scored_turns:
            average_score = 0.0
        else:
            average_score = round(mean(turn.score for turn in scored_turns), 1)

        dimensions = self._dimension_scores(session)
        weak_dimensions = sorted(dimensions, key=lambda item: item["score"])[:2]
        strengths = self._strengths(session)
        improvements = self._question_improvements(session)
        improvements.extend(
            f"优先补强{item['name']}：{item['advice']}"
            for item in weak_dimensions
            if len(improvements) < 4
        )
        if not improvements:
            improvements = ["先完成一轮完整模拟，再生成更具体的复习建议。"]

        return {
            "session_id": session.session_id,
            "direction": session.direction["name"],
            "difficulty": session.difficulty["name"],
            "overall_score": average_score,
            "ai_summary": self._ai_report_summary(session, average_score)
            or self._local_report_summary(session, average_score),
            "dimensions": dimensions,
            "strengths": strengths,
            "improvements": improvements,
            "review_plan": self._review_plan(session),
            "practice_drills": self._practice_drills(session),
            "answer_guides": self._answer_guides(session),
            "study_guides": self._study_guides(session),
            "turns": [
                {
                    "question": turn.question,
                    "answer": turn.answer,
                    "feedback": turn.feedback,
                    "tags": turn.tags,
                    "score": turn.score,
                    "question_meta": turn.question_meta,
                    "rubric_hits": self._rubric_coverage(turn.answer, turn.question_meta)[0],
                    "rubric_gaps": self._rubric_coverage(turn.answer, turn.question_meta)[1],
                    "score_evidence": self._score_evidence(turn),
                    "rewrite_advice": self._rewrite_advice(turn),
                }
                for turn in session.history
            ],
        }

    def _opening_message(self, session: InterviewSession) -> str:
        name = session.config.candidate_name or "同学"
        return (
            f"{name}，你好。接下来是 {session.direction['name']} 方向的"
            f"{session.difficulty['name']}模拟面试。回答时请尽量按背景、方案、取舍、结果来组织。"
        )

    def _select_question(self, session: InterviewSession, step: int) -> str:
        flow = MODE_FLOW.get(session.config.mode_id, MODE_FLOW["comprehensive"])
        if step >= len(flow):
            session.current_question_meta = None
            return "本轮问题已经结束。你可以生成报告，或重新选择方向和难度开始下一轮。"

        phase = flow[step]
        followup = self._select_followup_question(session, phase)
        if followup:
            session.current_question_meta = followup["meta"]
            return followup["prompt"]

        if phase == "self_intro":
            session.current_question_meta = {
                "source": "builtin",
                "phase": phase,
                "tags": ["自我介绍", "岗位匹配", "技术亮点"],
            }
            return QUESTION_BANK["self_intro"][0]
        if phase == "project":
            generated = self._ai_question(session, phase, step)
            if generated:
                session.current_question_meta = {
                    "source": "llm",
                    "phase": phase,
                    "tags": self._default_phase_tags(session, phase),
                    "rubric": [
                        "是否讲清业务背景和目标",
                        "是否说明个人贡献和关键技术方案",
                        "是否给出指标结果、验证方式和复盘",
                    ],
                }
                return generated
            return self._select_project_question(session, step)
        if phase == "fundamentals":
            yaml_question = self._select_bank_question(session, phase, step)
            if yaml_question:
                return yaml_question
            generated = self._ai_question(session, phase, step)
            if generated:
                session.current_question_meta = {
                    "source": "llm",
                    "phase": phase,
                    "tags": self._default_phase_tags(session, phase),
                }
                return generated
            questions = QUESTION_BANK["fundamentals"].get(
                session.config.direction_id,
                QUESTION_BANK["fundamentals"]["backend"],
            )
            session.current_question_meta = {
                "source": "builtin",
                "phase": phase,
                "tags": session.direction["topics"][:3],
            }
            return questions[step % len(questions)]
        if phase == "system_design":
            yaml_question = self._select_bank_question(session, phase, step)
            if yaml_question:
                return yaml_question
            generated = self._ai_question(session, phase, step)
            if generated:
                session.current_question_meta = {
                    "source": "llm",
                    "phase": phase,
                    "tags": self._default_phase_tags(session, phase),
                }
                return generated
            session.current_question_meta = {
                "source": "builtin",
                "phase": phase,
                "tags": ["System Design", "需求澄清", "容量与稳定性"],
            }
            return QUESTION_BANK["system_design"][step % len(QUESTION_BANK["system_design"])]
        if phase == "closing":
            session.current_question_meta = {
                "source": "builtin",
                "phase": phase,
                "tags": ["反问", "沟通"],
            }
            return QUESTION_BANK["closing"][0]
        session.current_question_meta = None
        return QUESTION_BANK["self_intro"][0]

    def _select_bank_question(
        self,
        session: InterviewSession,
        phase: str,
        step: int,
    ) -> str | None:
        candidates = [
            item for item in YAML_QUESTION_BANK.list_questions(session.config.direction_id)
            if item.get("type") != "coding"
        ]
        if phase == "fundamentals":
            candidates = [
                item for item in candidates
                if item.get("type") == "fundamentals" or item.get("topic") in session.direction["topics"]
            ]
        elif phase == "system_design":
            scenario_topics = {
                "system-design",
                "distributed-system",
                "high-availability",
                "high-performance",
                "message-queue",
                "spring",
                "security",
            }
            candidates = [
                item for item in candidates
                if item.get("type") == "scenario" or item.get("topic") in scenario_topics
            ]
        else:
            return None

        if not candidates:
            return None

        candidates = self._rank_bank_questions(candidates, session)
        phase_offset = self._phase_offset(session, phase, step)
        question = candidates[phase_offset % len(candidates)]
        session.current_question_meta = self._question_meta(question, phase)
        return self._format_bank_prompt(question)

    def _question_meta(self, question: dict, phase: str) -> dict:
        return {
            "id": question.get("id"),
            "source": question.get("source") or question.get("source_file") or "question_bank",
            "source_path": question.get("source_path"),
            "phase": phase,
            "topic": question.get("topic"),
            "type": question.get("type"),
            "difficulty": question.get("difficulty"),
            "tags": list(question.get("tags") or []),
            "followups": list(question.get("followups") or []),
            "rubric": list(question.get("rubric") or []),
        }

    def _rank_bank_questions(self, questions: list[dict], session: InterviewSession) -> list[dict]:
        target = self._difficulty_rank(session.config.difficulty_id)

        def score(item: dict) -> tuple[int, str]:
            item_rank = self._difficulty_rank(str(item.get("difficulty") or "campus"))
            distance = abs(item_rank - target)
            too_hard_penalty = 1 if item_rank > target else 0
            return distance + too_hard_penalty, str(item.get("id") or "")

        return sorted(questions, key=score)

    def _difficulty_rank(self, difficulty_id: str) -> int:
        ranks = {
            "internship": 0,
            "campus": 1,
            "bigtech": 2,
            "top_tier": 3,
        }
        return ranks.get(difficulty_id, 1)

    def _phase_offset(self, session: InterviewSession, phase: str, step: int) -> int:
        flow = MODE_FLOW.get(session.config.mode_id, MODE_FLOW["comprehensive"])
        return flow[:step].count(phase)

    def _format_bank_prompt(self, question: dict) -> str:
        prompt = str(question.get("prompt") or "").strip()
        followups = [
            str(item).strip()
            for item in question.get("followups", [])
            if str(item).strip()
        ][:2]
        if not followups:
            return prompt
        return f"{prompt}\n追问方向：{'；'.join(followups)}"

    def _select_followup_question(self, session: InterviewSession, phase: str) -> dict | None:
        if phase not in {"fundamentals", "project", "system_design"} or not session.history:
            return None
        previous = session.history[-1]
        previous_meta = previous.question_meta or {}
        if previous_meta.get("type") == "followup":
            return None
        parent_id = previous_meta.get("parent_id") or previous_meta.get("id")
        if parent_id and any(
            (turn.question_meta or {}).get("type") == "followup"
            and (turn.question_meta or {}).get("parent_id") == parent_id
            for turn in session.history
        ):
            return None
        followups = [
            str(item).strip()
            for item in previous_meta.get("followups", [])
            if str(item).strip()
        ]
        gaps = self._rubric_coverage(previous.answer, previous_meta)[1]
        if not followups or (previous.score >= 72 and not gaps):
            return None

        if gaps:
            prompt = f"刚才这题你还没有展开“{gaps[0]}”。请继续补充：{followups[0]}"
        else:
            prompt = f"继续追问上一题：{followups[0]}"
        if len(followups) > 1:
            prompt = f"{prompt}\n如果能答上，再补充：{followups[1]}"

        meta = dict(previous_meta)
        meta["phase"] = phase
        meta["type"] = "followup"
        meta["parent_id"] = parent_id
        meta["rubric"] = [
            f"是否回答：{followups[0]}",
            f"是否补充：{followups[1]}",
        ] if len(followups) > 1 else [f"是否回答：{followups[0]}"]
        return {"prompt": prompt, "meta": meta}

    def _select_project_question(self, session: InterviewSession, step: int) -> str:
        resume = session.config.resume_text or ""
        resume_analysis = self._resume_analysis(session)
        project_cards = list(resume_analysis.get("project_cards") or [])
        card = project_cards[step % len(project_cards)] if project_cards else None
        session.current_question_meta = {
            "source": "builtin",
            "phase": "project",
            "tags": self._project_tags(session, card),
            "followups": self._project_followups(session, step),
            "rubric": [
                "是否讲清业务背景和目标",
                "是否说明个人贡献和关键技术方案",
                "是否给出指标结果、验证方式和复盘",
                "是否能解释技术选型依据、故障风险和项目真实性",
            ],
        }
        if card:
            card_name = card.get("name") or "这个项目"
            summary = card.get("summary") or ""
            if step == 0:
                return (
                    f"我把你的简历先拆成项目卡片，第一张是「{card_name}」。"
                    f"请用 2 分钟讲清它的背景、你的个人贡献、核心方案和结果。"
                    f"{' 简历片段：' + summary if summary else ''}"
                )
            prompt_pool = self._project_card_prompts(card, resume_analysis)
            return prompt_pool[step % len(prompt_pool)]
        if step == 0 and resume.strip():
            focus = "、".join(session.direction["project_focus"][:4])
            return (
                "我看到你提供了简历内容。请选其中最能体现岗位匹配度的项目，"
                f"重点讲 {focus}，并说明你的个人贡献。"
            )
        questions = QUESTION_BANK["project"]
        return questions[step % len(questions)]

    def _project_followups(self, session: InterviewSession, step: int) -> list[str]:
        focus = session.direction["project_focus"]
        resume_analysis = self._resume_analysis(session)
        targeted: list[str] = []
        for card in resume_analysis.get("project_cards") or []:
            targeted.extend(str(item) for item in card.get("followup_questions") or [])
        targeted.extend(str(item) for item in resume_analysis.get("metric_questions") or [])
        targeted.extend(str(item) for item in resume_analysis.get("tech_choice_questions") or [])
        targeted.extend(str(item) for item in resume_analysis.get("incident_questions") or [])
        targeted.extend(
            f"你简历里的「{item}」比较模糊，请用事实、指标或代码细节解释它到底代表什么。"
            for item in resume_analysis.get("vague_claims") or []
        )
        followups = [
            "你在这个项目中的个人贡献和不可替代部分是什么？请区分团队成果和你自己的工作。",
            f"围绕{focus[0]}和{focus[1]}，当时还有哪些备选方案？为什么没有选它们？",
            "这个项目上线或验收后，核心指标怎么变化？你如何证明变化来自你的方案？",
            f"如果面试官质疑{focus[2]}或{focus[3]}，你会怎么解释边界条件和风险兜底？",
            "项目中有没有线上故障、压测瓶颈或需求变更？你当时怎么定位、恢复和复盘？",
        ]
        followups = list(dict.fromkeys(targeted + followups))
        return followups[step % len(followups):] + followups[:step % len(followups)]

    def _resume_analysis(self, session: InterviewSession) -> dict:
        resume = (session.config.resume_text or "").strip()
        if not resume:
            return {}
        return analyze_resume(resume).as_dict()

    def _project_tags(self, session: InterviewSession, card: dict | None) -> list[str]:
        tags = list(session.direction["project_focus"][:3])
        if card:
            tags.extend(str(item) for item in card.get("tech_stack") or [])
            tags.insert(0, str(card.get("name") or "项目卡片"))
        return list(dict.fromkeys(tags))[:5]

    def _project_card_prompts(self, card: dict, resume_analysis: dict) -> list[str]:
        name = card.get("name") or "这个项目"
        contribution = self._first_text(card.get("contribution_signals")) or self._first_text(
            resume_analysis.get("contributions")
        )
        metric = self._first_text(card.get("metrics"))
        vague = self._first_text(card.get("vague_claims")) or self._first_text(resume_analysis.get("vague_claims"))
        choice = self._first_text(card.get("tech_choices"))
        incident = self._first_text(card.get("incident_signals"))
        return [
            (
                f"继续深挖「{name}」："
                f"{'你写到「' + contribution + '」，' if contribution else ''}"
                "请拆出你自己的设计、编码、联调、上线和复盘动作，哪些不是团队其他人完成的？"
            ),
            (
                f"「{name}」的技术选型依据是什么？"
                f"{'简历里相关表述是「' + choice + '」。' if choice else ''}"
                "当时至少有哪些替代方案，分别为什么没选？"
            ),
            (
                f"「{name}」的效果怎么证明？"
                f"{'你写到「' + metric + '」，' if metric else ''}"
                "请说明指标来源、统计口径、上线前基线、上线后对比和归因方式。"
            ),
            (
                f"「{name}」如果在真实线上环境出问题，最可能的故障点是什么？"
                f"{'你简历里提到「' + incident + '」，' if incident else ''}"
                "请讲一次排查、恢复、兜底和复盘改进。"
            ),
            (
                f"「{name}」里有没有包装过度或边界不清的表述？"
                f"{'比如「' + vague + '」。' if vague else ''}"
                "请把它改成面试官可验证的事实、证据和代码/数据细节。"
            ),
        ]

    def _first_text(self, items: object) -> str:
        if not isinstance(items, list):
            return ""
        for item in items:
            text = str(item).strip()
            if text:
                return text
        return ""

    def _feedback(self, session: InterviewSession, answer: str) -> tuple[str, float]:
        if not answer:
            return "这个回答为空。真实面试中至少需要先给出结论，再补充依据。", 25.0
        if self._current_phase(session) == "closing":
            return self._closing_feedback(answer), self._score_closing(answer)

        rubric_hits, rubric_gaps = self._rubric_coverage(answer, session.current_question_meta)
        score = self._score_answer(answer, session.difficulty["pressure"], rubric_hits)
        positive = "你的回答已经覆盖了一部分关键信息。"
        if len(answer) >= 120:
            positive = "你的回答信息量比较足，适合继续做细节追问。"
        if any(marker in answer for marker in ["首先", "第一", "背景", "方案", "结果", "复杂度"]):
            positive = "你的表达有一定结构，这在校招技术面里是加分项。"
        if rubric_hits:
            positive = f"你的回答已经覆盖：{'、'.join(rubric_hits[:2])}。"

        gap = self._gap_hint(answer, session, rubric_gaps)
        fallback = f"{positive}{gap}"
        generated = self._ai_feedback(session, answer, score, fallback)
        return generated or fallback, score

    def _score_answer(self, answer: str, pressure: int, rubric_hits: list[str] | None = None) -> float:
        length_score = min(len(answer) / 160 * 45, 45)
        structure_markers = ["首先", "其次", "最后", "背景", "方案", "结果", "复杂度", "边界"]
        structure_score = min(sum(marker in answer for marker in structure_markers) * 8, 25)
        technical_markers = [
            "索引",
            "缓存",
            "线程",
            "进程",
            "复杂度",
            "一致性",
            "事务",
            "性能",
            "延迟",
            "吞吐",
            "测试",
            "监控",
            "模型",
        ]
        technical_score = min(sum(marker in answer for marker in technical_markers) * 5, 25)
        rubric_score = min(len(rubric_hits or []) * 8, 20)
        pressure_penalty = max(pressure - 2, 0) * 3
        return round(
            max(
                30,
                min(
                    95,
                    20 + length_score + structure_score + technical_score + rubric_score - pressure_penalty,
                ),
            ),
            1,
        )

    def _closing_feedback(self, answer: str) -> str:
        if any(word in answer for word in ["团队", "培养", "成长", "代码", "业务", "技术栈", "owner", "ownership"]):
            return "这个反问能围绕团队协作或成长预期展开，真实面试里是加分项。可以再追问新人前三个月的产出标准。"
        return "反问已完成。建议把问题聚焦在团队技术栈、培养机制、代码质量要求或岗位职责上。"

    def _score_closing(self, answer: str) -> float:
        if len(answer.strip()) >= 20:
            return 75.0
        return 60.0

    def _gap_hint(
        self,
        answer: str,
        session: InterviewSession,
        rubric_gaps: list[str] | None = None,
    ) -> str:
        hints = []
        if rubric_gaps:
            hints.append(f"建议补充{rubric_gaps[0]}")
        if len(answer) < 80:
            hints.append("建议补充更具体的例子或技术细节")
        if "结果" not in answer and self._current_phase(session) == "project":
            hints.append("项目题最好量化结果或说明验证方式")
        if not any(word in answer for word in ["取舍", "为什么", "对比", "方案"]):
            hints.append("可以补充方案取舍，而不只是描述做了什么")
        if not hints:
            hints.append("下一步可以继续展开边界条件和失败场景")
        return " " + "；".join(hints) + "。"

    def _rubric_coverage(self, answer: str, question_meta: dict | None) -> tuple[list[str], list[str]]:
        rubrics = list((question_meta or {}).get("rubric") or [])
        if not rubrics:
            return [], []

        normalized_answer = answer.lower()
        followup_keywords = self._followup_keywords(question_meta or {})
        hits: list[str] = []
        gaps: list[str] = []
        for rubric in rubrics:
            label = self._rubric_label(str(rubric))
            keywords = self._rubric_keywords(str(rubric))
            if len(keywords) <= 3 or any(word in str(rubric) for word in ["场景", "举出", "方案"]):
                keywords += followup_keywords
            if keywords and any(keyword.lower() in normalized_answer for keyword in keywords):
                hits.append(label)
            else:
                gaps.append(label)
        return hits, gaps

    def _followup_keywords(self, question_meta: dict) -> list[str]:
        keywords: list[str] = []
        for followup in question_meta.get("followups", []):
            keywords.extend(self._rubric_keywords(str(followup)))
        return keywords[:10]

    def _rubric_label(self, rubric: str) -> str:
        text = rubric.strip().strip("。")
        for prefix in ("能说明", "能解释", "能讲清", "能区分", "能比较", "能指出", "能提出", "能覆盖", "是否"):
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        return text[:28]

    def _rubric_keywords(self, rubric: str) -> list[str]:
        separators = [
            "、",
            "，",
            "。",
            "；",
            "：",
            ":",
            "？",
            "?",
            " ",
            "/",
            "和",
            "与",
            "及",
            "以及",
            "或",
            "为什么",
            "如何",
            "什么",
        ]
        text = rubric
        for separator in separators:
            text = text.replace(separator, "|")
        keywords = [
            item.strip(" ：:，。；（）()")
            for item in text.split("|")
            if len(item.strip(" ：:，。；（）()")) >= 2
        ]
        stop_words = {
            "能说明",
            "能解释",
            "能讲清",
            "能区分",
            "能比较",
            "能指出",
            "能提出",
            "能覆盖",
            "是否",
            "关系",
            "场景",
            "方案",
            "问题",
            "影响",
        }
        return [item for item in keywords if item not in stop_words][:8]

    def _focus_tags(self, session: InterviewSession) -> list[str]:
        meta_tags = (session.current_question_meta or {}).get("tags") or []
        if meta_tags:
            return list(dict.fromkeys(str(tag) for tag in meta_tags))[:4]
        phase = self._current_phase(session)
        if phase == "fundamentals":
            return session.direction["topics"][:3]
        if phase == "project":
            return session.direction["project_focus"][:3]
        if phase == "system_design":
            return ["需求澄清", "模块拆分", "容量与稳定性"]
        return ["表达结构", "岗位匹配", "技术亮点"]

    def _default_phase_tags(self, session: InterviewSession, phase: str) -> list[str]:
        if phase == "fundamentals":
            return session.direction["topics"][:3]
        if phase == "project":
            return session.direction["project_focus"][:3]
        if phase == "system_design":
            return ["System Design", "需求澄清", "容量与稳定性"]
        return ["表达结构", "岗位匹配"]

    def _current_phase(self, session: InterviewSession) -> str:
        flow = MODE_FLOW.get(session.config.mode_id, MODE_FLOW["comprehensive"])
        if session.turn_index >= len(flow):
            return "closing"
        return flow[session.turn_index]

    def _is_finished(self, session: InterviewSession) -> bool:
        flow = MODE_FLOW.get(session.config.mode_id, MODE_FLOW["comprehensive"])
        return session.turn_index >= len(flow)

    def _dimension_scores(self, session: InterviewSession) -> list[dict]:
        base = mean([turn.score for turn in session.history] or [0])
        phase_counts = {
            "project_depth": sum("项目" in tag or "业务" in tag for turn in session.history for tag in turn.tags),
            "cs_fundamentals": sum(topic in tag for turn in session.history for tag in turn.tags for topic in session.direction["topics"]),
        }
        advice = {
            "cs_fundamentals": "按操作系统、计网、数据库、语言基础建立错题清单",
            "project_depth": "用 STAR + 技术取舍 + 指标结果重写项目讲稿",
            "communication": "练习结论先行，避免只堆砌术语",
            "role_fit": "把简历项目和目标岗位的核心能力重新对齐",
        }
        dimensions = []
        for item in RUBRIC:
            bonus = min(phase_counts.get(item["id"], 0) * 2, 8)
            dimensions.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "score": round(max(0, min(100, base + bonus)), 1),
                    "advice": advice[item["id"]],
                }
            )
        return dimensions

    def _strengths(self, session: InterviewSession) -> list[str]:
        if not session.history:
            return ["尚未完成回答，暂无法判断优势。"]
        strengths = []
        if any(len(turn.answer) > 120 for turn in session.history):
            strengths.append("部分回答信息量较充分，具备继续深挖的基础。")
        if any(any(marker in turn.answer for marker in ["首先", "第一", "背景", "方案"]) for turn in session.history):
            strengths.append("回答中出现结构化表达，适合进一步固化成面试模板。")
        covered_topics = {
            (turn.question_meta or {}).get("topic")
            for turn in session.history
            if turn.question_meta and turn.score >= 70
        }
        covered_topics.discard(None)
        if covered_topics:
            strengths.append(f"在 {self._join_items(sorted(covered_topics)[:3])} 等主题上已有可展开的基础。")
        if not strengths:
            strengths.append("已经完成基础模拟流程，下一步需要提高回答的具体性。")
        return strengths

    def _question_improvements(self, session: InterviewSession) -> list[str]:
        improvements: list[str] = []
        low_turns = sorted(session.history, key=lambda turn: turn.score)[:3]
        for turn in low_turns:
            gaps = self._rubric_coverage(turn.answer, turn.question_meta)[1]
            if not gaps:
                continue
            topic = (turn.question_meta or {}).get("topic") or "本题"
            improvements.append(f"{topic}：补充{gaps[0]}。")
        return improvements

    def _score_evidence(self, turn: Turn) -> list[str]:
        evidence: list[str] = []
        meta = turn.question_meta or {}
        hits, gaps = self._rubric_coverage(turn.answer, meta)
        if hits:
            evidence.append(f"已覆盖评分点：{self._join_items(hits[:3])}。")
        if gaps:
            evidence.append(f"缺失评分点：{self._join_items(gaps[:3])}。")
        if len(turn.answer) < 80 and meta.get("phase") != "closing":
            evidence.append("回答篇幅偏短，真实面试中难以支撑连续追问。")
        if meta.get("phase") == "project" and "结果" not in turn.answer:
            evidence.append("项目回答缺少结果、指标或验证方式。")
        if not any(word in turn.answer for word in ["取舍", "对比", "为什么", "边界", "风险"]):
            evidence.append("缺少方案取舍或边界条件说明。")
        if not evidence:
            evidence.append("回答覆盖了基础结构，后续重点是补更具体的工程细节。")
        return evidence[:5]

    def _rewrite_advice(self, turn: Turn) -> list[str]:
        meta = turn.question_meta or {}
        phase = meta.get("phase")
        gaps = self._rubric_coverage(turn.answer, meta)[1]
        focus = gaps[0] if gaps else "关键细节"
        if phase == "project":
            return [
                "用一句话说明业务目标和你负责的模块。",
                "把团队成果拆成你自己的设计、编码、联调、上线动作。",
                f"补充“{focus}”，并给出指标来源、基线和上线后对比。",
                "最后说明一次故障、风险兜底或复盘改进。",
            ]
        if phase == "system_design":
            return [
                "先澄清规模、读写比例、延迟和一致性要求。",
                "按模块、数据流、存储、缓存、队列拆解方案。",
                f"补充“{focus}”，说明容量估算、风险和验证方式。",
            ]
        if phase == "closing":
            return ["反问聚焦团队技术栈、培养机制、代码质量或岗位职责。"]
        return [
            "先给定义或结论，避免直接堆术语。",
            "解释底层机制和为什么这样设计。",
            f"补充“{focus}”，给出适用场景、边界条件和常见误区。",
            "落到 Java 后端项目里说明如何验证或排查。",
        ]

    def _join_items(self, items: list[str]) -> str:
        return "、".join(str(item) for item in items if item)

    def _local_report_summary(self, session: InterviewSession, average_score: float) -> str:
        if not session.history:
            return "本轮还没有有效回答，先完成一轮面试后再复盘。"
        weak_turn = min(session.history, key=lambda turn: turn.score)
        weak_topic = (weak_turn.question_meta or {}).get("topic") or "当前薄弱题"
        gaps = self._rubric_coverage(weak_turn.answer, weak_turn.question_meta)[1]
        gap_text = gaps[0] if gaps else "回答具体性和边界条件"
        return (
            f"本轮平均分 {average_score}/100。整体已能进入真实面试流程，"
            f"下一步优先补强 {weak_topic} 的{gap_text}，并把回答固定成结论、依据、取舍、验证四段。"
        )

    def _practice_drills(self, session: InterviewSession) -> list[dict]:
        drills: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for turn in sorted(session.history, key=lambda item: item.score):
            meta = turn.question_meta or {}
            gaps = self._rubric_coverage(turn.answer, meta)[1]
            if not gaps:
                continue
            topic = meta.get("topic") or "interview"
            parent_id = meta.get("parent_id") or meta.get("id")
            key = (str(parent_id or turn.question), str(gaps[0]))
            if key in seen:
                continue
            seen.add(key)
            drills.append(
                {
                    "topic": topic,
                    "source_question_id": parent_id,
                    "focus": gaps[0],
                    "prompt": self._practice_prompt(turn, gaps[0]),
                    "target_structure": [
                        "先给结论",
                        "补关键原理或机制",
                        "给工程场景和取舍",
                        "说明验证或排查方法",
                    ],
                }
            )
            if len(drills) >= 5:
                break
        if drills:
            return drills

        return [
            {
                "topic": "communication",
                "source_question_id": None,
                "focus": "结构化表达",
                "prompt": "任选本轮一道题，用 90 秒重新回答，要求包含结论、原因、取舍和验证方式。",
                "target_structure": ["结论", "原因", "取舍", "验证"],
            }
        ]

    def _practice_prompt(self, turn: Turn, gap: str) -> str:
        question = turn.question.split("\n", 1)[0]
        return f"复练：重新回答「{question}」，这次必须补充“{gap}”，控制在 90 秒内。"

    def _answer_guides(self, session: InterviewSession) -> list[dict]:
        guides: list[dict] = []
        seen: set[str] = set()
        turns = [
            turn for turn in sorted(session.history, key=lambda item: item.score)
            if (turn.question_meta or {}).get("phase") != "closing"
        ]
        for turn in turns:
            meta = turn.question_meta or {}
            gaps = self._rubric_coverage(turn.answer, meta)[1]
            focus = gaps[0] if gaps else "回答结构和关键细节"
            parent_id = str(meta.get("parent_id") or meta.get("id") or turn.question)
            if parent_id in seen:
                continue
            seen.add(parent_id)
            guides.append(
                {
                    "topic": meta.get("topic") or meta.get("phase") or "interview",
                    "source_question_id": meta.get("parent_id") or meta.get("id"),
                    "question": turn.question.split("\n", 1)[0],
                    "focus": focus,
                    "structure": self._answer_structure(meta),
                    "example_answer": self._example_answer(turn, focus),
                }
            )
            if len(guides) >= 4:
                break
        if guides:
            return guides

        return [
            {
                "topic": "communication",
                "source_question_id": None,
                "question": "任选本轮一道题重新回答。",
                "focus": "结构化表达",
                "structure": ["先给直接结论", "解释核心依据", "补一个具体例子", "说明验证方式或边界条件"],
                "example_answer": (
                    "我会先给结论，再解释原因。这个问题的关键不只是记住概念，"
                    "还要说明它在真实项目中的适用边界。最后我会补充一个验证方法，"
                    "比如用指标、日志或压测结果证明方案有效。"
                ),
            }
        ]

    def _answer_structure(self, question_meta: dict) -> list[str]:
        phase = question_meta.get("phase")
        if phase == "project":
            return [
                "一句话说明项目目标和业务背景",
                "明确自己的职责和关键贡献",
                "讲清核心方案、备选方案和取舍原因",
                "给出量化结果、验证方式和复盘改进",
            ]
        if phase == "system_design":
            return [
                "先澄清需求、规模和约束",
                "拆核心模块和关键数据流",
                "说明存储、缓存、队列等取舍",
                "补充容量、故障、监控和验证方案",
            ]
        return [
            "先给定义或直接结论",
            "解释底层机制和关键原理",
            "对比适用场景、优缺点和边界",
            "结合工程例子说明排查或验证方式",
        ]

    def _example_answer(self, turn: Turn, focus: str) -> str:
        meta = turn.question_meta or {}
        phase = meta.get("phase")
        topic = meta.get("topic") or "这个点"
        if phase == "project":
            return (
                "可以这样答：这个项目的目标是解决一个明确的业务或效率问题。"
                "我负责其中的核心链路，包括方案设计、关键实现和上线验证。"
                "当时比较过至少两种方案，最终选择当前方案是因为它在复杂度、稳定性和交付成本之间更平衡。"
                f"针对“{focus}”，我会补充具体指标，例如延迟、错误率、吞吐或人工成本变化，并说明如何监控和复盘。"
            )
        if phase == "system_design":
            return (
                "可以这样答：我会先确认用户规模、读写比例、延迟目标和一致性要求。"
                "然后把系统拆成接入层、业务服务、存储层和异步任务。"
                "核心取舍要围绕容量、可用性和一致性展开，例如缓存是否需要失效策略、队列如何保证重试和幂等。"
                f"最后补上“{focus}”，用压测、监控指标和故障演练验证设计是否成立。"
            )
        return (
            f"可以这样答：{topic} 的核心先给结论，再解释为什么。"
            "例如先说明概念或机制，再讲它解决什么问题、会带来什么代价。"
            f"针对“{focus}”，需要补充适用场景、边界条件和常见误区。"
            "最后落到工程里，可以说如何通过日志、指标、实验或测试来验证自己的判断。"
        )

    def _study_guides(self, session: InterviewSession) -> list[dict]:
        guides: list[dict] = []
        seen: set[str] = set()
        turns = [
            turn for turn in sorted(session.history, key=lambda item: item.score)
            if (turn.question_meta or {}).get("phase") != "closing"
        ]
        for turn in turns:
            meta = turn.question_meta or {}
            source_key = str(meta.get("parent_id") or meta.get("id") or turn.question)
            if source_key in seen:
                continue
            seen.add(source_key)
            gaps = self._rubric_coverage(turn.answer, meta)[1]
            focus = gaps[0] if gaps else "回答结构和关键细节"
            guides.append(
                {
                    "topic": meta.get("topic") or meta.get("phase") or "interview",
                    "source_question_id": meta.get("parent_id") or meta.get("id"),
                    "question": turn.question.split("\n", 1)[0],
                    "focus": focus,
                    "related_knowledge": self._related_knowledge(meta, focus),
                    "reference_answer": self._reference_answer(turn, focus),
                    "common_mistakes": self._common_mistakes(meta, focus),
                    "interviewer_followups": self._interviewer_followups(meta, focus),
                    "low_score_answer": self._low_score_answer(meta, focus),
                    "high_score_answer": self._high_score_answer(meta, focus),
                }
            )
            if len(guides) >= 5:
                break

        if guides:
            return guides

        return [
            {
                "topic": "communication",
                "source_question_id": None,
                "question": "任选本轮一道题重新回答。",
                "focus": "结构化表达",
                "related_knowledge": ["结论先行", "STAR", "技术取舍", "验证方式"],
                "reference_answer": (
                    "先直接给结论，再解释关键依据；随后补一个项目或工程场景，"
                    "说明为什么选这个方案、有什么代价，最后用指标、日志、测试或压测结果验证。"
                ),
                "common_mistakes": ["只背概念，不说明场景。", "只说做了什么，不说明为什么。", "没有验证方式或量化结果。"],
                "interviewer_followups": ["这个结论在什么边界下不成立？", "如果线上指标变差，你会怎么验证原因？"],
                "low_score_answer": "这个我知道，大概就是按常规方案做，效果应该还可以。",
                "high_score_answer": (
                    "我的结论是先明确约束，再选方案。原因是不同场景下成本、稳定性和一致性要求不同。"
                    "我会给出备选方案对比，并用指标或实验说明最终方案是否有效。"
                ),
            }
        ]

    def _related_knowledge(self, question_meta: dict, focus: str) -> list[str]:
        items: list[str] = []
        for value in [
            question_meta.get("topic"),
            question_meta.get("difficulty"),
            focus,
            *list(question_meta.get("tags") or []),
        ]:
            if value:
                items.append(str(value))
        for rubric in question_meta.get("rubric") or []:
            label = self._rubric_label(str(rubric))
            if label:
                items.append(label)
        return list(dict.fromkeys(items))[:8]

    def _reference_answer(self, turn: Turn, focus: str) -> str:
        meta = turn.question_meta or {}
        phase = meta.get("phase")
        topic = meta.get("topic") or "本题"
        rubric_labels = [self._rubric_label(str(item)) for item in meta.get("rubric") or []]
        rubric_text = "、".join(label for label in rubric_labels if label) or focus

        if phase == "project":
            return (
                "参考结构：先用一句话说明项目背景和目标，再明确自己负责的模块、关键动作和交付边界。"
                "接着对比至少两个技术方案，解释选择依据和放弃原因。"
                f"围绕“{rubric_text}”补充核心实现、指标来源、上线验证、故障风险和复盘改进。"
            )
        if phase == "system_design":
            return (
                "参考结构：先澄清用户规模、读写比例、延迟目标、一致性和可用性要求。"
                "再拆模块、数据流和核心表，说明缓存、消息队列、存储、幂等和降级策略。"
                f"围绕“{rubric_text}”给出容量估算、故障场景、监控指标和验证方式。"
            )
        if phase == "self_intro":
            return (
                "参考结构：用 10 秒说明目标岗位和技术栈，用 30 秒讲最匹配的项目贡献，"
                "再用 15 秒补充可被追问的技术亮点，最后把话题引到自己最有把握的项目或知识点。"
            )
        return (
            f"参考结构：先给出 {topic} 的直接结论或定义，再解释底层机制和关键约束。"
            f"围绕“{rubric_text}”补齐适用场景、优缺点、边界条件和常见误区。"
            "最后落到 Java 后端工程里，说明如何通过日志、指标、测试、压测或代码设计验证。"
        )

    def _common_mistakes(self, question_meta: dict, focus: str) -> list[str]:
        phase = question_meta.get("phase")
        if phase == "project":
            return [
                "把团队成果说成个人成果，缺少自己的决策和实现细节。",
                "只说用了某个技术，不说明为什么选、替代方案是什么。",
                "指标没有来源，无法解释统计口径、基线和验证方式。",
                "不谈故障、风险和复盘，像包装过的项目陈述。",
            ]
        if phase == "system_design":
            return [
                "没有先澄清规模、读写比例、一致性和延迟目标。",
                "只画模块，不说明数据流、容量和故障处理。",
                "缓存、队列、分库分表等技术堆叠但缺少取舍依据。",
            ]
        if phase == "self_intro":
            return [
                "像背简历流水账，没有突出岗位匹配度。",
                "技术亮点过多过散，面试官不知道该追问哪里。",
                "没有把话题引向自己准备充分的项目。",
            ]
        return [
            "只背概念定义，不解释机制和适用边界。",
            f"没有展开“{focus}”。",
            "没有结合 Java 后端场景说明工程落地和验证方式。",
            "把相近概念混用，缺少对比和反例。",
        ]

    def _interviewer_followups(self, question_meta: dict, focus: str) -> list[str]:
        followups = [
            str(item).strip()
            for item in question_meta.get("followups", [])
            if str(item).strip()
        ]
        if followups:
            return followups[:5]
        phase = question_meta.get("phase")
        if phase == "project":
            return [
                "这个项目里哪些工作是你独立完成的？怎么证明？",
                "核心指标的统计口径、基线和数据来源是什么？",
                "如果当时的技术选型被质疑，你怎么解释取舍？",
                "上线后有没有故障或负反馈？你怎么复盘？",
            ]
        if phase == "system_design":
            return [
                "读写比例和容量扩大 10 倍后，瓶颈会在哪里？",
                "缓存和数据库不一致时怎么发现、恢复和兜底？",
                "你会监控哪些指标来证明设计有效？",
            ]
        return [
            f"请继续展开“{focus}”。",
            "这个结论在什么场景下不成立？",
            "如果线上出现相反现象，你会怎么排查？",
        ]

    def _low_score_answer(self, question_meta: dict, focus: str) -> str:
        phase = question_meta.get("phase")
        if phase == "project":
            return "我主要负责后端开发，用了一些缓存和数据库优化，最后项目效果还不错。"
        if phase == "system_design":
            return "我会用 Spring Boot 做服务，再加 Redis 和 MySQL，流量大了就加机器。"
        return f"这个问题大概就是{focus}，平时开发里会用到，按常规做就可以。"

    def _high_score_answer(self, question_meta: dict, focus: str) -> str:
        phase = question_meta.get("phase")
        if phase == "project":
            return (
                "我先说明项目目标和我的职责边界，再讲关键方案。"
                "当时比较过直接改 SQL、加缓存和异步化三种方案，最终按瓶颈和交付成本选择。"
                f"针对“{focus}”，我会给出指标口径、上线前后对比、异常兜底和复盘结论。"
            )
        if phase == "system_design":
            return (
                "我会先确认 QPS、数据量、读写比例、延迟目标和一致性要求。"
                "然后拆接入层、业务层、存储层和异步任务，分别说明缓存、队列、幂等和降级。"
                f"针对“{focus}”，补容量估算、风险点和用压测/监控验证的方案。"
            )
        topic = question_meta.get("topic") or "这个知识点"
        return (
            f"{topic} 我会先给结论，再解释机制。"
            f"重点补“{focus}”，包括适用场景、边界条件、和相近方案对比。"
            "最后结合 Java 后端场景说明排查或验证方法，比如日志、指标、单测、压测或线上监控。"
        )

    def _review_plan(self, session: InterviewSession) -> list[str]:
        drills = self._practice_drills(session)
        first_focus = drills[0]["focus"] if drills else "基础概念"
        topics = session.direction["topics"][:4]
        return [
            f"第 1 天：重答最低分题，重点补“{first_focus}”。",
            f"第 2 天：围绕 {', '.join(topics[:2])} 做 5 道追问，每题 90 秒内讲清。",
            "第 3 天：整理 2 个项目或场景题模板，必须包含约束、取舍、风险和验证方式。",
            "第 4 天：回放本轮报告中的逐题缺口，逐项录一版更完整回答。",
        ]

    def _ai_question(self, session: InterviewSession, phase: str, step: int) -> str | None:
        if not is_real_llm(session.config.provider_config):
            return None

        history = self._history_prompt(session)
        resume = (session.config.resume_text or "").strip()
        resume_hint = resume[:1200] if resume else "候选人未提供简历。"
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 OpenInterview 的计算机类校招技术面试官。"
                    "你必须贴近真实校招，问题要具体、可追问、可评分。"
                    "只输出一个中文问题，不要输出解释、编号或答案。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"方向：{session.direction['name']}。\n"
                    f"方向知识点：{', '.join(session.direction['topics'])}。\n"
                    f"难度：{session.difficulty['name']}，要求：{session.difficulty['expectation']}。\n"
                    f"模式：{session.mode['name']}。\n"
                    f"当前阶段：{phase}，第 {step + 1} 题。\n"
                    f"简历：{resume_hint}\n"
                    f"历史：{history}\n"
                    "请生成下一道面试题。项目题要能深挖个人贡献；系统设计或场景题要要求候选人说明约束、取舍和验证方式。"
                ),
            },
        ]
        return self._call_llm(session, messages)

    def _ai_feedback(
        self,
        session: InterviewSession,
        answer: str,
        score: float,
        fallback: str,
    ) -> str | None:
        if not is_real_llm(session.config.provider_config):
            return None

        messages = [
            {
                "role": "system",
                "content": (
                    "你是 OpenInterview 的校招面试评估器。"
                    "请输出中文反馈，不超过 180 字。先指出一个具体优点，再指出一个具体改进点。"
                    "不要泛泛鼓励，不要生成下一题。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"方向：{session.direction['name']}。\n"
                    f"难度：{session.difficulty['name']}。\n"
                    f"面试题：{session.current_question}\n"
                    f"候选人回答：{answer}\n"
                    f"规则评分：{score}/100。\n"
                    f"兜底反馈：{fallback}\n"
                    "请根据校招技术面标准给出反馈。"
                ),
            },
        ]
        return self._call_llm(session, messages)

    def _ai_report_summary(self, session: InterviewSession, average_score: float) -> str | None:
        if not session.history or not is_real_llm(session.config.provider_config):
            return None

        compact_turns = "\n".join(
            f"题：{turn.question}\n答：{turn.answer[:300]}\n分：{turn.score}"
            for turn in session.history[-6:]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是计算机校招模拟面试复盘教练。"
                    "请输出 120 字以内中文总结，必须包含整体判断和下一步复习重点。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"方向：{session.direction['name']}。\n"
                    f"难度：{session.difficulty['name']}。\n"
                    f"平均分：{average_score}/100。\n"
                    f"记录：\n{compact_turns}"
                ),
            },
        ]
        return self._call_llm(session, messages)

    def _call_llm(self, session: InterviewSession, messages: list[dict[str, str]]) -> str | None:
        try:
            adapter = build_llm_adapter(session.config.provider_config)
            text = adapter.complete(
                messages,
                temperature=llm_temperature(session.config.provider_config),
            )
        except Exception as exc:
            if is_real_llm(session.config.provider_config):
                raise RuntimeError(f"LLM provider failed: {exc}") from exc
            session.provider_notice = f"LLM provider failed, fallback to mock logic: {exc}"
            return None

        cleaned = text.strip()
        if not cleaned:
            session.provider_notice = "LLM provider returned empty text, fallback to mock logic."
            return None

        session.provider_notice = None
        return cleaned

    def _history_prompt(self, session: InterviewSession) -> str:
        if not session.history:
            return "暂无。"
        turns = []
        for index, turn in enumerate(session.history[-4:], start=1):
            turns.append(
                f"{index}. 问：{turn.question}\n答：{turn.answer[:240]}\n反馈：{turn.feedback[:160]}"
            )
        return "\n".join(turns)

    def _validate_provider_config(self, config: InterviewConfig) -> None:
        provider_config = config.provider_config or {}
        llm = provider_config.get("llm") or {}
        provider = (llm.get("provider") or "openai_compatible").strip().lower()
        if provider in {"openai", "openai_compatible", "compatible"}:
            missing = [
                name for name in ("api_base", "model", "api_key")
                if not str(llm.get(name) or "").strip()
            ]
            if missing:
                raise ValueError(
                    "LLM provider config is incomplete. "
                    f"Missing: {', '.join(missing)}. "
                    "Use provider=mock only for local development."
                )
