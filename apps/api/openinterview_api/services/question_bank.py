from __future__ import annotations

from pathlib import Path
from functools import lru_cache

import yaml


class QuestionBank:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(__file__).resolve().parents[1] / "questions"

    @lru_cache(maxsize=32)
    def list_questions(self, direction_id: str | None = None) -> tuple[dict, ...]:
        questions: list[dict] = []
        for path in sorted(self.directory.glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for item in data.get("questions", []):
                item = dict(item)
                item.setdefault("source_file", path.name)
                questions.append(item)
        if direction_id:
            questions = [
                item for item in questions
                if direction_id in item.get("directions", []) or "general" in item.get("directions", [])
            ]
        return tuple(questions)

    def get_question(self, question_id: str) -> dict | None:
        for question in self.list_questions():
            if question.get("id") == question_id:
                return question
        return None


@lru_cache(maxsize=1)
def default_question_bank() -> QuestionBank:
    return QuestionBank()
