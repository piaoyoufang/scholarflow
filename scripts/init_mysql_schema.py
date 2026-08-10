from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.storage.sql_db import execute


def init_mysql_schema() -> None:
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


if __name__ == "__main__":
    init_mysql_schema()
    print("MySQL tables initialized successfully")
