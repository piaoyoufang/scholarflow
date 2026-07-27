# 导入警告过滤工具，屏蔽Starlette版本兼容无关告警
import warnings
# 路径工具类，用于临时数据库文件路径管理
from pathlib import Path
# 临时目录工具，测试结束自动销毁文件夹，无sqlite文件残留
from tempfile import TemporaryDirectory
# 简单命名空间对象，模拟LangGraph工作流返回状态对象
from types import SimpleNamespace
# UUID生成工具，生成唯一测试用户名、对话线程ID
from uuid import uuid4

# Starlette框架弃用警告类型，用于精准过滤无关测试告警
from starlette.exceptions import StarletteDeprecationWarning

# 注释说明：FastAPI TestClient测试时会弹出无关兼容性提示，不影响业务测试结果，直接屏蔽
warnings.filterwarnings("ignore", category=StarletteDeprecationWarning)

# FastAPI内置测试客户端，模拟HTTP请求调用后端所有接口，无需启动真实服务
from fastapi.testclient import TestClient

# 导入后端api总入口模块，用于替换全局依赖、加载app实例
from app import api as api_module
# 导入完整账号认证存储类，包含注册、登录、双Token刷新、注销、线程权限逻辑
from app.security import AuthStore

# 全局测试固定密码，所有测试账号统一使用该密码
TEST_PASSWORD = "ScholarFlow123"


class FakeWorkflow:
    """
    假RAG工作流模拟类
    测试权限流程时，替代真实LangGraph+Qwen大模型，不会调用付费中转API，节省测试成本
    """
    # 模拟问答执行方法，固定返回测试用回答与空引用资料
    def invoke(self, inputs: dict, config: dict) -> dict:
        return {
            "answer": {
                "answer": "账号自动测试回答",
                "citations": [],
                "confidence": 1.0,
                "missing_information": [],
            }
        }
    # 模拟获取对话状态方法，返回空命名空间，规避真实数据库/模型依赖
    def get_state(self, config: dict) -> SimpleNamespace:
        return SimpleNamespace(values={})


def expect_status(response, expected: int, test_name: str) -> None:
    """
    通用接口状态码断言工具
    校验接口返回状态码与预期一致，不一致则打印完整报错信息，终止当前测试用例
    :param response: TestClient接口返回的响应对象
    :param expected: 预期HTTP状态码（200/201/401/409等）
    :param test_name: 当前测试用例名称，用于报错定位
    """
    assert response.status_code == expected, (
        f"{test_name}失败：预期状态码 {expected}，"
        f"实际状态码 {response.status_code}，响应内容 {response.text}"
    )


def bearer(access_token: str) -> dict[str, str]:
    """
    快速生成Bearer鉴权请求头工具函数
    所有需要登录鉴权的接口请求统一调用，减少重复代码
    :param access_token: 短期业务鉴权令牌明文
    :return: 标准Authorization请求头字典
    """
    return {"Authorization": f"Bearer {access_token}"}


def main() -> None:
    """
    全套账号生命周期自动化测试主函数
    覆盖10项核心测试：注册、重复注册、密码错误登录、正常登录、线程绑定、Token刷新、旧刷新令牌作废、跨刷新线程权限、账号注销、注销后令牌全部失效
    使用临时sqlite数据库，测试结束自动销毁，不污染生产/开发库
    """
    # 创建系统临时文件夹，代码块执行完毕自动删除整个目录，释放sqlite文件锁
    with TemporaryDirectory() as directory:
        # 实例化独立测试用认证存储，数据库存放于临时目录，隔离正式业务数据
        test_store = AuthStore(Path(directory) / "account-test.sqlite")

        # 保存api模块原始全局对象，测试完成后必须恢复，避免污染真实业务逻辑
        original_store = api_module.auth_store
        original_workflow = api_module.memory_workflow

        try:
            # 全局依赖替换：将后端正式认证库、真实RAG工作流替换为测试专用实例
            api_module.auth_store = test_store
            api_module.memory_workflow = FakeWorkflow()

            # 创建FastAPI测试客户端，加载项目app实例，模拟完整HTTP请求链路
            with TestClient(api_module.app) as client:
                # 生成随机唯一测试用户名，每次运行测试名称不同，规避重复注册冲突
                username = f"student_{uuid4().hex[:8]}"

                # ========== 测试用例1：新账号注册，预期返回201资源创建状态码，返回完整双Token结构 ==========
                register_response = client.post(
                    "/auth/register",
                    json={
                        "username": username,
                        "password": TEST_PASSWORD,
                    },
                )
                # 校验注册接口状态码必须为201
                expect_status(register_response, 201, "注册新账号")
                # 解析注册接口返回的账号会话JSON数据
                registered = register_response.json()

                # 定义合法会话必须包含的全部5个核心字段
                required_keys = {
                    "user_id",
                    "access_token",
                    "expires_at",
                    "refresh_token",
                    "refresh_expires_at",
                }
                # 校验返回数据包含所有必填字段，缺字段直接断言失败
                assert required_keys.issubset(registered), (
                    "注册响应缺少账号或双Token字段"
                )
                print("1. 注册成功并返回完整双 Token：通过")

                # ========== 测试用例2：重复注册同名账号，预期返回409冲突 ==========
                duplicate_response = client.post(
                    "/auth/register",
                    json={
                        "username": username,
                        "password": TEST_PASSWORD,
                    },
                )
                expect_status(duplicate_response, 409, "重复用户名")
                print("2. 重复用户名返回 409：通过")

                # ========== 测试用例3：正确用户名+错误密码登录，预期返回401未授权 ==========
                wrong_password_response = client.post(
                    "/auth/login",
                    json={
                        "username": username,
                        "password": "WrongPassword123",
                    },
                )
                expect_status(wrong_password_response, 401, "错误密码登录")
                print("3. 错误密码返回 401：通过")

                # ========== 测试用例4：正确账号密码登录，校验user_id不变、下发全新access_token ==========
                login_response = client.post(
                    "/auth/login",
                    json={
                        "username": username,
                        "password": TEST_PASSWORD,
                    },
                )
                expect_status(login_response, 200, "正确密码登录")
                logged_in = login_response.json()
                # 校验登录后的用户ID和注册时完全一致，不会变更账号主体
                assert logged_in["user_id"] == registered["user_id"], (
                    "同一账号登录后 user_id 发生变化"
                )
                # 校验重新登录会生成全新短期access_token，和注册时令牌不重复
                assert logged_in["access_token"] != registered["access_token"], (
                    "重新登录应该创建新的 Access Token"
                )
                print("4. 正确登录且 user_id 保持不变：通过")

                # ========== 测试用例5：使用登录access_token发起问答，绑定对话线程归属当前用户 ==========
                thread_id = str(uuid4())
                ask_response = client.post(
                    "/ask",
                    headers=bearer(logged_in["access_token"]),
                    json={
                        "question": "这是账号权限自动测试",
                        "thread_id": thread_id,
                    },
                )
                expect_status(ask_response, 200, "创建账号线程")
                print("5. 登录账号成功认领 thread：通过")

                # ========== 测试用例6：使用长效refresh_token轮换全套全新双Token ==========
                refresh_response = client.post(
                    "/auth/refresh",
                    json={
                        "refresh_token": logged_in["refresh_token"],
                    },
                )
                expect_status(refresh_response, 200, "刷新双Token")
                refreshed = refresh_response.json()

                # 校验刷新后用户ID不变
                assert refreshed["user_id"] == registered["user_id"], (
                    "刷新Token后 user_id 发生变化"
                )
                # 校验旧短期access_token失效，生成新access_token
                assert refreshed["access_token"] != logged_in["access_token"], (
                    "刷新后 Access Token 没有变化"
                )
                # 校验旧长效refresh_token作废，生成全新refresh_token
                assert refreshed["refresh_token"] != logged_in["refresh_token"], (
                    "刷新后 Refresh Token 没有轮换"
                )
                print("6. Refresh Token成功轮换整套Token：通过")

                # ========== 测试用例7：重复使用已轮换作废的旧refresh_token，预期401失效 ==========
                old_refresh_response = client.post(
                    "/auth/refresh",
                    json={
                        "refresh_token": logged_in["refresh_token"],
                    },
                )
                expect_status(old_refresh_response, 401, "重复使用旧Refresh Token")
                print("7. 旧 Refresh Token 不能重复使用：通过")

                # ========== 测试用例8：刷新后的新access_token仍有权限读取刷新前创建的对话线程 ==========
                thread_response = client.get(
                    f"/threads/{thread_id}",
                    headers=bearer(refreshed["access_token"]),
                )
                expect_status(thread_response, 200, "刷新后读取原thread")
                print("8. 刷新后原 thread 所有权保持不变：通过")

                # ========== 测试用例9：账号登出接口，同时作废当前access_token与refresh_token ==========
                logout_response = client.post(
                    "/auth/logout",
                    headers=bearer(refreshed["access_token"]),
                    json={
                        "refresh_token": refreshed["refresh_token"],
                    },
                )
                expect_status(logout_response, 200, "注销当前账号会话")
                # 校验登出接口返回成功标识
                assert logout_response.json().get("logged_out") is True
                print("9. 账号注销接口：通过")

                # ========== 测试用例10：校验注销后的两套令牌全部永久失效 ==========
                # 校验注销后的短期access_token无法访问鉴权接口
                access_after_logout = client.get(
                    "/sessions/current",
                    headers=bearer(refreshed["access_token"]),
                )
                expect_status(access_after_logout, 401, "注销后的Access Token")

                # 校验注销后的长效refresh_token无法调用刷新接口
                refresh_after_logout = client.post(
                    "/auth/refresh",
                    json={
                        "refresh_token": refreshed["refresh_token"],
                    },
                )
                expect_status(refresh_after_logout, 401, "注销后的Refresh Token")
                print("10. 注销后两种 Token 均失效：通过")

        finally:
            # 无论测试中途断言报错还是全部通过，都强制恢复后端原始全局对象
            # 防止测试覆盖正式环境的AuthStore与RAG工作流，避免业务代码异常
            api_module.auth_store = original_store
            api_module.memory_workflow = original_workflow

    # 全部10项用例无报错，打印总通过提示
    print("账号注册、登录、刷新、权限与注销测试：全部通过")


# 脚本直接运行时，执行全套账号自动化测试
if __name__ == "__main__":
    main()