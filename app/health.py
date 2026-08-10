from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import PROJECT_ROOT, settings


def resolve_project_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def check_sqlite(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, "missing"
    try:
        with sqlite3.connect(str(path), timeout=1) as connection:
            connection.execute("SELECT 1").fetchone()
    except Exception as exc:
        return False, type(exc).__name__
    return True, "ok"


def check_mysql() -> tuple[bool, str]:
    try:
        from app.storage.sql_db import fetch_one
        row = fetch_one("SELECT 1 AS ok")
        return (row or {}).get("ok") == 1, "ok"
    except Exception as exc:
        return False, type(exc).__name__


def check_redis() -> tuple[bool, str]:
    try:
        from app.cache import ping
        return ping()
    except Exception as exc:
        return False, type(exc).__name__


def check_qdrant() -> tuple[bool, str]:
    try:
        from app.vectorstores.qdrant_store import collection_status
        return collection_status()
    except Exception as exc:
        return False, type(exc).__name__


def readiness_report() -> dict[str, object]:
    auth_path = resolve_project_path(settings.auth_db_path)
    checkpoint_path = resolve_project_path(settings.checkpoint_db_path)

    auth_ok, auth_status = check_sqlite(auth_path)
    checkpoint_ok, checkpoint_status = check_sqlite(checkpoint_path)

    if settings.relational_backend.lower() == "mysql":
        relational_ok, relational_status = check_mysql()
        relational_name = "mysql"
    else:
        relational_ok, relational_status = True, "sqlite"
        relational_name = "sqlite"

    if settings.vector_backend.lower() == "qdrant":
        vector_ok, vector_status = check_qdrant()
        vector_name = "qdrant"
    else:
        vector_path = resolve_project_path(settings.vector_db_dir)
        vector_ok = vector_path.exists() and vector_path.is_dir() and (vector_path / "chroma.sqlite3").exists()
        vector_status = "ok" if vector_ok else "missing"
        vector_name = "chroma"

    redis_ok, redis_status = check_redis()

    checks = {
        "auth_database": auth_status,
        "checkpoint_database": checkpoint_status,
        "relational_backend": relational_name,
        "relational_database": relational_status,
        "cache_database": redis_status,
        "vector_backend": vector_name,
        "vector_database": vector_status,
    }
    return {
        "ready": auth_ok and checkpoint_ok and relational_ok and redis_ok and vector_ok,
        "checks": checks,
    }
