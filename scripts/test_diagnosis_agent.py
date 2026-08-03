from unittest.mock import patch

from app.agents.diagnostics import collect_diagnostics
from app.agents.supervisor import supervisor_node
from app.agents.workers import diagnosis_agent_node


def main() -> None:
    forced = supervisor_node(
        {"question": "[DIAGNOSIS] 当前系统状态", "agent_trace": []}
    )
    assert forced["supervisor_decision"].next_agent == "diagnosis_agent"

    with patch(
        "app.agents.workers.collect_diagnostics",
        return_value="通用评估：20/20；运行指标：无失败",
    ):
        result = diagnosis_agent_node(
            {"question": "系统状态", "agent_trace": ["supervisor"]}
        )
    assert result["tool_used"] == "diagnosis"
    assert result["agent_trace"] == ["supervisor", "diagnosis_agent"]
    assert "20/20" in result["documents"][0].page_content

    evidence = collect_diagnostics()
    assert "数据文件状态" in evidence
    assert "评估报告状态" in evidence
    assert "运行指标" in evidence
    print("诊断Agent离线测试：3/3 通过")


if __name__ == "__main__":
    main()
