"""会话域路由：会话创建/刷新/清除、线程列表/详情/删除——从 api.py 原样搬入"""
from fastapi import APIRouter, Depends, HTTPException

from app.deps import current_session, require_owner
from app.graph.builder import memory_store, memory_workflow
from app.schemas import SessionResponse
from app.security import auth_store

router = APIRouter()

# 登录会话创建接口，POST无鉴权，生成全新用户登录凭证，返回标准化会话结构体
# response_model 指定接口返回数据自动按SessionResponse模型校验、格式化
@router.post("/sessions", response_model=SessionResponse, tags=["会话"], summary="创建会话")
def create_session():
    # 调用认证存储工具生成新用户ID、明文访问Token、Token过期ISO时间字符串
    user_id, token, expires_at = auth_store.create_session()
    # 组装标准化会话返回模型，序列化后返回给前端
    return SessionResponse(
        # 全局唯一用户标识，后续所有接口鉴权、线程归属校验使用
        user_id=user_id,
        # 前端请求鉴权使用的Bearer明文access_token
        access_token=token,
        # 当前Token的过期时间，前端可用于提前提示用户刷新登录
        expires_at=expires_at,
    )


# 查询当前用户拥有的全部会话线程，用于前端刷新页面/重启容器后找回历史入口
@router.get("/threads", tags=["会话"], summary="获取线程列表")
def list_threads(session: tuple[str, str] = Depends(current_session)):
    user_id, _token = session
    threads = []
    for item in auth_store.list_threads(user_id):
        state = memory_workflow.get_state(
            {"configurable": {"thread_id": item["thread_id"]}}
        )
        history = state.values.get("history", []) if state.values else []
        threads.append(
            {
                "thread_id": item["thread_id"],
                "created_at": item["created_at"],
                "exists": bool(state.values),
                "history_count": len(history),
                "title": item.get("title", "新会话"),
                "updated_at": item.get("updated_at", item["created_at"]),
            }
        )
    return {"threads": threads}

# 查询指定会话线程信息接口，需要鉴权并校验线程归属
@router.get("/threads/{thread_id}", tags=["会话"], summary="获取线程详情")
def get_thread(thread_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _token = session
    # 校验当前登录用户是否拥有该线程访问权限，无权限直接抛异常
    require_owner(user_id, thread_id)
    # 从SQLite持久化存储读取该线程全部状态快照
    state = memory_workflow.get_state(
        {"configurable": {"thread_id": thread_id}}
    )
    # 组装线程信息返回：线程ID、是否存在、历史对话总条数
    history = state.values.get("history", []) if state.values else []
    return {
        "thread_id": thread_id,
        "exists": bool(state.values),
        "history_count": len(history),
        "history": history,
    }

# 删除指定会话线程接口，清空对话记忆与权限绑定关系
@router.delete("/threads/{thread_id}", tags=["会话"], summary="删除线程")
def clear_thread(thread_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _token = session
    # 前置校验：用户必须是该线程所有者
    require_owner(user_id, thread_id)
    # 删除LangGraph持久化会话快照（对话历史、检索缓存）
    memory_store.delete_thread(thread_id)
    # 删除认证库中该线程与用户的绑定权限记录
    auth_store.delete_thread(user_id, thread_id)
    # 返回删除成功标识与被清空的线程ID
    return {"deleted": True, "thread_id": thread_id}


# 获取当前登录用户信息接口，需携带合法Bearer Token鉴权
@router.get("/sessions/current", tags=["会话"], summary="获取当前登录会话")
def get_current_session(
    # 依赖全局鉴权函数自动校验Token，鉴权成功得到(user_id, 原始token)二元组
    session: tuple[str, str] = Depends(current_session),
):
    # 解包二元组，只提取用户唯一ID，丢弃原始token
    user_id, _token = session
    # 返回当前登录用户标识与鉴权成功状态给前端
    return {"user_id": user_id, "authenticated": True}


# Token续期刷新接口，传入有效旧Token，生成全新Token并作废旧Token，返回标准化会话结构
# response_model 自动约束返回数据格式为SessionResponse模型
@router.post("/sessions/refresh", response_model=SessionResponse, tags=["会话"], summary="刷新当前会话")
def refresh_session(
    # 依赖鉴权校验旧Token合法性
    session: tuple[str, str] = Depends(current_session),
):
    # 解包，丢弃用户ID，取出前端传入的旧访问令牌
    _user_id, old_token = session
    try:
        # 调用认证存储续期方法：旧Token标记失效，生成全新有效Token与过期时间
        user_id, new_token, expires_at = auth_store.refresh_session(old_token)
    except PermissionError as exc:
        # 捕获令牌失效异常，转为401未授权接口异常，保留原始异常堆栈
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    # 组装新会话信息返回给前端，前端替换本地旧Token
    return SessionResponse(
        user_id=user_id,
        access_token=new_token,
        expires_at=expires_at,
    )


# 登出注销当前Token接口，主动作废当前登录凭证
@router.delete("/sessions/current", tags=["会话"], summary="清除当前会话")
def logout(
    # 依赖鉴权校验当前会话有效
    session: tuple[str, str] = Depends(current_session),
):
    # 解包，丢弃用户ID，取出当前登录使用的token
    _user_id, token = session
    # 调用存储方法将该Token标记为已注销，立即失效
    auth_store.revoke_session(token)
    # 返回登出成功标识
    return {"logged_out": True}
