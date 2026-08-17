from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import PROJECT_ROOT
from app.storage.sql_db import execute, fetch_all, fetch_one, mysql_enabled

HISTORY_DB_PATH = PROJECT_ROOT / "data" / "learning_history" / "history.sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LearningHistoryStore:
    """保存用户在指定课程下生成的学习计划和题单。"""

    def __init__(self, db_path: Path = HISTORY_DB_PATH):
        self.db_path = db_path
        self.use_mysql = db_path == HISTORY_DB_PATH and mysql_enabled()
        if not self.use_mysql:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        if self.use_mysql:
            execute(
                """
                CREATE TABLE IF NOT EXISTS learning_plan_history (
                    record_id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    course_id VARCHAR(64) NOT NULL,
                    goal TEXT NOT NULL,
                    days INT NOT NULL,
                    difficulty VARCHAR(32) NOT NULL,
                    daily_minutes INT NOT NULL,
                    result_json JSON NOT NULL,
                    created_at VARCHAR(64) NOT NULL,
                    INDEX idx_plan_history_user_course (user_id, course_id, created_at)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            execute(
                """
                CREATE TABLE IF NOT EXISTS quiz_history (
                    record_id VARCHAR(64) PRIMARY KEY,
                    user_id VARCHAR(64) NOT NULL,
                    course_id VARCHAR(64) NOT NULL,
                    topic TEXT NOT NULL,
                    question_count INT NOT NULL,
                    question_type VARCHAR(32) NOT NULL,
                    difficulty VARCHAR(32) NOT NULL,
                    result_json JSON NOT NULL,
                    created_at VARCHAR(64) NOT NULL,
                    INDEX idx_quiz_history_user_course (user_id, course_id, created_at)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
            return

        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_plan_history (
                    record_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    days INTEGER NOT NULL,
                    difficulty TEXT NOT NULL,
                    daily_minutes INTEGER NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_plan_history_user_course
                ON learning_plan_history(user_id, course_id, created_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS quiz_history (
                    record_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    question_count INTEGER NOT NULL,
                    question_type TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_quiz_history_user_course
                ON quiz_history(user_id, course_id, created_at)
                """
            )

    @staticmethod
    def _loads(value: str | dict) -> dict:
        return value if isinstance(value, dict) else json.loads(value)

    def save_plan(
        self,
        *,
        user_id: str,
        course_id: str,
        goal: str,
        days: int,
        difficulty: str,
        daily_minutes: int,
        result: dict,
    ) -> str:
        record_id = str(uuid4())
        created_at = utc_now()
        payload = json.dumps(result, ensure_ascii=False)
        if self.use_mysql:
            execute(
                """
                INSERT INTO learning_plan_history(
                    record_id, user_id, course_id, goal, days, difficulty,
                    daily_minutes, result_json, created_at
                ) VALUES (
                    :record_id, :user_id, :course_id, :goal, :days, :difficulty,
                    :daily_minutes, :result_json, :created_at
                )
                """,
                {
                    "record_id": record_id, "user_id": user_id, "course_id": course_id,
                    "goal": goal, "days": days, "difficulty": difficulty,
                    "daily_minutes": daily_minutes, "result_json": payload,
                    "created_at": created_at,
                },
            )
            return record_id
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO learning_plan_history(
                    record_id, user_id, course_id, goal, days, difficulty,
                    daily_minutes, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (record_id, user_id, course_id, goal, days, difficulty,
                 daily_minutes, payload, created_at),
            )
        return record_id

    def save_quiz(
        self,
        *,
        user_id: str,
        course_id: str,
        topic: str,
        question_count: int,
        question_type: str,
        difficulty: str,
        result: dict,
    ) -> str:
        record_id = str(uuid4())
        created_at = utc_now()
        payload = json.dumps(result, ensure_ascii=False)
        if self.use_mysql:
            execute(
                """
                INSERT INTO quiz_history(
                    record_id, user_id, course_id, topic, question_count,
                    question_type, difficulty, result_json, created_at
                ) VALUES (
                    :record_id, :user_id, :course_id, :topic, :question_count,
                    :question_type, :difficulty, :result_json, :created_at
                )
                """,
                {
                    "record_id": record_id, "user_id": user_id, "course_id": course_id,
                    "topic": topic, "question_count": question_count,
                    "question_type": question_type, "difficulty": difficulty,
                    "result_json": payload, "created_at": created_at,
                },
            )
            return record_id
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO quiz_history(
                    record_id, user_id, course_id, topic, question_count,
                    question_type, difficulty, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (record_id, user_id, course_id, topic, question_count,
                 question_type, difficulty, payload, created_at),
            )
        return record_id

    def list_plans(self, user_id: str, course_id: str) -> list[dict]:
        sql = """
            SELECT record_id, goal, days, difficulty, daily_minutes, created_at
            FROM learning_plan_history
            WHERE user_id = {user_id} AND course_id = {course_id}
            ORDER BY created_at DESC
        """
        if self.use_mysql:
            return fetch_all(
                sql.format(user_id=":user_id", course_id=":course_id"),
                {"user_id": user_id, "course_id": course_id},
            )
        with self.connect() as conn:
            rows = conn.execute(
                sql.format(user_id="?", course_id="?"),
                (user_id, course_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_quizzes(self, user_id: str, course_id: str) -> list[dict]:
        sql = """
            SELECT record_id, topic, question_count, question_type, difficulty, created_at
            FROM quiz_history
            WHERE user_id = {user_id} AND course_id = {course_id}
            ORDER BY created_at DESC
        """
        if self.use_mysql:
            return fetch_all(
                sql.format(user_id=":user_id", course_id=":course_id"),
                {"user_id": user_id, "course_id": course_id},
            )
        with self.connect() as conn:
            rows = conn.execute(
                sql.format(user_id="?", course_id="?"),
                (user_id, course_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_plan(self, record_id: str, user_id: str, course_id: str) -> dict | None:
        return self._get_record("learning_plan_history", record_id, user_id, course_id)

    def get_quiz(self, record_id: str, user_id: str, course_id: str) -> dict | None:
        return self._get_record("quiz_history", record_id, user_id, course_id)

    def delete_plan(self, record_id: str, user_id: str, course_id: str) -> bool:
        return self._delete_record("learning_plan_history", record_id, user_id, course_id)

    def delete_quiz(self, record_id: str, user_id: str, course_id: str) -> bool:
        return self._delete_record("quiz_history", record_id, user_id, course_id)

    def _get_record(self, table: str, record_id: str, user_id: str, course_id: str) -> dict | None:
        sql = f"""
            SELECT * FROM {table}
            WHERE record_id = {{record_id}} AND user_id = {{user_id}} AND course_id = {{course_id}}
        """
        if self.use_mysql:
            row = fetch_one(
                sql.format(record_id=":record_id", user_id=":user_id", course_id=":course_id"),
                {"record_id": record_id, "user_id": user_id, "course_id": course_id},
            )
        else:
            with self.connect() as conn:
                raw = conn.execute(
                    sql.format(record_id="?", user_id="?", course_id="?"),
                    (record_id, user_id, course_id),
                ).fetchone()
            row = dict(raw) if raw else None
        if not row:
            return None
        row["result"] = self._loads(row.pop("result_json"))
        return row

    def _delete_record(self, table: str, record_id: str, user_id: str, course_id: str) -> bool:
        sql = f"""
            DELETE FROM {table}
            WHERE record_id = {{record_id}} AND user_id = {{user_id}} AND course_id = {{course_id}}
        """
        if self.use_mysql:
            return execute(
                sql.format(record_id=":record_id", user_id=":user_id", course_id=":course_id"),
                {"record_id": record_id, "user_id": user_id, "course_id": course_id},
            ) > 0
        with self.connect() as conn:
            result = conn.execute(
                sql.format(record_id="?", user_id="?", course_id="?"),
                (record_id, user_id, course_id),
            )
        return result.rowcount > 0


learning_history_store = LearningHistoryStore()
