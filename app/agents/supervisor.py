# 导入对话状态定义类，存储全流程会话数据
from app.graph.state import AgentState
# 导入高速轻量大模型实例，用于执行分流决策推理
from app.models import fast_model
# 导入分流决策结构化输出模型，约束LLM返回固定格式结果
from app.schemas import SupervisorDecision
# 导入同步重试工具函数，提供指数退避重试、异常捕获、性能指标自动埋点能力
from app.resilience import run_with_retry
# 导入全局运行时指标单例，用于记录各组件调用次数、耗时、成败、重试、降级等监控数据
from app.runtime_metrics import runtime_metrics


def _fallback_decision(question: str) -> SupervisorDecision:
    """
    LLM调用失败时的降级关键词分流函数
    当结构化输出报错、模型超时/异常时，通过关键词规则强制分流，保障流程不中断
    :param question: 用户检索/原始提问文本
    :return: 标准化分流决策对象
    """
    # 定义报告Agent触发关键词元组，命中任意词直接走报告流程
    report_markers = (
        "评估",
        "报告",
        "通过率",
        "失败题",
        "未通过",
        "eval_report",
        "mcp_eval_report",
    )
    diagnosis_markers = (
        "系统状态",
        "健康状态",
        "运行指标",
        "降级次数",
        "失败次数",
        "系统诊断",
        "数据库状态",
    )
    # 遍历关键词匹配，命中则路由至报告Agent，否则路由至知识检索Agent
    if any(marker in question for marker in diagnosis_markers):
        next_agent = "diagnosis_agent"
    elif any(marker in question for marker in report_markers):
        next_agent = "report_agent"
    else:
        next_agent = "knowledge_agent"
    # 组装降级分流决策，标记降级触发原因
    return SupervisorDecision(
        next_agent=next_agent,
        reason="Supervisor结构化输出失败，使用关键词规则回退。",
    )


def supervisor_node(state: AgentState) -> AgentState:
    """
    总控分流节点 Supervisor
    负责判断用户需求，自动分配至知识检索Agent或报告生成Agent
    支持用户指令前缀强制分流、LLM智能分流、关键词降级分流三层兜底逻辑
    :param state: 当前对话全量状态数据
    :return: 更新后的对话状态，写入分流决策与执行链路追踪
    """
    # 取出并清理用户原始提问，去除首尾空格
    original_question = state["question"].strip()
    # 优先读取检索专用改写问题，无改写问题则使用原始提问，清理首尾空格
    question = state.get(
        "retrieval_question",
        original_question,
    ).strip()

    # 显式诊断前缀优先，便于稳定测试诊断图分支。
    if original_question.startswith("[DIAGNOSIS]"):
        decision = SupervisorDecision(
            next_agent="diagnosis_agent",
            reason="用户使用[DIAGNOSIS]前缀强制进入诊断Agent。",
        )
    # 分支1：用户输入带[REPORT]前缀，强制走报告生成Agent
    elif original_question.startswith("[REPORT]"):
        decision = SupervisorDecision(
            next_agent="report_agent",
            reason="用户使用[REPORT]前缀强制进入报告Agent。",
        )
    # 分支2：用户输入带[KNOWLEDGE]前缀，强制走知识检索Agent
    elif original_question.startswith("[KNOWLEDGE]"):
        decision = SupervisorDecision(
            next_agent="knowledge_agent",
            reason="用户使用[KNOWLEDGE]前缀强制进入知识Agent。",
        )
    # 分支3：无强制前缀，调用轻量LLM智能判断分流方向
    else:
        # 构造给Supervisor大模型的系统提示词，明确分流规则与两类Agent职责
        prompt = f"""你是 ScholarFlow 的 Supervisor Agent。
你只负责分流，不回答问题，也不调用工具。

可选Agent：
1. knowledge_agent：课程资料、RAG、Embedding、向量库、LangGraph、MCP概念。
2. report_agent：评估CSV、通过率、失败题、未通过原因、最近评估结果。
3. diagnosis_agent：系统健康、数据库文件、运行指标、失败重试和整体评估状态。

用户原始问题：
{original_question}

用于路由的独立问题：
{question}
"""
        try:
            # 调用同步重试包装器执行Supervisor分流大模型推理，自动处理失败重试并采集监控指标
            decision = run_with_retry(
                # 匿名lambda函数，封装完整的轻量模型结构化推理逻辑
                lambda: (
                    # 获取轻量高速分流大模型实例
                    fast_model()
                    # 约束LLM输出必须匹配SupervisorDecision结构化模型，避免乱输出
                    .with_structured_output(SupervisorDecision)
                    # 传入分流提示词prompt，执行大模型推理得到分流决策
                    .invoke(prompt)
                ),
                # 标记当前执行业务组件名称，用于runtime_metrics区分监控指标
                component="model.supervisor",
            )
        # 捕获Supervisor大模型调用全量异常（超时、解析失败、接口报错等）
        except Exception:
            # 指标埋点：记录model.supervisor组件触发了降级兜底逻辑
            runtime_metrics.record_fallback("model.supervisor")
            # 执行关键词规则降级分流，替代LLM智能判断
            decision = _fallback_decision(question)
            # 返回更新后的对话状态字典
            return {
                # 写入降级模式生成的分流决策对象
                "supervisor_decision": decision,
                # 标记本轮流程触发降级，供日志/监控识别异常链路
                "degraded": True,
                # 写入降级原因文本，用于问题排查
                "degradation_reasons": [
                    *state.get("degradation_reasons", []),
                    "Supervisor模型失败，使用关键词分流",
                ],
                # 读取原有执行轨迹，追加当前supervisor节点名称，完整记录流程链路
                "agent_trace": [
                    *state.get("agent_trace", []),
                    "supervisor",
                ],
            }

    # 返回更新后的对话状态字典
    return {
        # 写入本次分流决策结果，供后续流程读取路由方向
        "supervisor_decision": decision,
        # 读取原有Agent执行链路，追加当前supervisor节点名称，记录执行轨迹
        "agent_trace": [
            *state.get("agent_trace", []),
            "supervisor",
        ],
    }
