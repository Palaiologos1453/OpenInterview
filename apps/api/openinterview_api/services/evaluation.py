from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import mean
import json

import yaml

from ..interview_engine import CampusInterviewEngine, InterviewConfig, InterviewSession


DEFAULT_EVAL_SEED_PATH = Path(__file__).resolve().parents[2] / "eval" / "scoring_seed.yaml"
SCORE_TOLERANCE = 12.0


@dataclass
class EvaluationCase:
    id: str
    direction_id: str
    difficulty_id: str
    interviewer_style_id: str
    phase: str
    question: str
    question_meta: dict
    answer: str
    expected_score: float
    expected_gaps: list[str]
    note: str = ""


def expand_seed_cases(path: Path = DEFAULT_EVAL_SEED_PATH) -> list[EvaluationCase]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases: list[EvaluationCase] = []
    engine = CampusInterviewEngine()
    for question in data.get("questions", []):
        base_id = str(question["id"])
        rubrics = list(question.get("rubric") or [])
        rubric_labels = [engine._rubric_label(str(item)) for item in rubrics]
        question_meta = dict(question.get("question_meta") or {})
        question_meta.setdefault("phase", question.get("phase") or "fundamentals")
        question_meta.setdefault("rubric", rubrics)
        answer_profiles = question.get("answers") or data.get("answer_profiles") or []
        for answer in answer_profiles:
            expected_gaps = _expected_gaps(answer, rubric_labels)
            cases.append(
                EvaluationCase(
                    id=f"{base_id}-{answer['id']}",
                    direction_id=str(question.get("direction_id") or "backend"),
                    difficulty_id=str(question.get("difficulty_id") or "campus"),
                    interviewer_style_id=str(question.get("interviewer_style_id") or "small_company_basic"),
                    phase=str(question.get("phase") or "fundamentals"),
                    question=str(question["prompt"]),
                    question_meta=dict(question_meta),
                    answer=_render_text(str(answer["text"]), rubric_labels, question),
                    expected_score=float(answer["score"]),
                    expected_gaps=expected_gaps,
                    note=str(answer.get("note") or ""),
                )
            )
    return cases


def evaluate_scoring_cases(cases: list[EvaluationCase] | None = None) -> dict:
    engine = CampusInterviewEngine()
    evaluated = [_evaluate_case(engine, case) for case in (cases or expand_seed_cases())]
    if not evaluated:
        return {
            "case_count": 0,
            "score_mae": 0,
            "within_tolerance_rate": 0,
            "gap_precision": 0,
            "gap_recall": 0,
            "misjudgments": [],
            "cases": [],
        }

    score_errors = [abs(item["actual_score"] - item["expected_score"]) for item in evaluated]
    within_tolerance = [item for item in evaluated if item["score_error"] <= SCORE_TOLERANCE]
    gap_precision_values = [item["gap_precision"] for item in evaluated if item["expected_gaps"] or item["actual_gaps"]]
    gap_recall_values = [item["gap_recall"] for item in evaluated if item["expected_gaps"] or item["actual_gaps"]]
    misjudgments = [
        item
        for item in evaluated
        if item["score_error"] > SCORE_TOLERANCE or item["gap_recall"] < 0.6
    ]
    misjudgments = sorted(misjudgments, key=lambda item: (item["score_error"], 1 - item["gap_recall"]), reverse=True)
    return {
        "case_count": len(evaluated),
        "score_mae": round(mean(score_errors), 2),
        "within_tolerance_rate": round(len(within_tolerance) / len(evaluated), 3),
        "gap_precision": round(mean(gap_precision_values or [1.0]), 3),
        "gap_recall": round(mean(gap_recall_values or [1.0]), 3),
        "misjudgment_count": len(misjudgments),
        "misjudgments": misjudgments[:15],
        "cases": evaluated,
    }


def write_evaluation_report(output_path: Path, result: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() == ".json":
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return
    lines = [
        "# OpenInterview Scoring Evaluation",
        "",
        f"- Cases: {result['case_count']}",
        f"- Score MAE: {result['score_mae']}",
        f"- Within +/-{int(SCORE_TOLERANCE)} rate: {result['within_tolerance_rate']}",
        f"- Gap precision: {result['gap_precision']}",
        f"- Gap recall: {result['gap_recall']}",
        f"- Misjudgments: {result.get('misjudgment_count', 0)}",
        "",
        "## Top Misjudgments",
        "",
    ]
    for item in result.get("misjudgments", []):
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"- Expected score: {item['expected_score']}",
                f"- Actual score: {item['actual_score']}",
                f"- Score error: {item['score_error']}",
                f"- Expected gaps: {', '.join(item['expected_gaps']) or 'none'}",
                f"- Actual gaps: {', '.join(item['actual_gaps']) or 'none'}",
                f"- Note: {item.get('note') or 'none'}",
                "",
            ]
        )
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _evaluate_case(engine: CampusInterviewEngine, case: EvaluationCase) -> dict:
    session = InterviewSession(
        config=InterviewConfig(
            direction_id=case.direction_id,
            difficulty_id=case.difficulty_id,
            mode_id=_mode_for_phase(case.phase),
            interviewer_style_id=case.interviewer_style_id,
            provider_config={"llm": {"provider": "mock"}, "asr": {"provider": "browser"}, "tts": {"provider": "browser"}},
        ),
        current_question=case.question,
        current_question_meta=case.question_meta,
    )
    feedback, actual_score = engine._feedback(session, case.answer)
    actual_hits, actual_gaps = engine._rubric_coverage(case.answer, case.question_meta)
    expected_gap_set = set(case.expected_gaps)
    actual_gap_set = set(actual_gaps)
    matched_gaps = expected_gap_set & actual_gap_set
    precision = len(matched_gaps) / len(actual_gap_set) if actual_gap_set else (1.0 if not expected_gap_set else 0.0)
    recall = len(matched_gaps) / len(expected_gap_set) if expected_gap_set else (1.0 if not actual_gap_set else 0.0)
    score_error = round(abs(actual_score - case.expected_score), 2)
    return {
        "id": case.id,
        "direction_id": case.direction_id,
        "phase": case.phase,
        "question": case.question,
        "expected_score": case.expected_score,
        "actual_score": actual_score,
        "score_error": score_error,
        "expected_gaps": case.expected_gaps,
        "actual_gaps": actual_gaps,
        "actual_hits": actual_hits,
        "gap_precision": round(precision, 3),
        "gap_recall": round(recall, 3),
        "feedback": feedback,
        "note": case.note,
    }


def _mode_for_phase(phase: str) -> str:
    if phase == "project":
        return "project_deep_dive"
    if phase == "system_design":
        return "system_design_intro"
    return "fundamentals"


def _expected_gaps(answer: dict, rubric_labels: list[str]) -> list[str]:
    if isinstance(answer.get("gaps"), list):
        return [str(item) for item in answer.get("gaps", [])]
    missing = {
        int(item)
        for item in answer.get("missing_rubric_indexes", [])
        if isinstance(item, int) or str(item).isdigit()
    }
    return [label for index, label in enumerate(rubric_labels) if index in missing]


def _render_text(template: str, rubric_labels: list[str], question: dict) -> str:
    values = {
        "prompt": str(question.get("prompt") or ""),
        "topic": str((question.get("question_meta") or {}).get("topic") or question.get("phase") or "interview"),
    }
    for index, label in enumerate(rubric_labels):
        values[f"rubric_{index}"] = label
    return template.format_map(_SafeFormat(values))


class _SafeFormat(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
