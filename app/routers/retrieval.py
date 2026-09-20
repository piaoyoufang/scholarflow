"""检索调试域路由：查看 RAG 召回过程与命中片段——从 api.py 原样搬入"""
from fastapi import APIRouter, Depends, HTTPException

from app.courses.store import course_store
from app.deps import current_session
from app.retrieval.debug import debug_retrieval
from app.schemas import AskRequest

router = APIRouter()

@router.post("/courses/{course_id}/retrieval/debug", tags=["检索调试"], summary="检索调试")
def retrieval_debug(
    course_id: str,                          # 路径参数：目标课程ID
    request: AskRequest,                     # 请求体模型，内部携带question、thread_id字段
    session: tuple[str, str] = Depends(current_session), # 依赖注入，校验用户登录状态，返回(user_id, token)
):
    """
    【教师专用调试接口】查看RAG检索召回结果
    只允许课程教师调用，用来排查知识库召回、分数、元数据、课程过滤是否正常
    """
    # 解包会话，拿到当前登录用户ID
    user_id, _ = session

    try:
        # 权限校验：要求当前用户必须是该课程的教师；普通学生禁止访问该调试接口
        course_store.require_course_teacher(course_id, user_id)
    except LookupError as exc:
        # 捕获异常：course_id课程不存在，返回404
        # from exc：保留原始异常堆栈，方便后端日志排查定位问题
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        # 捕获异常：课程存在，但当前用户不是课程教师，无调试权限，返回403
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 调用调试函数，传入用户提问与课程id，返回格式化后的检索调试信息直接响应前端
    return debug_retrieval(request.question, course_id)
