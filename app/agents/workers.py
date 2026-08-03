# 导入图谱内部功能节点：检索节点、工具判断节点、MCP资料搜索节点、最终回答生成节点
from app.graph.nodes import (
    answer_node,
    decide_tool_node,
    mcp_search_node,
    retrieve_node,
)
# 导入全局对话状态载体，存储整个问答流程所有中间数据
from langchain_core.documents import Document

from app.agents.diagnostics import collect_diagnostics
from app.graph.state import AgentState
# 导入工具路由决策结构化模型，定义工具调用相关字段
from app.schemas import RouteDecision
# 导入全局运行时指标单例对象，用于全项目统一采集各组件调用性能、故障、降级监控数据
from app.runtime_metrics import runtime_metrics


def knowledge_agent_node(state: AgentState) -> AgentState:
    """
    知识检索智能体主节点
    执行完整资料检索流程：向量库召回文档 → 判断是否需要MCP工具补充资料 → 执行MCP搜索，更新对话状态
    :param state: 当前对话全局状态
    :return: 合并检索、工具判断、MCP搜索结果后的全新对话状态
    """
    # 调用向量检索节点，执行RAG向量库文档召回，返回包含documents的状态更新字典
    retrieved = retrieve_node(state)
    # 浅拷贝原状态，合并检索节点输出，生成中间临时工作状态
    working_state: AgentState = {**state, **retrieved}

    # 调用工具判断节点，根据召回文档判断是否需要调用MCP外部工具
    decision_update = decide_tool_node(working_state)
    # 将工具判断结果合并进临时工作状态，供后续MCP节点读取
    working_state = {**working_state, **decision_update}

    # 初始化最终输出状态，先合并文档检索结果与工具判断结果
    result: AgentState = {
        **retrieved,
        **decision_update,
    }

    # 从工具判断结果中取出路由决策对象
    decision = decision_update.get("tool_decision")
    # 判断存在决策且标记需要使用MCP工具，执行外部资料搜索
    if decision and decision.use_mcp:
        # 调用MCP搜索节点，拉取外部补充资料
        mcp_update = mcp_search_node(working_state)
        # 判断MCP调用结果是否存在错误标识，代表外部工具拉取数据失败
        if mcp_update.get("mcp_error"):
            # 监控埋点：记录知识MCP组件触发降级兜底，统计MCP故障频次
            runtime_metrics.record_fallback("agent.knowledge_mcp")
            # 标记本轮流程整体降级，日志/监控可筛选MCP异常的请求
            mcp_update["degraded"] = True
            # 拼接完整降级原因列表，保留历史已存在的降级记录并新增本次MCP故障说明
            mcp_update["degradation_reasons"] = [
                # 读取上游已有的降级事由，兼容多环节连续降级场景
                *working_state.get("degradation_reasons", []),
                "知识MCP失败，使用Chroma证据继续回答"
            ]
        # 将MCP返回的资料、错误信息等合并进最终状态
        result.update(mcp_update)

    # 读取原有执行链路，追加当前knowledge_agent节点名，记录流程轨迹
    result["agent_trace"] = [
        *state.get("agent_trace", []),
        "knowledge_agent",
    ]
    # 返回完整检索流程后的状态，传递给下游回答节点
    return result


def report_agent_node(state: AgentState) -> AgentState:
    """
    评估报告智能体节点
    专门处理评估、报表类问题，强制调用MCP评估报表查询工具，不执行向量文档检索
    :param state: 当前对话全局状态
    :return: 携带评估报表MCP查询结果、流程轨迹的新状态
    """
    # 优先读取改写后的检索问题，无改写则使用用户原始提问，去除首尾空格
    query = state.get(
        "retrieval_question",
        state["question"],
    ).strip()
    # 手动构造工具路由决策：强制启用MCP，指定评估报表专用工具
    decision = RouteDecision(
        use_mcp=True,
        tool_name="search_evaluation_report",
        query=query,
        reason="Supervisor已把评估问题分配给报告Agent。",
    )
    # 组装临时工作状态，注入固定报表工具决策，传递给MCP搜索节点
    working_state: AgentState = {
        **state,
        "tool_decision": decision,
        "selected_tool": decision.tool_name,
        "tool_used": "report_agent",
    }
    # 执行MCP评估报表查询，获取报表数据或查询异常信息
    mcp_update = mcp_search_node(working_state)
    # 读取MCP更新结果中的错误标识，转为布尔值标记报告MCP是否调用失败
    mcp_failed = bool(mcp_update.get("mcp_error"))
    # 全局降级总标记：原有流程已降级 OR 本次报告MCP调用失败，任一成立则整体标记降级
    degraded = state.get("degraded", False) or mcp_failed
    # 复制上游已存在的降级原因列表，避免直接修改原state数据
    degradation_reasons = list(state.get("degradation_reasons", []))
    # 如果报告MCP调用失败，执行降级埋点与原因追加
    if mcp_failed:
        # 监控埋点：记录报告MCP组件触发降级，用于统计MCP接口故障率
        runtime_metrics.record_fallback("agent.report_mcp")
        # 将本次MCP故障描述追加至降级原因列表，日志可完整展示全链路异常
        degradation_reasons.append("评估报告MCP失败，无法获得报告证据")
    # 组装报告节点输出状态：清空向量文档、携带MCP报表查询全部信息、更新执行轨迹
    return {
        "documents": [], # 报表流程不使用向量检索文档，置空
        "tool_decision": decision, # 固定报表工具决策
        "selected_tool": decision.tool_name, # 当前使用的MCP工具名
        "tool_used": mcp_update.get("tool_used", "mcp_failed"), # 实际执行的工具，失败则标记mcp_failed
        "mcp_results": mcp_update.get("mcp_results", []), # MCP返回的评估报表数据列表
        "mcp_error": mcp_update.get("mcp_error", ""), # MCP查询产生的错误信息，无错误为空字符串
        "agent_trace": [
            *state.get("agent_trace", []),
            "report_agent", # 向执行链路追加报告智能体标记
        ],
        "degraded": degraded,
        "degradation_reasons": degradation_reasons,
    }


def diagnosis_agent_node(state: AgentState) -> AgentState:
    """Collect read-only system evidence for the common answer agent."""
    evidence = collect_diagnostics()
    decision = RouteDecision(
        use_mcp=False,
        tool_name="none",
        query=state.get("retrieval_question", state["question"]),
        reason="诊断Agent直接读取可信本地状态，不调用MCP。",
    )
    document = Document(
        page_content=evidence,
        metadata={
            "source_id": "scholarflow_diagnostics",
            "source_name": "ScholarFlow运行诊断",
        },
    )
    return {
        "documents": [document],
        "mcp_results": [],
        "mcp_error": "",
        "tool_decision": decision,
        "selected_tool": "diagnosis",
        "tool_used": "diagnosis",
        "agent_trace": [
            *state.get("agent_trace", []),
            "diagnosis_agent",
        ],
    }


def answer_agent_node(state: AgentState) -> AgentState:
    """
    最终回答生成节点
    接收上游knowledge_agent/report_agent的资料数据，调用大模型整合内容生成最终回复
    :param state: 携带检索文档/MCP报表数据的上游对话状态
    :return: 包含大模型回答、引用片段、完整执行轨迹的最终状态
    """
    # 调用回答生成节点，基于上游资料生成模型回答，返回回答相关状态更新
    answer_update = answer_node(state)
    # 合并回答结果，并追加当前answer_agent至执行链路
    return {
        **answer_update,
        "agent_trace": [
            *state.get("agent_trace", []),
            "answer_agent",
        ],
    }
