# 导入时间模块，用于模拟Token过期等待
import time
# 路径工具类，拼接临时目录与数据库文件名
from pathlib import Path
# 临时目录工具，代码执行完毕自动销毁目录，无测试文件残留
from tempfile import TemporaryDirectory

# 导入认证权限存储类，提供会话创建、鉴权、刷新、注销、清理全套能力
from app.security import AuthStore

def main() -> None:
    """AuthStore Token全生命周期单元测试脚本
    覆盖4个核心测试点：Token自动过期、刷新作废旧令牌、手动注销、批量清理失效会话
    """
    # 创建系统临时文件夹，代码块结束自动删除整个目录，避免sqlite文件锁残留
    with TemporaryDirectory() as directory:
        # 实例化认证存储，数据库存放在临时目录，设置Token有效期仅1秒，快速模拟过期
        store = AuthStore(
            Path(directory) / "auth.sqlite",
            token_ttl_seconds=1,
        )

        # 创建首个登录会话，返回用户ID、原始Token、过期时间字符串
        user_id, old_token, old_expires_at = store.create_session()
        # 断言校验：创建会话一定会返回合法过期时间，不为空
        assert old_expires_at
        # 断言校验：新生成的Token鉴权可正常匹配到对应用户ID
        assert store.authenticate(old_token) == user_id

        # 将测试线程绑定至当前用户，校验线程归属不影响Token生命周期
        store.claim_thread(user_id, "lifecycle-thread")
        # 调用会话刷新接口，传入合法旧Token，生成全新Token
        refreshed_user, new_token, new_expires_at = store.refresh_session(
            old_token
        )
        # 断言校验：刷新前后用户ID保持不变，不会切换用户
        assert refreshed_user == user_id
        # 断言校验：刷新后会生成新的有效过期时间
        assert new_expires_at
        # 断言校验：刷新后旧Token已被标记注销，鉴权直接失败返回None
        assert store.authenticate(old_token) is None
        # 断言校验：新Token鉴权正常，可识别用户
        assert store.authenticate(new_token) == user_id
        # 校验用户依旧是该线程合法所有者，刷新Token不改变线程归属关系
        store.require_thread_owner(user_id, "lifecycle-thread")

        # 手动注销新生成的Token，返回True代表注销成功
        assert store.revoke_session(new_token) is True
        # 断言校验：注销后的Token鉴权失效
        assert store.authenticate(new_token) is None

        # 再新建一条测试会话，用于测试自动过期逻辑
        _user, expiring_token, _expires_at = store.create_session()
        # 休眠1.1秒，超过Token 1秒有效期，触发过期逻辑
        time.sleep(1.1)
        # 断言校验：超时后的Token鉴权失败，判定为过期失效
        assert store.authenticate(expiring_token) is None

        # 执行批量清理方法，删除所有已注销、已过期的会话记录
        deleted = store.cleanup_sessions()
        # 断言校验：本次测试至少产生3条可清理的失效会话（旧刷新token、手动注销token、超时token）
        assert deleted >= 3

    # 全部断言无报错，打印全部测试项通过提示
    print("Token 过期：通过")
    print("Token 刷新与旧 Token 失效：通过")
    print("Token 注销：通过")
    print("过期/注销记录清理：通过")

# 脚本直接运行时自动执行全套Token生命周期测试
if __name__ == "__main__":
    main()