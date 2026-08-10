from pathlib import Path
import sys
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.sql_db import execute
from scripts.init_mysql_schema import init_mysql_schema

TABLES = [
    (PROJECT_ROOT / "data" / "courses" / "courses.sqlite", "courses", "course_id"),
    (PROJECT_ROOT / "data" / "courses" / "courses.sqlite", "course_members", None),
    (PROJECT_ROOT / "data" / "knowledge" / "documents.sqlite", "documents", "source_id"),
    (PROJECT_ROOT / "data" / "feedback" / "feedback.sqlite", "qa_feedback", "feedback_id"),
    (PROJECT_ROOT / "data" / "analytics" / "qa_events.sqlite", "qa_events", "event_id"),
    (PROJECT_ROOT / "data" / "tasks" / "tasks.sqlite", "ingestion_tasks", "task_id"),
]


def sqlite_rows(db_path: Path, table: str) -> list[dict]:
    if not db_path.exists():
        return []
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if not exists:
            return []
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]


def upsert_row(table: str, row: dict, primary_key: str | None) -> None:
    columns = list(row.keys())
    values = ", ".join(f":{col}" for col in columns)
    col_sql = ", ".join(columns)
    if primary_key:
        updates = ", ".join(f"{col}=VALUES({col})" for col in columns if col != primary_key)
        sql = f"INSERT INTO {table}({col_sql}) VALUES ({values}) ON DUPLICATE KEY UPDATE {updates}"
    elif table == "course_members":
        sql = f"INSERT INTO {table}({col_sql}) VALUES ({values}) ON DUPLICATE KEY UPDATE role_in_course=VALUES(role_in_course), joined_at=VALUES(joined_at)"
    else:
        sql = f"INSERT INTO {table}({col_sql}) VALUES ({values})"
    execute(sql, row)


def main() -> None:
    init_mysql_schema()
    total = 0
    for db_path, table, pk in TABLES:
        rows = sqlite_rows(db_path, table)
        for row in rows:
            upsert_row(table, row, pk)
        print(f"{table}: migrated {len(rows)} rows")
        total += len(rows)
    print(f"迁移完成，共 {total} 行")


if __name__ == "__main__":
    main()
