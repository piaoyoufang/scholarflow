# 在 LangGraph 中，AgentState 就像是整个工作流的共享内存或全局变量。它规定了数据在不同节点（如检索、生成答案）之间流转时，必须包含哪些信息。
from typing import Annotated,Any, TypedDict

from langchain_core.documents import Document

from app.schemas import ResearchAnswer, RouteDecision, SupervisorDecision

# 对话历史归约函数 keep_recent_history
def keep_recent_history(
    existing: list[dict[str, str]], # 状态里已经存在的旧对话历史列表
    new: list[dict[str, str]], # 节点本次新生成、要追加进去的对话消息列表返回：裁剪后的完整历史列表
) -> list[dict[str, str]]:
    """合并新对话，只保留最近 12 条消息，也就是最多 6 轮。"""
    return (existing + new)[-12:]

class AgentState(TypedDict, total=False):
    question: str # 用户原始问题
    retrieval_question: str # AI 路由决策优化后的专用检索问句，专门传给 Chroma 检索、MCP 工具检索；
    history: Annotated[list[dict[str, str]], keep_recent_history] # LangGraph 专属绑定：每次节点写入 history 字段时，自动调用上面的归约函数,不写 Annotated：state["history"] = new_messages → 直接覆盖，旧历史全部丢失
    documents: list[Document] # Chroma 召回的文档片段
    tool_decision: RouteDecision # MCP 路由决策模型（AI 判断是否调用 MCP）
    selected_tool: str  # Qwen 最终选择的 MCP 工具名
    tool_used: str # 记录最后到底用了什么工具，方便调试
    mcp_results: list[dict[str, Any]] # MCP 工具返回的结果
    mcp_error: str # MCP 调用失败时保存错误，不让整个 Agent 崩掉
    answer: ResearchAnswer # Qwen 最终输出的带引用、置信度的答案 JSON 模型
    error: str # 错误信息
    # 存储路由 Supervisor 分流决策结构化对象，包含下一步执行Agent标识与分流理由
    supervisor_decision: SupervisorDecision
    # 存储本次对话全流程执行过的Agent名称列表，用于链路追踪、日志统计
    agent_trace: list[str]
    # 标记本轮问答流程是否触发降级兜底逻辑（True=走降级分支，False=正常LLM执行成功）
    degraded: bool
    # 存储所有触发降级的原因文本列表，可记录多条异常/降级事由用于日志排查
    degradation_reasons: list[str]
