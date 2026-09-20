"""认证域路由：注册、登录、刷新令牌、退出登录——从 api.py 原样搬入"""
from fastapi import APIRouter, Depends, HTTPException

from app.deps import current_session
from app.schemas import AccountSessionResponse, LoginRequest, RefreshTokenRequest, RegisterRequest
from app.security import auth_store

router = APIRouter()


# 封装工具函数：根据用户ID生成标准化账号登录会话返回体（双Token结构）
# 返回继承SessionResponse的扩展模型AccountSessionResponse
def account_response(user_id: str) -> AccountSessionResponse:
    # 查询账号全局身份，返回给前端用于学生/教师端菜单划分
    role = auth_store.get_user_role(user_id)
    access, access_exp, refresh, refresh_exp = auth_store.create_account_session(user_id)
    return AccountSessionResponse(
        user_id=user_id,
        access_token=access,
        expires_at=access_exp,
        refresh_token=refresh,
        refresh_expires_at=refresh_exp,
        role=role,
    )


@router.post("/auth/register", response_model=AccountSessionResponse, status_code=201, tags=["认证"], summary="注册账号")
def register(request: RegisterRequest):
    try:
        # 调用存储层注册方法，传入前端标准化用户名、解密后的明文原始密码
        user_id = auth_store.register_user(
            request.username,
            # SecretStr专用方法，取出加密存储的原始明文密码用于哈希
            request.password.get_secret_value(),
            request.role,
        )
    # 捕获业务校验异常：用户名重复、用户名长度不足等ValueError
    except ValueError as exc:
        # 转换为409冲突接口异常，提示前端资源已存在（用户名重复）
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # 注册成功，生成双Token会话并返回给前端
    return account_response(user_id)


# 账号密码登录接口 POST /auth/login
# response_model 自动序列化双Token会话返回结构
@router.post("/auth/login", response_model=AccountSessionResponse, tags=["认证"], summary="账号登录")
def login(request: LoginRequest):
    # 调用存储层校验账号密码，传入用户名、解密后的明文密码
    user_id = auth_store.verify_user(
        request.username,
        request.password.get_secret_value(),
    )
    # 校验失败（无用户/密码错误），抛出401未授权异常
    if not user_id:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    # 登录校验通过，生成access+refresh双令牌返回前端
    return account_response(user_id)


# 长效刷新令牌续期接口 POST /auth/refresh
# 使用refresh_token换新access_token与新refresh_token，旧刷新令牌直接失效
@router.post("/auth/refresh", response_model=AccountSessionResponse, tags=["认证"], summary="刷新登录令牌")
def refresh_account_session(request: RefreshTokenRequest):
    try:
        # 调用存储层令牌轮换逻辑，传入前端携带的旧refresh_token
        user_id, access, access_exp, refresh, refresh_exp = (
            auth_store.rotate_refresh_token(request.refresh_token)
        )
    # 捕获刷新令牌失效/过期/注销的权限异常
    except PermissionError as exc:
        # 转为401未授权错误，告知前端刷新凭证失效
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    # 查询账号身份，刷新登录态时同步给前端恢复菜单权限
    role = auth_store.get_user_role(user_id)
    # 组装全新双Token会话返回，前端替换本地旧令牌
    return AccountSessionResponse(
        user_id=user_id,
        access_token=access,
        expires_at=access_exp,
        refresh_token=refresh,
        refresh_expires_at=refresh_exp,
        role=role,
    )


# 完整登出接口 POST /auth/logout
# 同时作废当前access短期令牌 + 传入的refresh长效刷新令牌，彻底下线登录会话
@router.post("/auth/logout", tags=["认证"], summary="退出登录")
def logout_account(
    # 请求体携带需要注销的refresh_token
    request: RefreshTokenRequest,
    # 依赖鉴权校验当前有效的access_token，解包得到(user_id, access_token)
    session: tuple[str, str] = Depends(current_session),
):
    # 解包二元组，丢弃用户ID，取出当前业务鉴权access令牌
    _user_id, access_token = session
    # 注销当前正在使用的短期access_token，业务接口立刻无法访问
    auth_store.revoke_session(access_token)
    # 注销前端提交的长效refresh_token，无法再调用刷新续期接口
    auth_store.revoke_refresh_token(request.refresh_token)
    # 返回登出成功标识
    return {"logged_out": True}
