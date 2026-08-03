import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from app.graph.nodes import update_memory_summary
from app.graph.state import AgentState


def test_short_history_does_not_summarize() -> None:
    state: AgentState = {
        "question": "测试",
        "history": [
            {"role": "user", "content": "第一条"},
            {"role": "assistant", "content": "第二条"},
        ],
        "memory_summary": "旧摘要",
        "turn_count": 1,
    }
    with patch("app.graph.nodes.fast_model") as mocked_model:
        result = update_memory_summary(state)
    assert result == "旧摘要"
    mocked_model.assert_not_called()


def test_summary_failure_keeps_old_summary() -> None:
    state: AgentState = {
        "question": "测试",
        "history": [
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"消息 {index}",
            }
            for index in range(8)
        ],
        "memory_summary": "不能丢失的旧摘要",
        "turn_count": 2,
    }

    class BrokenModel:
        def invoke(self, _prompt: str):
            raise RuntimeError("模拟摘要模型失败")

    with patch("app.graph.nodes.fast_model", return_value=BrokenModel()):
        with patch(
            "app.graph.nodes.run_with_retry",
            side_effect=lambda operation, **_kwargs: operation(),
        ):
            result = update_memory_summary(state)
    assert result == "不能丢失的旧摘要"


def test_summary_fields_persist_in_checkpoint() -> None:
    with TemporaryDirectory() as directory:
        database = Path(directory) / "summary-test.sqlite"
        connection = sqlite3.connect(str(database), check_same_thread=False)
        saver = SqliteSaver(connection)

        def write_memory(_state: AgentState) -> AgentState:
            return {
                "memory_summary": "项目目录是 D:/python/ai-project/scholarflow",
                "turn_count": 6,
            }

        graph = StateGraph(AgentState)
        graph.add_node("write_memory", write_memory)
        graph.add_edge(START, "write_memory")
        graph.add_edge("write_memory", END)
        workflow = graph.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": "summary-test-thread"}}
        workflow.invoke({"question": "保存记忆"}, config=config)

        snapshot = workflow.get_state(config)
        assert snapshot.values["turn_count"] == 6
        assert "scholarflow" in snapshot.values["memory_summary"]
        connection.close()


def main() -> None:
    test_short_history_does_not_summarize()
    test_summary_failure_keeps_old_summary()
    test_summary_fields_persist_in_checkpoint()
    print("摘要记忆离线测试：3/3 通过")


if __name__ == "__main__":
    main()
