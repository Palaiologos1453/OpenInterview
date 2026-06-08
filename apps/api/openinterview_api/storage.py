from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .settings import database_path


SCHEMA = """
PRAGMA journal_mode = WAL;

DROP TABLE IF EXISTS coding_submissions;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS interviews (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    config_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    report_json TEXT
);

CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    feedback TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    question_meta_json TEXT,
    score REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interview_id TEXT,
    text TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    interview_id TEXT,
    event_name TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_items (
    id TEXT PRIMARY KEY,
    interview_id TEXT,
    question_id TEXT,
    topic TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    score REAL NOT NULL,
    gaps_json TEXT NOT NULL,
    rewrite_advice_json TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

"""

SCHEMA_VERSION = 3

MIGRATIONS = [
    (1, "add_turn_question_meta", "ALTER TABLE turns ADD COLUMN question_meta_json TEXT"),
    (2, "add_schema_migrations_table", None),
    (3, "add_review_items_table", None),
]


class Storage:
    def __init__(self, path: Path | None = None):
        self.path = path or database_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.executescript(SCHEMA)
            self._apply_migrations(connection)

    def _apply_migrations(self, connection: sqlite3.Connection) -> None:
        _ensure_column(connection, "turns", "question_meta_json", "TEXT")
        _ensure_review_items_table(connection)
        applied = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for version, name, sql in MIGRATIONS:
            if version in applied:
                continue
            if sql and not _migration_already_applied(connection, sql):
                connection.execute(sql)
            connection.execute(
                """
                INSERT INTO schema_migrations (version, name, applied_at)
                VALUES (?, ?, ?)
                """,
                (version, name, utc_now()),
            )

    def create_user(self, user_id: str, display_name: str, token_hash: str) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO users (id, display_name, token_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, display_name, token_hash, now),
            )

    def get_user_by_id(self, user_id: str) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def get_interview(self, interview_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id, user_id, config_json, status, created_at, updated_at, report_json
                FROM interviews
                WHERE id = ?
                """,
                (interview_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "config": json.loads(row["config_json"]),
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "report": json.loads(row["report_json"]) if row["report_json"] else None,
        }

    def create_interview(self, interview_id: str, config: dict, user_id: str | None = None) -> None:
        now = utc_now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO interviews (id, user_id, config_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (interview_id, user_id, json.dumps(config, ensure_ascii=False), "active", now, now),
            )

    def save_turn(
        self,
        interview_id: str,
        *,
        turn_index: int,
        question: str,
        answer: str,
        feedback: str,
        tags: list[str],
        score: float,
        question_meta: dict | None = None,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO turns (
                    interview_id, turn_index, question, answer, feedback, tags_json,
                    question_meta_json, score, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interview_id,
                    turn_index,
                    question,
                    answer,
                    feedback,
                    json.dumps(tags, ensure_ascii=False),
                    json.dumps(question_meta, ensure_ascii=False) if question_meta else None,
                    score,
                    utc_now(),
                ),
            )
            connection.execute(
                "UPDATE interviews SET updated_at = ? WHERE id = ?",
                (utc_now(), interview_id),
            )

    def save_report(self, interview_id: str, report: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE interviews SET report_json = ?, status = ?, updated_at = ? WHERE id = ?
                """,
                (json.dumps(report, ensure_ascii=False), "reported", utc_now(), interview_id),
            )

    def save_trace(self, trace: dict, interview_id: str | None = None) -> None:
        with self.connect() as connection:
            for event in trace.get("events", []):
                connection.execute(
                    """
                    INSERT INTO traces (
                        trace_id, interview_id, event_name, duration_ms, metadata_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace["trace_id"],
                        interview_id,
                        event["name"],
                        event["duration_ms"],
                        json.dumps(event.get("metadata") or {}, ensure_ascii=False),
                        utc_now(),
                    ),
                )

    def save_transcript(self, text: str, *, source: str, interview_id: str | None = None) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO transcripts (interview_id, text, source, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (interview_id, text, source, utc_now()),
            )

    def list_interviews(self, limit: int = 50) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, user_id, config_json, status, created_at, updated_at, report_json
                FROM interviews
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "user_id": row["user_id"],
                "config": json.loads(row["config_json"]),
                "status": row["status"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "has_report": row["report_json"] is not None,
            }
            for row in rows
        ]

    def export_interviews(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": utc_now(),
            "interviews": self.list_interviews(limit=100000),
            "turns": self._all_turns(),
            "transcripts": self._all_rows(
                """
                SELECT id, interview_id, text, source, created_at
                FROM transcripts
                ORDER BY created_at ASC
                """,
                json_columns=(),
            ),
            "traces": self._all_rows(
                """
                SELECT id, trace_id, interview_id, event_name, duration_ms, metadata_json, created_at
                FROM traces
                ORDER BY created_at ASC
                """,
                json_columns=("metadata_json",),
            ),
            "review_items": self.list_review_items(limit=100000),
        }

    def _all_turns(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, interview_id, turn_index, question, answer, feedback, tags_json,
                       question_meta_json, score, created_at
                FROM turns
                ORDER BY interview_id ASC, turn_index ASC
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "interview_id": row["interview_id"],
                "turn_index": row["turn_index"],
                "question": row["question"],
                "answer": row["answer"],
                "feedback": row["feedback"],
                "tags": json.loads(row["tags_json"]),
                "question_meta": json.loads(row["question_meta_json"]) if row["question_meta_json"] else None,
                "score": row["score"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def _all_rows(self, query: str, *, json_columns: tuple[str, ...]) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(query).fetchall()
        items: list[dict] = []
        for row in rows:
            item = dict(row)
            for column in json_columns:
                item[column.removesuffix("_json")] = json.loads(item.pop(column))
            items.append(item)
        return items

    def get_interview_turns(self, interview_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT turn_index, question, answer, feedback, tags_json,
                       question_meta_json, score, created_at
                FROM turns
                WHERE interview_id = ?
                ORDER BY turn_index ASC
                """,
                (interview_id,),
            ).fetchall()
        return [
            {
                "turn_index": row["turn_index"],
                "question": row["question"],
                "answer": row["answer"],
                "feedback": row["feedback"],
                "tags": json.loads(row["tags_json"]),
                "question_meta": json.loads(row["question_meta_json"]) if row["question_meta_json"] else None,
                "score": row["score"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def delete_interview(self, interview_id: str) -> bool:
        with self.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM interviews WHERE id = ?",
                (interview_id,),
            ).fetchone()
            if not exists:
                return False
            for table in ("turns", "transcripts", "traces"):
                connection.execute(f"DELETE FROM {table} WHERE interview_id = ?", (interview_id,))
            connection.execute("DELETE FROM review_items WHERE interview_id = ?", (interview_id,))
            connection.execute("DELETE FROM interviews WHERE id = ?", (interview_id,))
            return True

    def clear_interviews(self) -> int:
        with self.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM interviews").fetchone()[0]
            for table in ("turns", "transcripts", "traces", "review_items", "interviews"):
                connection.execute(f"DELETE FROM {table}")
            return int(count)

    def upsert_review_item(self, item: dict) -> None:
        now = utc_now()
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT attempts_json, status, created_at FROM review_items WHERE id = ?",
                (item["id"],),
            ).fetchone()
            attempts = list(item.get("attempts") or [])
            status = item.get("status") or "todo"
            created_at = now
            if existing:
                old_attempts = json.loads(existing["attempts_json"] or "[]")
                attempts = old_attempts + attempts
                status = existing["status"] if item.get("preserve_status", True) else status
                created_at = existing["created_at"]
            connection.execute(
                """
                INSERT OR REPLACE INTO review_items (
                    id, interview_id, question_id, topic, question, answer, score,
                    gaps_json, rewrite_advice_json, status, attempts_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item["id"],
                    item.get("interview_id"),
                    item.get("question_id"),
                    item.get("topic") or "interview",
                    item.get("question") or "",
                    item.get("answer") or "",
                    float(item.get("score") or 0),
                    json.dumps(item.get("gaps") or [], ensure_ascii=False),
                    json.dumps(item.get("rewrite_advice") or [], ensure_ascii=False),
                    status,
                    json.dumps(attempts, ensure_ascii=False),
                    created_at,
                    now,
                ),
            )

    def list_review_items(self, limit: int = 100, status: str | None = None) -> list[dict]:
        query = """
            SELECT id, interview_id, question_id, topic, question, answer, score,
                   gaps_json, rewrite_advice_json, status, attempts_json, created_at, updated_at
            FROM review_items
        """
        params: tuple[object, ...] = ()
        if status:
            query += " WHERE status = ?"
            params = (status,)
        query += " ORDER BY updated_at DESC LIMIT ?"
        params = (*params, limit)
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_review_item_from_row(row) for row in rows]

    def update_review_item_status(self, item_id: str, status: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE review_items SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), item_id),
            )
            return cursor.rowcount > 0

    def delete_review_item(self, item_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM review_items WHERE id = ?", (item_id,))
            return cursor.rowcount > 0

    def clear_review_items(self) -> int:
        with self.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM review_items").fetchone()[0]
            connection.execute("DELETE FROM review_items")
            return int(count)

    def utc_timestamp_for_filename(self) -> str:
        return utc_timestamp_for_filename()

    def metrics(self) -> dict:
        with self.connect() as connection:
            counts = {
                "interviews": connection.execute("SELECT COUNT(*) FROM interviews").fetchone()[0],
                "turns": connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0],
                "transcripts": connection.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0],
                "traces": connection.execute("SELECT COUNT(*) FROM traces").fetchone()[0],
            }
            latency_rows = connection.execute(
                """
                SELECT event_name, COUNT(*) AS count, AVG(duration_ms) AS avg_ms, MAX(duration_ms) AS max_ms
                FROM traces
                GROUP BY event_name
                ORDER BY event_name
                """
            ).fetchall()
        return {
            "counts": counts,
            "latency": [
                {
                    "event_name": row["event_name"],
                    "count": row["count"],
                    "avg_ms": round(row["avg_ms"] or 0, 2),
                    "max_ms": round(row["max_ms"] or 0, 2),
                }
                for row in latency_rows
            ],
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_timestamp_for_filename() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def _migration_already_applied(connection: sqlite3.Connection, sql: str) -> bool:
    normalized = sql.strip().upper()
    if not normalized.startswith("ALTER TABLE") or "ADD COLUMN" not in normalized:
        return False
    parts = sql.split()
    table = parts[2]
    column = parts[5]
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    return column in columns


def _ensure_review_items_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS review_items (
            id TEXT PRIMARY KEY,
            interview_id TEXT,
            question_id TEXT,
            topic TEXT NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            score REAL NOT NULL,
            gaps_json TEXT NOT NULL,
            rewrite_advice_json TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def _review_item_from_row(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "interview_id": row["interview_id"],
        "question_id": row["question_id"],
        "topic": row["topic"],
        "question": row["question"],
        "answer": row["answer"],
        "score": row["score"],
        "gaps": json.loads(row["gaps_json"]),
        "rewrite_advice": json.loads(row["rewrite_advice_json"]),
        "status": row["status"],
        "attempts": json.loads(row["attempts_json"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
