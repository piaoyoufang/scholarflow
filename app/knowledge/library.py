
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import PROJECT_ROOT
from app.storage.sql_db import execute, fetch_all, fetch_one, mysql_enabled

DOCUMENT_DB_PATH = PROJECT_ROOT / "data" / "knowledge" / "documents.sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DocumentRecord:
    source_id: str
    course_id: str
    uploader_user_id: str
    original_name: str
    saved_name: str
    file_path: str
    file_type: str
    file_size: int
    chunk_count: int
    status: str
    created_at: str
    updated_at: str


class KnowledgeLibrary:
    """????????????? MySQL?????? db_path ??? SQLite?"""

    def __init__(self, db_path: Path = DOCUMENT_DB_PATH):
        self.db_path = db_path
        self.use_mysql = db_path == DOCUMENT_DB_PATH and mysql_enabled()
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
            CREATE TABLE IF NOT EXISTS documents (
                source_id VARCHAR(64) PRIMARY KEY,
                course_id VARCHAR(64) NOT NULL,
                uploader_user_id VARCHAR(64) NOT NULL,
                original_name VARCHAR(255) NOT NULL,
                saved_name VARCHAR(255) NOT NULL,
                file_path TEXT NOT NULL,
                file_type VARCHAR(32) NOT NULL,
                file_size BIGINT NOT NULL,
                chunk_count INT NOT NULL DEFAULT 0,
                status VARCHAR(32) NOT NULL DEFAULT 'processing',
                created_at VARCHAR(64) NOT NULL,
                updated_at VARCHAR(64) NOT NULL,
                INDEX idx_documents_course_id (course_id),
                INDEX idx_documents_status (status)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
            return
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    source_id TEXT PRIMARY KEY,
                    course_id TEXT NOT NULL,
                    uploader_user_id TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    saved_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'processing',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    def register_document(self, course_id: str, uploader_user_id: str, original_name: str,
                          saved_name: str, file_path: str, file_type: str, file_size: int,
                          status: str = "processing") -> DocumentRecord:
        now = utc_now()
        record = DocumentRecord(str(uuid4()), course_id, uploader_user_id, original_name, saved_name,
                                file_path, file_type, file_size, 0, status, now, now)
        if self.use_mysql:
            execute("""
                INSERT INTO documents(
                    source_id, course_id, uploader_user_id, original_name, saved_name,
                    file_path, file_type, file_size, chunk_count, status, created_at, updated_at
                ) VALUES (
                    :source_id, :course_id, :uploader_user_id, :original_name, :saved_name,
                    :file_path, :file_type, :file_size, :chunk_count, :status, :created_at, :updated_at
                )
            """, record.__dict__)
            return record
        with self.connect() as conn:
            conn.execute("""
                INSERT INTO documents(
                    source_id, course_id, uploader_user_id, original_name, saved_name,
                    file_path, file_type, file_size, chunk_count, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, tuple(record.__dict__.values()))
        return record

    def list_course_documents(self, course_id: str) -> list[dict]:
        if self.use_mysql:
            return fetch_all("""
                SELECT * FROM documents WHERE course_id = :course_id ORDER BY created_at DESC
            """, {"course_id": course_id})
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM documents WHERE course_id = ? ORDER BY created_at DESC", (course_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_document(self, source_id: str) -> dict | None:
        if self.use_mysql:
            return fetch_one("SELECT * FROM documents WHERE source_id = :source_id", {"source_id": source_id})
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE source_id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    def update_status(self, source_id: str, status: str, chunk_count: int | None = None) -> None:
        if status not in {"processing", "success", "failed"}:
            raise ValueError("文档状态只能是 processing、success 或 failed")
        now = utc_now()
        if self.use_mysql:
            if chunk_count is None:
                execute("UPDATE documents SET status = :status, updated_at = :updated_at WHERE source_id = :source_id",
                        {"status": status, "updated_at": now, "source_id": source_id})
            else:
                execute("""
                    UPDATE documents SET status = :status, chunk_count = :chunk_count, updated_at = :updated_at
                    WHERE source_id = :source_id
                """, {"status": status, "chunk_count": chunk_count, "updated_at": now, "source_id": source_id})
            return
        with self.connect() as conn:
            if chunk_count is None:
                conn.execute("UPDATE documents SET status = ?, updated_at = ? WHERE source_id = ?", (status, now, source_id))
            else:
                conn.execute("UPDATE documents SET status = ?, chunk_count = ?, updated_at = ? WHERE source_id = ?", (status, chunk_count, now, source_id))

    def delete_document_record(self, source_id: str) -> dict:
        document = self.get_document(source_id)
        if not document:
            raise LookupError("文档不存在")
        if self.use_mysql:
            execute("DELETE FROM documents WHERE source_id = :source_id", {"source_id": source_id})
        else:
            with self.connect() as conn:
                conn.execute("DELETE FROM documents WHERE source_id = ?", (source_id,))
        return document

    def document_summary(self, course_id: str) -> dict:
        if self.use_mysql:
            rows = fetch_all("""
                SELECT status, COUNT(*) AS count FROM documents
                WHERE course_id = :course_id GROUP BY status
            """, {"course_id": course_id})
        else:
            with self.connect() as conn:
                rows = conn.execute("""
                    SELECT status, COUNT(*) AS count FROM documents
                    WHERE course_id = ? GROUP BY status
                """, (course_id,)).fetchall()
        data = {"document_count": 0, "success_document_count": 0,
                "failed_document_count": 0, "processing_document_count": 0}
        for row in rows:
            count = row["count"]
            data["document_count"] += count
            if row["status"] == "success": data["success_document_count"] = count
            elif row["status"] == "failed": data["failed_document_count"] = count
            elif row["status"] == "processing": data["processing_document_count"] = count
        return data


knowledge_library = KnowledgeLibrary()
