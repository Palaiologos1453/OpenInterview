from __future__ import annotations

from contextlib import contextmanager
from threading import Lock
from threading import RLock
from typing import Protocol

from ..catalog import get_catalog
from ..interview_engine import CampusInterviewEngine, InterviewConfig, InterviewSession, Turn
from ..storage import Storage


class SessionStore(Protocol):
    def save(self, session: InterviewSession) -> None:
        ...

    def get(self, session_id: str) -> InterviewSession | None:
        ...

    def delete(self, session_id: str) -> None:
        ...

    def clear(self) -> None:
        ...

    def contains(self, session_id: str) -> bool:
        ...


class SQLiteBackedSessionStore:
    """Process-local hot cache with SQLite restore.

    The interface is intentionally small so Redis/Postgres implementations can
    replace the hot cache for multi-instance deployments without changing API
    handlers.
    """

    def __init__(self, *, storage: Storage, engine: CampusInterviewEngine):
        self.storage = storage
        self.engine = engine
        self._sessions: dict[str, InterviewSession] = {}
        self._lock = Lock()
        self._session_locks: dict[str, RLock] = {}

    def save(self, session: InterviewSession) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

    def get(self, session_id: str) -> InterviewSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
        if session:
            return session
        restored = self._restore(session_id)
        if restored:
            self.save(restored)
        return restored

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()

    def contains(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions

    @contextmanager
    def session_lock(self, session_id: str):
        with self._lock:
            lock = self._session_locks.setdefault(session_id, RLock())
        with lock:
            yield

    def _restore(self, session_id: str) -> InterviewSession | None:
        record = self.storage.get_interview(session_id)
        if not record:
            return None
        config = dict(record["config"])
        if config.get("direction_id") not in _valid_direction_ids():
            config["direction_id"] = "backend"
        config.setdefault("interviewer_style_id", "small_company_basic")
        provider_config = config.get("provider_config")
        if isinstance(provider_config, dict):
            redacted = False
            for group in provider_config.values():
                if isinstance(group, dict) and group.get("api_key") == "***":
                    group["api_key"] = ""
                    redacted = True
            if redacted:
                llm = provider_config.get("llm")
                if isinstance(llm, dict):
                    llm["provider"] = "mock"
        try:
            interview_config = InterviewConfig(**config)
        except TypeError:
            return None
        session = InterviewSession(config=interview_config, session_id=session_id)
        for item in self.storage.get_interview_turns(session_id):
            session.history.append(
                Turn(
                    question=item["question"],
                    answer=item["answer"],
                    feedback=item["feedback"],
                    tags=item["tags"],
                    score=item["score"],
                    question_meta=item.get("question_meta"),
                )
            )
        session.turn_index = len(session.history)
        session.current_question = self.engine._select_question(session, step=session.turn_index)
        return session


def _valid_direction_ids() -> set[str]:
    return {item["id"] for item in get_catalog()["directions"]}
