# 单元测试Mock工具，用于模拟图内节点，屏蔽真实大模型、MCP接口调用
from unittest.mock import patch

# 导入分流总控节点Supervisor
from app.agents.supervisor import supervisor_node
# 导入三个业务工作Agent节点：知识检索、评估报告、最终回答生成
from app.agents.workers import (
    answer_agent_node,
    knowledge_agent_node,
    report_agent_node,
)
# 导入流程图构建函数、Supervisor后的分支路由判断函数
from app.graph.builder import build_graph, route_after_supervisor
# 导入各类结构化Pydantic模型：回答输出、工具路由、分流决策
from app.schemas import ResearchAnswer, RouteDecision, SupervisorDecision


# 通用断言封装函数，统一测试校验逻辑，失败抛出带提示的断言错误
def check(condition: bool, message: str) -> None:
    # 条件不成立，抛出错误并携带自定义提示文本
    if not condition:
        raise AssertionError(message)


# 测试用例1：校验Supervisor前缀强制分流逻辑 [REPORT]/[KNOWLEDGE]
def test_supervisor_forced_routes() -> None:
    # 传入带[REPORT]标记的提问，执行分流节点，初始链路为空
    report = supervisor_node(
        {"question": "[REPORT] 最近评估通过率是多少？", "agent_trace": []}
    )
    # 传入带[KNOWLEDGE]标记的提问，执行分流节点，初始链路为空
    knowledge = supervisor_node(
        {"question": "[KNOWLEDGE] RAG是什么？", "agent_trace": []}
    )

    # 校验REPORT前缀强制路由到report_agent
    check(
        report["supervisor_decision"].next_agent == "report_agent",
        "REPORT前缀没有进入报告Agent",
    )
    # 校验KNOWLEDGE前缀强制路由到knowledge_agent
    check(
        knowledge["supervisor_decision"].next_agent == "knowledge_agent",
        "KNOWLEDGE前缀没有进入知识Agent",
    )
    # 校验执行链路自动追加supervisor标记
    check(report["agent_trace"] == ["supervisor"], "监督轨迹不正确")


# 测试用例2：校验Supervisor后的条件路由函数逻辑，含空决策兜底
def test_route_function() -> None:
    # 构造携带报告Agent分流决策的状态字典
    state = {
        "supervisor_decision": SupervisorDecision(
            next_agent="report_agent",
            reason="测试",
        )
    }
    # 路由函数正常读取决策，返回report_agent
    check(
        route_after_supervisor(state) == "report_agent",
        "条件边没有读取监督决策",
    )
    # 状态无分流决策时，兜底返回knowledge_agent
    check(
        route_after_supervisor({}) == "knowledge_agent",
        "空决策没有回退到知识Agent",
    )


# 测试用例3：校验三个业务Agent完整执行逻辑，Mock屏蔽真实大模型与MCP调用
def test_worker_nodes_without_qwen() -> None:
    # 构造工具决策：无需调用MCP外部工具，仅本地RAG检索
    no_tool = RouteDecision(
        use_mcp=False,
        tool_name="none",
        query="RAG是什么",
        reason="普通知识问题",
    )
    # 多重Mock：模拟retrieve_node向量检索、decide_tool_node工具判断节点返回固定值
    with (
        patch(
            "app.agents.workers.retrieve_node",
            return_value={"documents": []},
        ),
        patch(
            "app.agents.workers.decide_tool_node",
            return_value={
                "tool_decision": no_tool,
                "selected_tool": "none",
                "tool_used": "rag_only",
            },
        ),
    ):
        # 执行知识检索Agent，传入已执行supervisor的链路记录
        knowledge = knowledge_agent_node(
            {"question": "RAG是什么", "agent_trace": ["supervisor"]}
        )

    # 校验知识Agent执行链路正确追加节点名称
    check(
        knowledge["agent_trace"] == ["supervisor", "knowledge_agent"],
        "知识Agent轨迹不正确",
    )

    # Mock MCP搜索节点，拦截真实外部报表接口调用
    with patch(
        "app.agents.workers.mcp_search_node",
        return_value={
            "mcp_results": [],
            "tool_used": "mcp",
            "mcp_error": "",
        },
    ) as mocked_mcp:
        # 执行报告Agent，传入已执行supervisor的链路记录
        report = report_agent_node(
            {
                "question": "最近通过率是多少",
                "agent_trace": ["supervisor"],
            }
        )

    # 校验报告Agent一定会调用MCP搜索节点一次
    check(mocked_mcp.call_count == 1, "报告Agent没有调用MCP节点")
    # 校验报告Agent强制选择评估报表专用工具
    check(
        report["selected_tool"] == "search_evaluation_report",
        "报告Agent工具选择不正确",
    )
    # 校验报告Agent执行链路正确追加节点名称
    check(
        report["agent_trace"] == ["supervisor", "report_agent"],
        "报告Agent轨迹不正确",
    )

    # 构造模拟最终回答结构化数据，替代真实大模型输出
    fake_answer = ResearchAnswer(
        answer="测试回答",
        citations=[],
        confidence=0.8,
        missing_information=[],
    )
    # Mock回答生成节点，拦截真实LLM调用
    with patch(
        "app.agents.workers.answer_node",
        return_value={"answer": fake_answer, "history": []},
    ):
        # 执行最终回答Agent，传入上游supervisor+report_agent的链路
        answered = answer_agent_node(
            {"question": "测试", "agent_trace": ["supervisor", "report_agent"]}
        )

    # 校验完整链路：分流→报表→回答Agent全部记录
    check(
        answered["agent_trace"]
        == ["supervisor", "report_agent", "answer_agent"],
        "回答Agent轨迹不正确",
    )


# 测试用例4：校验LangGraph流程图完整节点结构，确保所有节点均已注册
def test_graph_structure() -> None:
    # 构建完整流程图，提取图中所有节点名称转为集合
    node_names = set(build_graph().get_graph().nodes)
    # 定义预期必须存在的全部节点
    expected = {
        "rewrite_question",
        "supervisor",
        "knowledge_agent",
        "report_agent",
        "answer_agent",
    }
    # 校验预期节点全部存在于流程图中
    check(expected.issubset(node_names), "多Agent图缺少必要节点")


# 自动化测试统一入口，顺序执行全部测试用例
def main() -> None:
    # 执行强制分流测试
    test_supervisor_forced_routes()
    print("Supervisor强制路由：通过")
    # 执行路由函数兜底逻辑测试
    test_route_function()
    print("Supervisor条件边与回退：通过")
    # 执行三个业务Agent完整链路测试
    test_worker_nodes_without_qwen()
    print("三个专职Agent与执行轨迹：通过")
    # 执行流程图节点完整性校验
    test_graph_structure()
    print("LangGraph多Agent结构：通过")
    print("测试未调用真实Qwen：通过")


# 脚本直接运行时，自动执行全套Agent自动化测试，全程Mock不消耗大模型额度
if __name__ == "__main__":
    main()