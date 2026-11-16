"""共享依赖注入：供 app/routers/ 下所有 router 使用
从 api.py 原样搬出，一行逻辑未改"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.courses.store import course_store
from app.security import auth_store

# 实例化Bearer令牌解析器；auto_error=False 关闭内置自动报错，自定义鉴权异常提示
bearer = HTTPBearer(auto_error=False)

# 全局鉴权依赖注入函数，给所有需要登录校验的接口使用
# 校验请求头Bearer Token，鉴权通过返回二元组(用户唯一ID, 原始token字符串)
def current_session(
    # 依赖注入：自动从请求头解析Authorization凭证；无token时变量为None
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> tuple[str, str]:
    # 校验1：没有携带凭证 或 认证协议不是标准bearer（大小写兼容判断）
    if not credentials or credentials.scheme.lower() != "bearer":
        # 抛出401未授权异常，提示前端缺少合法Bearer令牌
        raise HTTPException(status_code=401, detail="缺少 Bearer Token")

    # 提取请求头中携带的原始明文token字符串
    token = credentials.credentials
    # 调用认证存储校验token合法性：验证哈希、过期时间、注销状态
    user_id = auth_store.authenticate(token)
    # 校验2：token校验不通过（不存在/过期/手动注销）
    if not user_id:
        # 抛出401异常，告知前端令牌失效
        raise HTTPException(
            status_code=401,
            detail="Token 无效、已过期或已注销",
        )
    # 鉴权全部通过，返回当前登录用户ID + 原始token，供下游接口使用
    return user_id, token

# 线程归属权限统一校验工具：校验用户是否为该thread_id所有者，转换数据库异常为HTTP标准错误
# 全局教师身份校验：保护创建课程、上传资料、教学分析等教师端能力，防止只靠前端隐藏菜单
def require_teacher_account(user_id: str) -> None:
    if auth_store.get_user_role(user_id) != "teacher":
        raise HTTPException(status_code=403, detail="仅教师账号可操作")


# 判断用户名是否在管理员名单（ADMIN_USERNAMES，逗号分隔，大小写不敏感）
def is_admin_user(user_id: str) -> bool:
    username = auth_store.get_username(user_id)
    if not username:
        return False
    allowed = {
        name.strip().casefold()
        for name in settings.admin_usernames.split(",")
        if name.strip()
    }
    return username.casefold() in allowed


# 管理员鉴权依赖：仅管理员可访问管理接口
def require_admin(
    session: tuple[str, str] = Depends(current_session),
) -> tuple[str, str]:
    user_id, token = session
    if not is_admin_user(user_id):
        raise HTTPException(status_code=403, detail="仅管理员可操作")
    return user_id, token


# 课程访问校验：管理员可进入任意课程查看并试用问答；其他用户必须是课程成员
def ensure_course_access(course_id: str, user_id: str) -> None:
    if not course_store.get_course(course_id):
        raise LookupError("课程不存在")
    if is_admin_user(user_id):
        return
    if not course_store.get_member_role(course_id, user_id):
        raise PermissionError("你不是该课程成员，无权访问")


# 教师只读页面校验（看板、问答分析、检索可视化、成员列表）：课程教师或管理员可查看
def ensure_course_viewer(course_id: str, user_id: str) -> None:
    if not course_store.get_course(course_id):
        raise LookupError("课程不存在")
    if is_admin_user(user_id):
        return
    if course_store.get_member_role(course_id, user_id) != "teacher":
        raise PermissionError("仅课程教师可查看")


def require_owner(user_id: str, thread_id: str) -> None:
    try:
        # 调用认证库校验线程归属关系
        auth_store.require_thread_owner(user_id, thread_id)
    except LookupError as exc:
        # 捕获线程不存在异常，转换为404接口异常，保留原始异常堆栈
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        # 捕获非所有者权限异常，转换为403禁止访问异常
        raise HTTPException(status_code=403, detail=str(exc)) from exc

