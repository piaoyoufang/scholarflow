
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import PROJECT_ROOT, settings
from app.storage.sql_db import execute, fetch_all, fetch_one, mysql_enabled

COURSE_DB_PATH = PROJECT_ROOT / "data" / "courses" / "courses.sqlite"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CourseRecord:
    course_id: str
    course_name: str
    description: str
    owner_teacher_id: str
    created_at: str
    updated_at: str


class CourseStore:
    """???????????? MySQL???????? db_path ???? SQLite?"""

    def __init__(self, db_path: Path = COURSE_DB_PATH):
        self.db_path = db_path
        self.use_mysql = db_path == COURSE_DB_PATH and mysql_enabled()
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
            CREATE TABLE IF NOT EXISTS courses (
                course_id VARCHAR(64) PRIMARY KEY,
                course_name VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                owner_teacher_id VARCHAR(64) NOT NULL,
                created_at VARCHAR(64) NOT NULL,
                updated_at VARCHAR(64) NOT NULL,
                INDEX idx_courses_owner_teacher_id (owner_teacher_id)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
            execute("""
            CREATE TABLE IF NOT EXISTS course_members (
                course_id VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL,
                role_in_course VARCHAR(32) NOT NULL,
                joined_at VARCHAR(64) NOT NULL,
                PRIMARY KEY (course_id, user_id),
                INDEX idx_course_members_user_id (user_id)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            """)
            return
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS courses (
                    course_id TEXT PRIMARY KEY,
                    course_name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    owner_teacher_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS course_members (
                    course_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role_in_course TEXT NOT NULL,
                    joined_at TEXT NOT NULL,
                    PRIMARY KEY (course_id, user_id)
                )
            """)

    def create_course(self, course_name: str, description: str, owner_teacher_id: str) -> CourseRecord:
        now = utc_now()
        course_id = str(uuid4())
        if self.use_mysql:
            execute(
                """
                INSERT INTO courses(course_id, course_name, description, owner_teacher_id, created_at, updated_at)
                VALUES (:course_id, :course_name, :description, :owner_teacher_id, :created_at, :updated_at)
                """,
                {"course_id": course_id, "course_name": course_name, "description": description,
                 "owner_teacher_id": owner_teacher_id, "created_at": now, "updated_at": now},
            )
            execute(
                """
                INSERT INTO course_members(course_id, user_id, role_in_course, joined_at)
                VALUES (:course_id, :user_id, :role_in_course, :joined_at)
                """,
                {"course_id": course_id, "user_id": owner_teacher_id, "role_in_course": "teacher", "joined_at": now},
            )
        else:
            with self.connect() as conn:
                conn.execute("""
                    INSERT INTO courses(course_id, course_name, description, owner_teacher_id, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (course_id, course_name, description, owner_teacher_id, now, now))
                conn.execute("""
                    INSERT INTO course_members(course_id, user_id, role_in_course, joined_at)
                    VALUES (?, ?, ?, ?)
                """, (course_id, owner_teacher_id, "teacher", now))
        return CourseRecord(course_id, course_name, description, owner_teacher_id, now, now)

    def list_user_courses(self, user_id: str) -> list[dict]:
        sql = """
            SELECT c.course_id, c.course_name, c.description, c.owner_teacher_id,
                   c.created_at, c.updated_at, m.role_in_course
            FROM courses c
            JOIN course_members m ON c.course_id = m.course_id
            WHERE m.user_id = {placeholder}
            ORDER BY c.updated_at DESC
        """
        if self.use_mysql:
            return fetch_all(sql.format(placeholder=":user_id"), {"user_id": user_id})
        with self.connect() as conn:
            rows = conn.execute(sql.format(placeholder="?"), (user_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_course(self, course_id: str) -> dict | None:
        if self.use_mysql:
            return fetch_one("SELECT * FROM courses WHERE course_id = :course_id", {"course_id": course_id})
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM courses WHERE course_id = ?", (course_id,)).fetchone()
        return dict(row) if row else None

    def add_member(self, course_id: str, user_id: str, role_in_course: str = "student") -> None:
        if role_in_course not in {"teacher", "student"}:
            raise ValueError("role_in_course ??? teacher ? student")
        if not self.get_course(course_id):
            raise LookupError("?????")
        now = utc_now()
        if self.use_mysql:
            execute(
                """
                INSERT INTO course_members(course_id, user_id, role_in_course, joined_at)
                VALUES (:course_id, :user_id, :role_in_course, :joined_at)
                ON DUPLICATE KEY UPDATE role_in_course = VALUES(role_in_course), joined_at = VALUES(joined_at)
                """,
                {"course_id": course_id, "user_id": user_id, "role_in_course": role_in_course, "joined_at": now},
            )
            return
        with self.connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO course_members(course_id, user_id, role_in_course, joined_at)
                VALUES (?, ?, ?, ?)
            """, (course_id, user_id, role_in_course, now))

    def list_members(self, course_id: str) -> list[dict]:
        if self.use_mysql:
            return fetch_all("""
                SELECT course_id, user_id, role_in_course, joined_at
                FROM course_members
                WHERE course_id = :course_id
                ORDER BY joined_at ASC
            """, {"course_id": course_id})
        with self.connect() as conn:
            rows = conn.execute("""
                SELECT course_id, user_id, role_in_course, joined_at
                FROM course_members
                WHERE course_id = ?
                ORDER BY joined_at ASC
            """, (course_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_member_role(self, course_id: str, user_id: str) -> str | None:
        if self.use_mysql:
            row = fetch_one("""
                SELECT role_in_course FROM course_members
                WHERE course_id = :course_id AND user_id = :user_id
            """, {"course_id": course_id, "user_id": user_id})
        else:
            with self.connect() as conn:
                row = conn.execute("""
                    SELECT role_in_course FROM course_members
                    WHERE course_id = ? AND user_id = ?
                """, (course_id, user_id)).fetchone()
        return row["role_in_course"] if row else None

    def require_course_access(self, course_id: str, user_id: str) -> None:
        if not self.get_course(course_id):
            raise LookupError("?????")
        if not self.get_member_role(course_id, user_id):
            raise PermissionError("????????????")

    def require_course_teacher(self, course_id: str, user_id: str) -> None:
        if not self.get_course(course_id):
            raise LookupError("?????")
        if self.get_member_role(course_id, user_id) != "teacher":
            raise PermissionError("?????????????")


course_store = CourseStore()
