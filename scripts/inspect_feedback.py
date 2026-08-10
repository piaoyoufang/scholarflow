from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import PROJECT_ROOT


DB_PATH = PROJECT_ROOT / "data" / "feedback" / "feedback.sqlite"


def main() -> None:
    if not DB_PATH.exists():
        print(f"反馈数据库不存在：{DB_PATH}")
        print("请先在前端 AI 问答页面点击一次“有帮助”或“没帮助”。")
        return

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                feedback_id,
                course_id,
                user_id,
                thread_id,
                rating,
                reason,
                comment,
                question,
                created_at
            FROM qa_feedback
            ORDER BY created_at DESC
            LIMIT 20
            """
        ).fetchall()

    if not rows:
        print("qa_feedback 表里暂时没有反馈记录。")
        print("请先在前端 AI 问答页面点击“有帮助”或“没帮助”。")
        return

    for index, row in enumerate(rows, start=1):
        print("=" * 80)
        print(f"{index}. feedback_id: {row['feedback_id']}")
        print(f"course_id : {row['course_id']}")
        print(f"user_id   : {row['user_id']}")
        print(f"thread_id : {row['thread_id']}")
        print(f"rating    : {row['rating']}")
        print(f"reason    : {row['reason']}")
        print(f"comment   : {row['comment']}")
        print(f"question  : {row['question']}")
        print(f"created_at: {row['created_at']}")


if __name__ == "__main__":
    main()
