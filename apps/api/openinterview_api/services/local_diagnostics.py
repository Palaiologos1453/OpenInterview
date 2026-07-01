from __future__ import annotations

from pathlib import Path
import sqlite3

from ..settings import database_path, data_dir, project_root
from ..storage import SCHEMA_VERSION, Storage
from .evaluation import DEFAULT_EVAL_SEED_PATH, expand_seed_cases


def local_diagnostics_report(storage: Storage | None = None) -> dict:
    storage = storage or Storage()
    db_path = database_path()
    data_root = data_dir()
    checks = {
        "project_root": _path_check(project_root(), expect_dir=True),
        "data_dir": _writable_dir_check(data_root),
        "database": _database_check(db_path),
        "schema": _schema_check(db_path),
        "backup_export": _backup_export_check(storage),
        "scoring_eval_seed": _scoring_seed_check(),
    }
    return {
        "ok": all(item["ok"] for item in checks.values()),
        "scope": "local-first",
        "checks": checks,
        "recommendations": _recommendations(checks),
    }


def _path_check(path: Path, *, expect_dir: bool = False) -> dict:
    exists = path.exists()
    return {
        "ok": exists and (path.is_dir() if expect_dir else True),
        "path": str(path),
        "exists": exists,
        "is_dir": path.is_dir() if exists else False,
    }


def _writable_dir_check(path: Path) -> dict:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".openinterview-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return {"ok": True, "path": str(path), "writable": True}
    except Exception as exc:
        return {"ok": False, "path": str(path), "writable": False, "error": str(exc)}


def _database_check(path: Path) -> dict:
    if not path.exists():
        return {"ok": True, "path": str(path), "exists": False, "note": "Database will be created on first write."}
    connection = None
    try:
        connection = sqlite3.connect(path)
        result = connection.execute("PRAGMA integrity_check").fetchone()
        wal = connection.execute("PRAGMA journal_mode").fetchone()
        page_count = connection.execute("PRAGMA page_count").fetchone()
        page_size = connection.execute("PRAGMA page_size").fetchone()
        return {
            "ok": result and result[0] == "ok",
            "path": str(path),
            "exists": True,
            "integrity": result[0] if result else "unknown",
            "journal_mode": wal[0] if wal else "unknown",
            "size_bytes": path.stat().st_size,
            "page_count": page_count[0] if page_count else None,
            "page_size": page_size[0] if page_size else None,
        }
    except Exception as exc:
        return {"ok": False, "path": str(path), "exists": True, "error": str(exc)}
    finally:
        if connection:
            connection.close()


def _schema_check(path: Path) -> dict:
    if not path.exists():
        return {"ok": True, "expected_schema_version": SCHEMA_VERSION, "applied_versions": []}
    connection = None
    try:
        connection = sqlite3.connect(path)
        rows = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        versions = [int(row[0]) for row in rows]
        latest = max(versions or [0])
        return {
            "ok": latest >= SCHEMA_VERSION,
            "expected_schema_version": SCHEMA_VERSION,
            "latest_schema_version": latest,
            "applied_versions": versions,
        }
    except sqlite3.Error as exc:
        return {
            "ok": False,
            "expected_schema_version": SCHEMA_VERSION,
            "latest_schema_version": None,
            "error": str(exc),
        }
    finally:
        if connection:
            connection.close()


def _backup_export_check(storage: Storage) -> dict:
    try:
        exported = storage.export_interviews()
        return {
            "ok": True,
            "schema_version": exported.get("schema_version"),
            "interviews": len(exported.get("interviews") or []),
            "turns": len(exported.get("turns") or []),
            "review_items": len(exported.get("review_items") or []),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _scoring_seed_check() -> dict:
    try:
        cases = expand_seed_cases(DEFAULT_EVAL_SEED_PATH)
        return {
            "ok": len(cases) >= 100,
            "path": str(DEFAULT_EVAL_SEED_PATH),
            "cases": len(cases),
        }
    except Exception as exc:
        return {"ok": False, "path": str(DEFAULT_EVAL_SEED_PATH), "error": str(exc)}


def _recommendations(checks: dict) -> list[str]:
    recommendations: list[str] = []
    if not checks["data_dir"]["ok"]:
        recommendations.append("检查 data 目录权限，确保本地历史和报告可以写入。")
    if not checks["database"]["ok"]:
        recommendations.append("SQLite integrity_check 未通过，先从历史 JSON 备份恢复或删除损坏库重建。")
    if not checks["schema"]["ok"]:
        recommendations.append("数据库 schema 版本偏旧，重启 API 触发迁移后再检查。")
    if not checks["backup_export"]["ok"]:
        recommendations.append("历史导出失败，先排查 SQLite 可读性再升级或清理数据。")
    if not checks["scoring_eval_seed"]["ok"]:
        recommendations.append("评分评测集不可用，检查 apps/api/eval/scoring_seed.yaml。")
    if not recommendations:
        recommendations.append("本地数据、SQLite、备份导出和评分评测集状态正常。")
    return recommendations
