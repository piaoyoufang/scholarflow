"""课程管理域路由：课程创建/列表/加入/详情、成员管理——从 api.py 原样搬入"""
from fastapi import APIRouter, Depends, HTTPException

from app.cache import delete_prefix, get_json, set_json
from app.courses.store import course_store
from app.deps import (
    current_session,
    ensure_course_access,
    ensure_course_viewer,
    is_admin_user,
    require_teacher_account,
)
from app.schemas import CourseCreateRequest, CourseJoinRequest, CourseMemberAddRequest

router = APIRouter()

# 创建课程接口 POST /courses
@router.post("/courses", tags=["课程管理"], summary="创建课程")
def create_course(
    request: CourseCreateRequest,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    require_teacher_account(user_id)
    course = course_store.create_course(
        course_name=request.course_name,
        description=request.description,
        owner_teacher_id=user_id,
    )
    delete_prefix(f"user:{user_id}:courses")
    return {"course": course.__dict__}
@router.get("/courses", tags=["课程管理"], summary="获取课程列表")
def list_courses(session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    # 管理员不参与课程成员关系，直接返回全平台课程并标记为管理员视角，便于进入任意课程查看
    if is_admin_user(user_id):
        return {
            "courses": [
                {**course, "role_in_course": "admin"}
                for course in course_store.list_all_courses()
            ]
        }
    cache_key = f"user:{user_id}:courses"
    cached = get_json(cache_key)
    if cached is not None:
        return cached
    result = {"courses": course_store.list_user_courses(user_id)}
    set_json(cache_key, result)
    return result


@router.post("/courses/join", tags=["课程管理"], summary="通过课程码加入课程")
def join_course_by_invite_code(
    request: CourseJoinRequest,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course = course_store.join_course_by_invite_code(request.invite_code, user_id)
        delete_prefix(f"user:{user_id}:courses")
        delete_prefix(f"course:{course['course_id']}:")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "status": "ok",
        "message": "加入课程成功",
        "course": course,
    }


@router.get("/courses/{course_id}", tags=["课程管理"], summary="获取课程详情")
def get_course(course_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    try:
        ensure_course_access(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    cache_key = f"course:{course_id}:detail"
    cached = get_json(cache_key)
    if cached is not None:
        return cached
    result = {"course": course_store.get_course(course_id)}
    set_json(cache_key, result)
    return result
@router.post("/courses/{course_id}/members", tags=["课程管理"], summary="添加课程成员")
def add_course_member(
    course_id: str,
    request: CourseMemberAddRequest,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
        course_store.add_member(course_id, request.user_id, request.role_in_course)
        delete_prefix(f"course:{course_id}:")
        delete_prefix(f"user:{request.user_id}:courses")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"status": "ok"}
@router.get("/courses/{course_id}/members", tags=["课程管理"], summary="获取课程成员")
def list_course_members(course_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    try:
        # 权限校验：课程教师或管理员可查看成员列表
        ensure_course_viewer(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    # 查询并返回课程所有成员
    return {"members": course_store.list_members(course_id)}
