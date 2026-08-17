
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import PROJECT_ROOT
from app.storage.sql_db import execute, fetch_all, fetch_one, mysql_enabled

QA_EVENT_DB_PATH = PROJECT_ROOT / "data" / "analytics" / "qa_events.sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class QAEventStore:
    """RAG ????????? MySQL?????? db_path ??? SQLite?"""

    def __init__(self, db_path: Path = QA_EVENT_DB_PATH):
        self.db_path = db_path
        self.use_mysql = db_path == QA_EVENT_DB_PATH and mysql_enabled()
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
            CREATE TABLE IF NOT EXISTS qa_events (
                event_id VARCHAR(64) PRIMARY KEY,
                course_id VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL,
                thread_id VARCHAR(128) NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                citation_count INT NOT NULL,
                pass_result INT NOT NULL DEFAULT 1,
                quality_score INT NOT NULL DEFAULT 100,
                error TEXT NOT NULL,
                process_status VARCHAR(32) NOT NULL DEFAULT 'pending',
                process_note TEXT NOT NULL,
                processed_at VARCHAR(64) NOT NULL,
                created_at VARCHAR(64) NOT NULL,
                INDEX idx_qa_events_course_id (course_id),
                INDEX idx_qa_events_process_status (process_status)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
            return
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS qa_events (
                    event_id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    citation_count INTEGER NOT NULL,
                    pass_result INTEGER NOT NULL DEFAULT 1,
                    quality_score INTEGER NOT NULL DEFAULT 100,
                    error TEXT NOT NULL DEFAULT '',
                    process_status TEXT NOT NULL DEFAULT 'pending',
                    process_note TEXT NOT NULL DEFAULT '',
                    processed_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(qa_events)").fetchall()}
            if "process_status" not in existing_columns:
                conn.execute("ALTER TABLE qa_events ADD COLUMN process_status TEXT NOT NULL DEFAULT 'pending'")
            if "process_note" not in existing_columns:
                conn.execute("ALTER TABLE qa_events ADD COLUMN process_note TEXT NOT NULL DEFAULT ''")
            if "processed_at" not in existing_columns:
                conn.execute("ALTER TABLE qa_events ADD COLUMN processed_at TEXT NOT NULL DEFAULT ''")

    def update_process_status(self, event_id: str, status: str, note: str = "") -> None:
        if status not in {"pending", "processing", "resolved", "ignored"}:
            raise ValueError("处理状态只能是 pending、processing、resolved 或 ignored")
        if self.use_mysql:
            rowcount = execute("""
                UPDATE qa_events SET process_status = :status, process_note = :note, processed_at = :processed_at
                WHERE event_id = :event_id
            """, {"status": status, "note": note, "processed_at": utc_now(), "event_id": event_id})
            if rowcount == 0:
                raise LookupError("问答事件不存在")
            return
        with self.connect() as conn:
            cursor = conn.execute("""
                UPDATE qa_events SET process_status = ?, process_note = ?, processed_at = ? WHERE event_id = ?
            """, (status, note, utc_now(), event_id))
            if cursor.rowcount == 0:
                raise LookupError("问答事件不存在")

    def dashboard_summary(self, course_id: str) -> dict:
        if self.use_mysql:
            total = fetch_one("SELECT COUNT(*) AS count FROM qa_events WHERE course_id = :course_id", {"course_id": course_id})["count"]
            no_citation = fetch_one("SELECT COUNT(*) AS count FROM qa_events WHERE course_id = :course_id AND citation_count = 0", {"course_id": course_id})["count"]
            low_quality = fetch_one("""
                SELECT COUNT(*) AS count FROM qa_events
                WHERE course_id = :course_id AND (pass_result = 0 OR quality_score < 60 OR error != '')
            """, {"course_id": course_id})["count"]
        else:
            with self.connect() as conn:
                total = conn.execute("SELECT COUNT(*) AS count FROM qa_events WHERE course_id = ?", (course_id,)).fetchone()["count"]
                no_citation = conn.execute("SELECT COUNT(*) AS count FROM qa_events WHERE course_id = ? AND citation_count = 0", (course_id,)).fetchone()["count"]
                low_quality = conn.execute("""
                    SELECT COUNT(*) AS count FROM qa_events
                    WHERE course_id = ? AND (pass_result = 0 OR quality_score < 60 OR error != '')
                """, (course_id,)).fetchone()["count"]
        return {"qa_count": total, "no_citation_count": no_citation,
                "low_quality_count": low_quality,
                "citation_rate": 0 if total == 0 else round((total - no_citation) / total, 4)}

    def record_event(self, *, course_id: str, user_id: str, thread_id: str, question: str,
                     answer: str, citation_count: int, pass_result: bool = True,
                     quality_score: int = 100, error: str = "") -> str:
        event_id = str(uuid4())
        params = {"event_id": event_id, "course_id": course_id, "user_id": user_id,
                  "thread_id": thread_id, "question": question, "answer": answer,
                  "citation_count": citation_count, "pass_result": 1 if pass_result else 0,
                  "quality_score": quality_score, "error": error,
                  "process_status": "pending", "process_note": "", "processed_at": "", "created_at": utc_now()}
        if self.use_mysql:
            execute("""
                INSERT INTO qa_events(
                    event_id, course_id, user_id, thread_id, question, answer,
                    citation_count, pass_result, quality_score, error,
                    process_status, process_note, processed_at, created_at
                ) VALUES (
                    :event_id, :course_id, :user_id, :thread_id, :question, :answer,
                    :citation_count, :pass_result, :quality_score, :error,
                    :process_status, :process_note, :processed_at, :created_at
                )
            """, params)
            return event_id
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO qa_events(
                    event_id, course_id, user_id, thread_id, question, answer,
                    citation_count, pass_result, quality_score, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (event_id, course_id, user_id, thread_id, question, answer, citation_count,
                  1 if pass_result else 0, quality_score, error, params["created_at"]))
        return event_id

    def top_questions(self, course_id: str, limit: int = 20) -> list[dict]:
        if self.use_mysql:
            return fetch_all("""
                SELECT question, COUNT(*) AS count FROM qa_events
                WHERE course_id = :course_id GROUP BY question ORDER BY count DESC LIMIT :limit
            """, {"course_id": course_id, "limit": limit})
        with self.connect() as conn:
            rows = conn.execute("""
                SELECT question, COUNT(*) AS count FROM qa_events
                WHERE course_id = ? GROUP BY question ORDER BY count DESC LIMIT ?
            """, (course_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def no_citation_questions(self, course_id: str, limit: int = 20) -> list[dict]:
        if self.use_mysql:
            return fetch_all("""
                SELECT event_id, question, answer, citation_count, created_at
                FROM qa_events WHERE course_id = :course_id AND citation_count = 0
                ORDER BY created_at DESC LIMIT :limit
            """, {"course_id": course_id, "limit": limit})
        with self.connect() as conn:
            rows = conn.execute("""
                SELECT event_id, question, answer, citation_count, created_at
                FROM qa_events WHERE course_id = ? AND citation_count = 0
                ORDER BY created_at DESC LIMIT ?
            """, (course_id, limit)).fetchall()
        return [dict(row) for row in rows]

    def low_quality_questions(self, course_id: str, limit: int = 20) -> list[dict]:
        if self.use_mysql:
            return fetch_all("""
                SELECT event_id, question, answer, quality_score, pass_result, error, created_at
                FROM qa_events
                WHERE course_id = :course_id AND (pass_result = 0 OR quality_score < 60 OR error != '')
                ORDER BY created_at DESC LIMIT :limit
            """, {"course_id": course_id, "limit": limit})
        with self.connect() as conn:
            rows = conn.execute("""
                SELECT event_id, question, answer, quality_score, pass_result, error, created_at
                FROM qa_events
                WHERE course_id = ? AND (pass_result = 0 OR quality_score < 60 OR error != '')
                ORDER BY created_at DESC LIMIT ?
            """, (course_id, limit)).fetchall()
        return [dict(row) for row in rows]


qa_event_store = QAEventStore()
