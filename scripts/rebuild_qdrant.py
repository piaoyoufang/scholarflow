from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.loader import ingest
from app.knowledge.library import knowledge_library
from app.storage.sql_db import fetch_all


def rebuild_course(course_id: str) -> None:
    docs = knowledge_library.list_course_documents(course_id)
    total = 0
    for doc in docs:
        if doc.get("status") != "success":
            continue
        file_path = Path(doc["file_path"])
        if not file_path.is_absolute():
            file_path = PROJECT_ROOT / file_path
        if not file_path.exists():
            print(f"跳过不存在文件：{file_path}")
            continue
        count = ingest(str(file_path), course_id=course_id, source_id=doc["source_id"])
        knowledge_library.update_status(doc["source_id"], "success", chunk_count=count)
        print(f"{doc['original_name']}: {count} chunks")
        total += count
    print(f"课程 {course_id} 重建完成：{total} chunks")


def rebuild_all() -> None:
    course_ids = [row["course_id"] for row in fetch_all("SELECT DISTINCT course_id FROM documents")]
    for course_id in course_ids:
        rebuild_course(course_id)


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        rebuild_course(sys.argv[1])
    else:
        rebuild_all()
