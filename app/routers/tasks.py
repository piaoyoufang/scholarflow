"""任务中心域路由：课程任务列表、任务详情——从 api.py 原样搬入"""
from fastapi import APIRouter, Depends, HTTPException

from app.courses.store import course_store
from app.deps import current_session
from app.tasks.store import task_store

router = APIRouter()

@router.get("/courses/{course_id}/tasks", tags=["任务中心"], summary="查看课程任务列表")
def list_course_tasks(course_id: str, session: tuple[str, str] = Depends(current_session)):
    """
    查询课程下全部上传/入库任务。
    课程成员可查看，方便前端上传任务页展示最近任务。
    """
    user_id, _ = session
    try:
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"tasks": task_store.list_course_tasks(course_id)}

@router.get("/tasks/{task_id}", tags=["任务中心"], summary="查看任务详情")
def get_task(task_id: str, session: tuple[str, str] = Depends(current_session)):
    """
    查询任务详情接口
    :param task_id: 路径参数，要查询的任务UUID
    :param session: 依赖注入，拿到当前登录用户 (user_id, token)，校验用户已登录
    """
    # 根据task_id从sqlite查询任务记录，会自动把result_json解析为result字典
    task = task_store.get_task(task_id)
    # 如果查询结果为空，代表任务id不存在，返回404
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    # 将任务字典返回给前端，前端拿到status/progress/message/error做进度展示
    return {"task": task}
