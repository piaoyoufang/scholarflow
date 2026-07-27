# 路径工具类，用于拼接临时目录与数据库文件名
from pathlib import Path
# 临时目录工具，运行结束自动销毁文件夹与数据库文件，避免残留测试数据
from tempfile import TemporaryDirectory

# 导入认证权限存储类，提供会话创建、鉴权、线程归属校验功能
from app.security import AuthStore

def main() -> None:
    """AuthStore 完整单元测试脚本：验证登录鉴权、线程隔离、线程删除三大核心权限逻辑"""
    # 创建系统临时文件夹，代码块结束后自动删除整个目录，测试数据无残留
    with TemporaryDirectory() as directory:
        # 拼接临时库完整路径：临时目录/auth.sqlite，实例化独立的认证存储对象
        store = AuthStore(Path(directory) / "auth.sqlite")

        # 第十八步起 create_session 同时返回过期时间；本测试只使用用户ID和Token。
        user_a, token_a, _expires_a = store.create_session()
        user_b, token_b, _expires_b = store.create_session()

        # 断言校验：使用token_a鉴权，必须返回对应用户A的ID，证明token与用户绑定正确
        assert store.authenticate(token_a) == user_a
        # 断言校验：使用token_b鉴权，必须返回对应用户B的ID
        assert store.authenticate(token_b) == user_b
        # 断言校验：非法随机token鉴权返回None，令牌校验拦截生效
        assert store.authenticate("invalid-token") is None

        # 定义本次测试专用对话线程ID
        thread_id = "permission-test-thread"
        # 将测试线程归属绑定给用户A
        store.claim_thread(user_a, thread_id)
        # 校验：用户A是线程所有者，校验逻辑正常通过不抛异常
        store.require_thread_owner(user_a, thread_id)

        try:
            # 用户B尝试认领已属于用户A的线程
            store.claim_thread(user_b, thread_id)
        except PermissionError:
            # 预期捕获权限异常，符合隔离规则，直接跳过
            pass
        else:
            # 没有抛出异常代表权限校验失效，主动抛出断言错误终止测试
            raise AssertionError("用户 B 不应能认领用户 A 的线程")

        try:
            # 用户B尝试校验该线程所有权（不属于自己）
            store.require_thread_owner(user_b, thread_id)
        except PermissionError:
            # 预期捕获权限拒绝异常，测试逻辑正常
            pass
        else:
            # 无异常抛出则权限隔离失效，抛出断言失败
            raise AssertionError("用户 B 不应能读取用户 A 的线程")

        # 用户A执行线程删除操作，删除该线程归属记录
        store.delete_thread(user_a, thread_id)
        try:
            # 再次校验用户A对该线程的所有权
            store.require_thread_owner(user_a, thread_id)
        except LookupError:
            # 预期捕获线程不存在异常，证明删除记录生效
            pass
        else:
            # 未捕获异常说明删除未生效，抛出断言错误
            raise AssertionError("删除后线程所有权记录应消失")

    # 全部断言无报错，打印所有测试项通过提示
    print("Token 身份验证：通过")
    print("线程所有权隔离：通过")
    print("线程删除权限：通过")

# 脚本直接运行时自动执行全套权限单元测试
if __name__ == "__main__":
    main()
