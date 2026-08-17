
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import PROJECT_ROOT
from app.storage.sql_db import execute, fetch_all, mysql_enabled

FEEDBACK_DB_PATH = PROJECT_ROOT / "data" / "feedback" / "feedback.sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FeedbackStore:
    """????????? MySQL?????? db_path ??? SQLite?"""

    def __init__(self, db_path: Path = FEEDBACK_DB_PATH):
        self.db_path = db_path
        self.use_mysql = db_path == FEEDBACK_DB_PATH and mysql_enabled()
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
            CREATE TABLE IF NOT EXISTS qa_feedback (
                feedback_id VARCHAR(64) PRIMARY KEY,
                course_id VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL,
                thread_id VARCHAR(128) NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                rating VARCHAR(16) NOT NULL,
                reason TEXT NOT NULL,
                comment TEXT NOT NULL,
                created_at VARCHAR(64) NOT NULL,
                INDEX idx_qa_feedback_course_id (course_id),
                INDEX idx_qa_feedback_rating (rating)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
            return
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS qa_feedback (
                    feedback_id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    rating TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)

    def create_feedback(self, *, course_id: str, user_id: str, thread_id: str,
        question: str, answer: str, rating: str, reason: str = "", comment: str = "") -> str:
        if rating not in {"up", "down"}:
            raise ValueError("反馈类型只能是 up 或 down")
        feedback_id = str(uuid4())
        params = {"feedback_id": feedback_id, "course_id": course_id, "user_id": user_id,
                  "thread_id": thread_id, "question": question, "answer": answer,
                  "rating": rating, "reason": reason, "comment": comment, "created_at": utc_now()}
        if self.use_mysql:
            execute("""
                INSERT INTO qa_feedback(
                    feedback_id, course_id, user_id, thread_id, question, answer, rating, reason, comment, created_at
                ) VALUES (
                    :feedback_id, :course_id, :user_id, :thread_id, :question, :answer, :rating, :reason, :comment, :created_at
                )
            """, params)
            return feedback_id
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO qa_feedback(
                    feedback_id, course_id, user_id, thread_id, question, answer, rating, reason, comment, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(params.values()))
        return feedback_id

    def summary(self, course_id: str) -> dict:
        if self.use_mysql:
            rows = fetch_all("""
                SELECT rating, COUNT(*) AS count FROM qa_feedback
                WHERE course_id = :course_id GROUP BY rating
            """, {"course_id": course_id})
        else:
            with self.connect() as conn:
                rows = conn.execute("""
                    SELECT rating, COUNT(*) AS count FROM qa_feedback
                    WHERE course_id = ? GROUP BY rating
                """, (course_id,)).fetchall()
        data = {"up": 0, "down": 0}
        for row in rows:
            data[row["rating"]] = row["count"]
        return data

    def recent_down_feedback(self, course_id: str, limit: int = 20) -> list[dict]:
        if self.use_mysql:
            return fetch_all("""
                SELECT * FROM qa_feedback
                WHERE course_id = :course_id AND rating = 'down'
                ORDER BY created_at DESC LIMIT :limit
            """, {"course_id": course_id, "limit": limit})
        with self.connect() as conn:
            rows = conn.execute("""
                SELECT * FROM qa_feedback
                WHERE course_id = ? AND rating = 'down'
                ORDER BY created_at DESC LIMIT ?
            """, (course_id, limit)).fetchall()
        return [dict(row) for row in rows]


feedback_store = FeedbackStore()
