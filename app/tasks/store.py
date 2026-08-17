
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import PROJECT_ROOT
from app.storage.sql_db import execute, fetch_all, fetch_one, mysql_enabled

TASK_DB_PATH = PROJECT_ROOT / "data" / "tasks" / "tasks.sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    """????????????? MySQL?????? db_path ??? SQLite?"""

    def __init__(self, db_path: Path = TASK_DB_PATH):
        self.db_path = db_path
        self.use_mysql = db_path == TASK_DB_PATH and mysql_enabled()
        if not self.use_mysql:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        if self.use_mysql:
            execute("""
            CREATE TABLE IF NOT EXISTS ingestion_tasks (
                task_id VARCHAR(64) PRIMARY KEY,
                course_id VARCHAR(64) NOT NULL,
                source_id VARCHAR(64) NOT NULL,
                owner_user_id VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                progress INT NOT NULL DEFAULT 0,
                message TEXT NOT NULL,
                result_json TEXT NOT NULL,
                error TEXT NOT NULL,
                created_at VARCHAR(64) NOT NULL,
                updated_at VARCHAR(64) NOT NULL,
                INDEX idx_ingestion_tasks_course_id (course_id),
                INDEX idx_ingestion_tasks_status (status)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
            return
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ingestion_tasks (
                    task_id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    owner_user_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    def create_task(self, course_id: str, source_id: str, owner_user_id: str) -> str:
        task_id = str(uuid4())
        now = utc_now()
        params = {"task_id": task_id, "course_id": course_id, "source_id": source_id,
                  "owner_user_id": owner_user_id, "status": "pending", "progress": 0,
                  "message": "等待处理", "result_json": "{}", "error": "", "created_at": now, "updated_at": now}
        if self.use_mysql:
            execute("""
                INSERT INTO ingestion_tasks(
                    task_id, course_id, source_id, owner_user_id, status,
                    progress, message, result_json, error, created_at, updated_at
                ) VALUES (
                    :task_id, :course_id, :source_id, :owner_user_id, :status,
                    :progress, :message, :result_json, :error, :created_at, :updated_at
                )
            """, params)
            return task_id
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO ingestion_tasks(
                    task_id, course_id, source_id, owner_user_id, status,
                    progress, message, result_json, error, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(params.values()))
        return task_id

    def update_task(self, task_id: str, status: str, progress: int, message: str,
                    result: dict | None = None, error: str = "") -> None:
        params = {"task_id": task_id, "status": status, "progress": progress,
                  "message": message, "result_json": json.dumps(result or {}, ensure_ascii=False),
                  "error": error, "updated_at": utc_now()}
        if self.use_mysql:
            execute("""
                UPDATE ingestion_tasks
                SET status = :status, progress = :progress, message = :message,
                    result_json = :result_json, error = :error, updated_at = :updated_at
                WHERE task_id = :task_id
            """, params)
            return
        with self.connect() as conn:
            conn.execute("""
                UPDATE ingestion_tasks
                SET status = ?, progress = ?, message = ?, result_json = ?, error = ?, updated_at = ?
                WHERE task_id = ?
            """, (status, progress, message, params["result_json"], error, params["updated_at"], task_id))

    def _decode(self, data: dict | None) -> dict | None:
        if not data:
            return None
        data["result"] = json.loads(data.pop("result_json") or "{}")
        return data

    def get_task(self, task_id: str) -> dict | None:
        if self.use_mysql:
            return self._decode(fetch_one("SELECT * FROM ingestion_tasks WHERE task_id = :task_id", {"task_id": task_id}))
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM ingestion_tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._decode(dict(row) if row else None)

    def list_course_tasks(self, course_id: str) -> list[dict]:
        if self.use_mysql:
            rows = fetch_all("""
                SELECT * FROM ingestion_tasks WHERE course_id = :course_id ORDER BY created_at DESC
            """, {"course_id": course_id})
        else:
            with self.connect() as conn:
                rows = conn.execute("""
                    SELECT * FROM ingestion_tasks WHERE course_id = ? ORDER BY created_at DESC
                """, (course_id,)).fetchall()
                rows = [dict(row) for row in rows]
        return [self._decode(dict(row)) for row in rows]


task_store = TaskStore()
