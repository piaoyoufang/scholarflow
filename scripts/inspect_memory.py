import sqlite3
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT, settings
from app.graph.builder import memory_workflow


def _database_path() -> Path:
    path = Path(settings.checkpoint_db_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _short_text(value: Any, max_length: int = 100) -> str:
    """把状态内容整理成适合终端查看的一行文本。"""
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}..."


def _decision_field(decision: Any, field: str) -> str:
    """兼容Pydantic对象和旧版字典两种checkpoint格式。"""
    if decision is None:
        return ""
    if isinstance(decision, dict):
        return str(decision.get(field, ""))
    return str(getattr(decision, field, ""))


def main() -> None:
    """查看每个线程的checkpoint数量和最新多Agent执行状态。"""
    path = _database_path()
    print("数据库：", path)

    if not path.exists():
        print("状态：尚未生成。先通过 /ask 完成一次问答。")
        return

    with sqlite3.connect(str(path)) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name='checkpoints'"
        ).fetchone()
        if not table:
            print("状态：数据库存在，但 checkpoints 表尚未创建。")
            return

        rows = connection.execute(
            "SELECT thread_id, COUNT(*) AS checkpoint_count "
            "FROM checkpoints GROUP BY thread_id ORDER BY thread_id"
        ).fetchall()

    print("线程数量：", len(rows))
    if not rows:
        print("状态：尚无会话。先通过 /ask 完成一次问答。")
        return

    for thread_id, checkpoint_count in rows:
        snapshot = memory_workflow.get_state(
            {"configurable": {"thread_id": thread_id}}
        )
        values = snapshot.values
        decision = values.get("supervisor_decision")
        trace = values.get("agent_trace", [])

        print(f"\n- 线程：{thread_id}")
        print(f"  checkpoint数量：{checkpoint_count}")
        print(f"  最新问题：{_short_text(values.get('question')) or '无'}")

        if decision is None and not trace:
            print("  Supervisor决策：无")
            print("  Agent轨迹：无（这是旧checkpoint，或请求由未重启的旧后端处理）")
        else:
            print(
                "  Supervisor决策："
                f"{_decision_field(decision, 'next_agent') or 'unknown'}"
            )
            print(
                "  分流原因："
                f"{_short_text(_decision_field(decision, 'reason')) or '无'}"
            )
            print(f"  Agent轨迹：{trace}")

        print(f"  使用工具：{values.get('selected_tool') or 'none'}")
        print(f"  工具状态：{values.get('tool_used') or 'none'}")
        if values.get("mcp_error"):
            print(f"  MCP错误：{_short_text(values['mcp_error'])}")


if __name__ == "__main__":
    main()
