# 单元测试mock工具，用于模拟RAG工作流，不真实调用大模型API
from unittest.mock import patch
# UUID生成工具，生成测试对话线程ID
from uuid import uuid4

# FastAPI测试客户端，模拟HTTP请求调用接口
from fastapi.testclient import TestClient

# 导入项目FastAPI应用实例
from app.api import app
# 项目全局配置对象，临时修改限流开关、阈值，测试后恢复原值
from app.config import settings
# 导入两套限流器：全局IP限流器、问答用户专属限流器
from app.rate_limit import ask_rate_limiter, global_rate_limiter

# 全局测试客户端，复用app实例发起接口请求
client = TestClient(app)

# 通用断言封装工具，简化测试判断逻辑，失败抛出可读断言错误
def check(condition: bool, message: str) -> None:
    # 条件不成立则抛出断言异常，附带自定义错误描述
    if not condition:
        raise AssertionError(message)

# 测试用例1：全局IP粒度接口限流功能
def test_ip_rate_limit() -> None:
    # 清空限流器历史计数，隔离本次测试数据
    global_rate_limiter.reset()
    # 保存配置原始限流开关状态，测试结束还原
    original_enabled = settings.rate_limit_enabled
    # 保存原始全局单窗口最大请求次数，测试结束还原
    original_limit = settings.rate_limit_max_requests

    try:
        # 临时开启限流功能
        settings.rate_limit_enabled = True
        # 临时设置单窗口最大允许2次请求
        settings.rate_limit_max_requests = 2

        # 第一次调用健康检查接口，预期放行
        first = client.get("/health")
        # 第二次调用健康检查接口，窗口额度未耗尽，放行
        second = client.get("/health")
        # 第三次调用，超过窗口2次上限，触发429限流拦截
        blocked = client.get("/health")

        # 校验第一次请求状态码200
        check(first.status_code == 200, "第1次健康检查应该成功")
        # 校验第二次请求状态码200
        check(second.status_code == 200, "第2次健康检查应该成功")
        # 校验第三次请求返回429请求频繁
        check(blocked.status_code == 429, "第3次请求应该返回429")
        # 校验429响应携带Retry-After标准头
        check("Retry-After" in blocked.headers, "429响应缺少Retry-After")
        # 校验返回的错误提示文本和业务定义一致
        check(
            blocked.json()["detail"] == "请求过于频繁，请稍后重试",
            "429响应内容不正确",
        )
    finally:
        # 无论测试成功/失败，恢复配置原始限流开关
        settings.rate_limit_enabled = original_enabled
        # 恢复原始全局请求上限配置
        settings.rate_limit_max_requests = original_limit
        # 清空限流器计数，不污染其他测试用例
        global_rate_limiter.reset()

# 测试用例2：登录用户粒度问答接口限流，mock屏蔽真实大模型调用
def test_ask_user_rate_limit_without_qwen() -> None:
    # 清空两套限流器历史计数，隔离测试数据
    global_rate_limiter.reset()
    ask_rate_limiter.reset()
    # 保存配置原始参数，用于测试结束还原
    original_enabled = settings.rate_limit_enabled
    original_global_limit = settings.rate_limit_max_requests
    original_ask_limit = settings.ask_rate_limit_max_requests

    try:
        # 临时开启限流总开关
        settings.rate_limit_enabled = True
        # 全局IP限流阈值设为100，避免IP限流干扰问答用户限流测试
        settings.rate_limit_max_requests = 100
        # 问答接口单用户窗口最大1次提问，第二次直接拦截
        settings.ask_rate_limit_max_requests = 1

        # 创建空登录会话，获取短期access_token鉴权令牌
        session_response = client.post("/sessions")
        # 校验会话创建成功
        check(session_response.status_code == 200, "创建测试会话失败")
        # 提取会话返回的access_token
        token = session_response.json()["access_token"]
        # 组装Bearer鉴权请求头，用于问答接口调用
        headers = {"Authorization": f"Bearer {token}"}

        # 模拟问答工作流返回的假结果，不调用真实LangGraph与大模型中转API
        fake_result = {
            "answer": {
                "answer": "这是自动测试回答",
                "citations": [],
            }
        }
        # 问答接口请求体：测试提问+随机对话线程ID
        body = {
            "question": "测试限流，不调用真实Qwen",
            "thread_id": str(uuid4()),
        }

        # 使用patch mock覆盖memory_workflow.invoke方法，固定返回假回答
        with patch(
            "app.api.memory_workflow.invoke",
            return_value=fake_result,
        ) as mocked_invoke:
            # 第一次提问，未达上限，正常放行
            first = client.post("/ask", json=body, headers=headers)
            # 第二次提问，达到单用户1次阈值，触发429限流拦截
            blocked = client.post("/ask", json=body, headers=headers)

        # 校验第一次问答请求成功200
        check(first.status_code == 200, "第1次问答应该成功")
        # 校验第二次问答被用户限流拦截返回429
        check(blocked.status_code == 429, "第2次问答应该被用户限流")
        # 校验限流响应携带Retry-After头
        check("Retry-After" in blocked.headers, "问答429缺少Retry-After")
        # 校验mock的问答执行函数仅被调用1次，被拦截的请求不会进入Agent逻辑
        check(mocked_invoke.call_count == 1, "被限流请求不应调用Agent")
    finally:
        # 恢复所有限流配置为原始值，不污染项目正式配置
        settings.rate_limit_enabled = original_enabled
        settings.rate_limit_max_requests = original_global_limit
        settings.ask_rate_limit_max_requests = original_ask_limit
        # 清空两套限流器计数
        global_rate_limiter.reset()
        ask_rate_limiter.reset()

# 自动化测试入口主函数，依次执行两套限流测试用例
def main() -> None:
    # 执行IP全局限流测试
    test_ip_rate_limit()
    print("IP通用限流：通过")

    # 执行问答用户粒度限流测试
    test_ask_user_rate_limit_without_qwen()
    print("用户问答限流：通过")
    print("429响应与Retry-After：通过")
    print("被限流请求不调用Qwen：通过")

# 脚本直接运行时，自动执行全部限流自动化测试
if __name__ == "__main__":
    main()