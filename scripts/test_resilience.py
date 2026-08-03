# 导入异步IO库，用于执行异步重试测试用例
import asyncio
# 单元测试模拟工具，用于mock模型对象，屏蔽真实大模型调用
from unittest.mock import patch

# 导入待测试的Supervisor分流节点业务函数
from app.agents.supervisor import supervisor_node
# 导入知识Agent，验证MCP降级时能保留上游完整降级链
from app.agents.workers import knowledge_agent_node
# 导入回答节点业务函数
from app.graph.nodes import answer_node, decide_tool_node
# 导入同步、异步两套重试核心工具函数
from app.resilience import run_async_with_retry, run_with_retry
# 导入全局运行时监控指标单例，校验埋点统计逻辑
from app.runtime_metrics import runtime_metrics
# 导入工具路由结构，构造不调用真实Qwen的MCP测试决策
from app.schemas import RouteDecision


# 自定义断言封装函数，简化测试校验逻辑
def check(condition: bool, message: str) -> None:
    # 校验条件不成立时抛出断言错误，携带错误描述
    if not condition:
        raise AssertionError(message)


# 测试同步重试：首次失败、第二次执行成功的场景
def test_sync_retry_then_success() -> None:
    # 记录函数执行次数计数器
    attempts = 0

    # 定义待重试的同步业务函数
    def operation() -> str:
        nonlocal attempts
        # 每次执行计数+1
        attempts += 1
        # 第一次执行主动抛出网络异常，模拟调用失败
        if attempts == 1:
            raise ConnectionError("模拟第一次网络失败")
        # 第二次正常返回结果
        return "ok"

    # 调用同步重试执行器，限定最大尝试2次
    result = run_with_retry(
        operation,
        component="test.sync_success",
        max_attempts=2,
    )
    # 校验最终返回结果正确
    check(result == "ok", "同步重试后没有返回成功结果")
    # 校验总共执行2次（1次失败+1次成功）
    check(attempts == 2, "同步操作尝试次数不正确")


# 测试同步重试：所有尝试全部失败，最终抛出原始异常
def test_sync_final_failure() -> None:
    attempts = 0

    # 持续抛出超时异常的业务函数
    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise TimeoutError("模拟持续超时")

    try:
        # 最大尝试2次，必然全部失败
        run_with_retry(
            operation,
            component="test.sync_failure",
            max_attempts=2,
        )
    except TimeoutError:
        # 捕获预期异常，测试正常往下走
        pass
    else:
        # 未抛出异常则测试失败
        raise AssertionError("最终失败没有向上抛出")

    # 校验完整执行2次重试逻辑
    check(attempts == 2, "最终失败尝试次数不正确")


# 异步测试用例：校验单次异步操作超时机制是否生效
async def _run_async_timeout_case() -> None:
    # 执行耗时超过超时阈值的异步函数
    async def slow_operation() -> str:
        # 休眠0.2秒，远大于设定的0.01s超时
        await asyncio.sleep(0.2)
        return "不应返回"

    try:
        # 仅允许1次执行，单次超时0.01秒
        await run_async_with_retry(
            slow_operation,
            component="test.async_timeout",
            timeout_seconds=0.01,
            max_attempts=1,
        )
    except TimeoutError:
        # 捕获预期超时异常，测试通过直接return
        return
    # 未触发超时则测试失败
    raise AssertionError("异步操作没有按时超时")


def test_async_timeout() -> None:
    asyncio.run(_run_async_timeout_case())


# 模拟持续报错的结构化模型类，用于mock替换真实chat_model/fast_model
class FailingStructuredModel:
    # 链式方法with_structured_output直接返回自身，保持调用链兼容
    def with_structured_output(self, _schema):
        return self

    # 执行推理时固定抛出超时异常，模拟模型服务故障
    def invoke(self, _prompt):
        raise TimeoutError("模拟Qwen持续超时")


class SuccessfulRouteModel:
    def with_structured_output(self, _schema):
        return self

    def invoke(self, _prompt):
        return RouteDecision(
            use_mcp=False,
            tool_name="none",
            query="RAG是什么？",
            reason="普通知识问题使用向量检索",
        )


def test_tool_router_success_returns_mapping() -> None:
    with patch(
        "app.graph.nodes.chat_model",
        return_value=SuccessfulRouteModel(),
    ):
        result = decide_tool_node(
            {
                "question": "RAG是什么？",
                "retrieval_question": "RAG是什么？",
                "documents": [],
            }
        )

    check(isinstance(result, dict), "工具路由成功分支没有返回字典")
    check(result["selected_tool"] == "none", "工具路由成功结果不正确")
    check(result["tool_used"] == "rag_only", "工具使用状态不正确")


# 测试Supervisor分流节点模型失败后的关键词降级逻辑
def test_supervisor_fallback() -> None:
    # 使用patch替换fast_model，返回报错模拟模型，不调用真实大模型
    with patch(
        "app.agents.supervisor.fast_model",
        return_value=FailingStructuredModel(),
    ):
        # 执行分流节点，传入基础对话状态
        result = supervisor_node(
            {
                "question": "最近评估通过率是多少？",
                "agent_trace": [],
                "degradation_reasons": ["上游已有降级"],
            }
        )

    # 校验流程标记为降级
    check(result["degraded"] is True, "Supervisor没有标记降级")
    # 校验降级关键词路由正确分配至报表Agent
    check(
        result["supervisor_decision"].next_agent == "report_agent",
        "Supervisor关键词回退路由不正确",
    )
    check(
        result["degradation_reasons"]
        == ["上游已有降级", "Supervisor模型失败，使用关键词分流"],
        "Supervisor覆盖了上游降级原因",
    )


# 测试回答节点模型调用失败后的兜底结构化回答降级逻辑
def test_answer_fallback() -> None:
    # mock替换chat_model为持续报错的模拟模型
    with patch(
        "app.graph.nodes.chat_model",
        return_value=FailingStructuredModel(),
    ):
        # 执行回答节点，传入基础状态
        result = answer_node(
            {
                "question": "RAG是什么？",
                "documents": [],
                "mcp_results": [],
                "degradation_reasons": ["上游已有降级"],
            }
        )

    # 校验全局降级标记开启
    check(result["degraded"] is True, "Answer没有标记降级")
    # 校验兜底回答置信度为0
    check(result["answer"].confidence == 0.0, "兜底回答置信度不是0")
    # 校验兜底回答携带故障说明
    check(bool(result["answer"].missing_information), "兜底回答缺少错误说明")
    check(
        result["degradation_reasons"]
        == ["上游已有降级", "回答模型失败，返回结构化兜底答案"],
        "Answer覆盖了上游降级原因",
    )


# 验证知识Agent的MCP失败会追加原因，而不是覆盖上游已有原因
def test_knowledge_mcp_fallback_chain() -> None:
    decision = RouteDecision(
        use_mcp=True,
        tool_name="search_local_knowledge",
        query="MCP是什么？",
        reason="测试MCP降级",
    )
    with (
        patch(
            "app.agents.workers.retrieve_node",
            return_value={"documents": []},
        ),
        patch(
            "app.agents.workers.decide_tool_node",
            return_value={
                "tool_decision": decision,
                "selected_tool": decision.tool_name,
                "tool_used": "mcp_auto",
            },
        ),
        patch(
            "app.agents.workers.mcp_search_node",
            return_value={
                "mcp_results": [],
                "tool_used": "mcp_failed",
                "mcp_error": "模拟MCP超时",
            },
        ),
    ):
        result = knowledge_agent_node(
            {
                "question": "MCP是什么？",
                "agent_trace": ["supervisor"],
                "degraded": True,
                "degradation_reasons": ["上游已有降级"],
            }
        )

    check(result["degraded"] is True, "Knowledge MCP失败没有标记降级")
    check(
        result["degradation_reasons"]
        == ["上游已有降级", "知识MCP失败，使用Chroma证据继续回答"],
        "Knowledge MCP覆盖了上游降级原因",
    )


# 测试runtime_metrics指标埋点统计逻辑是否准确
def test_metrics() -> None:
    # 获取全量监控快照数据
    snapshot = runtime_metrics.snapshot()
    # 提取同步成功用例的指标统计
    success = snapshot["test.sync_success"]
    # 提取同步全部失败用例的指标统计
    failure = snapshot["test.sync_failure"]

    # 校验总调用次数、成功次数、重试次数统计
    check(success["calls"] == 1, "成功调用统计不正确")
    check(success["successes"] == 1, "成功次数统计不正确")
    check(success["retries"] == 1, "重试次数统计不正确")
    # 校验失败次数统计
    check(failure["failures"] == 1, "失败次数统计不正确")
    # 校验Supervisor模型降级计数为1
    check(
        snapshot["model.supervisor"]["fallbacks"] == 1,
        "Supervisor降级次数统计不正确",
    )
    # 校验回答模型降级计数为1
    check(
        snapshot["model.answer"]["fallbacks"] == 1,
        "Answer降级次数统计不正确",
    )
    check(
        snapshot["agent.knowledge_mcp"]["fallbacks"] == 1,
        "Knowledge MCP降级次数统计不正确",
    )


# 主测试执行入口，顺序运行所有测试用例并打印通过日志
def main() -> None:
    # 执行所有测试前重置监控指标，清空历史数据避免干扰校验
    runtime_metrics.reset()
    # 执行同步单次失败重试成功用例
    test_sync_retry_then_success()
    print("同步失败后重试成功：通过")
    # 执行同步全部失败抛出异常用例
    test_sync_final_failure()
    print("达到最大次数后停止：通过")
    # 异步运行异步超时测试用例
    test_async_timeout()
    print("异步单次超时：通过")
    test_tool_router_success_returns_mapping()
    print("工具路由成功分支返回状态：通过")
    # 执行Supervisor模型降级测试
    test_supervisor_fallback()
    print("Supervisor最终失败关键词降级：通过")
    # 执行回答模型兜底降级测试
    test_answer_fallback()
    print("Answer最终失败结构化降级：通过")
    test_knowledge_mcp_fallback_chain()
    print("Knowledge MCP失败保留完整降级链：通过")
    # 校验所有监控指标埋点统计结果
    test_metrics()
    print("调用、失败、重试与降级指标：通过")
    print("测试未调用真实Qwen和MCP：通过")


# 脚本直接运行时启动全套测试
if __name__ == "__main__":
    main()
