"""管理员域路由：教师邀请码、账号管理、全局课程管理与全平台统计"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.cache import delete_prefix
from app.config import settings
from app.courses.store import course_store
from app.deps import is_admin_user, require_admin
from app.feedback.store import feedback_store
from app.knowledge.library import knowledge_library
from app.analytics.qa_events import qa_event_store
from app.learning_history.store import learning_history_store
from app.observability import get_logger
from app.schemas import (
    AdminPasswordResetRequest,
    AdminUserCreateRequest,
    AdminUserDisabledRequest,
    AdminUserRoleUpdateRequest,
    TeacherInviteCreateRequest,
    TeacherInviteCreateResponse,
    TeacherInviteItem,
)
from app.security import auth_store
from app.tasks.store import task_store

router = APIRouter()
logger = get_logger("admin")


# 管理员生成教师邀请码 POST /admin/teacher-invites
@router.post(
    "/admin/teacher-invites",
    response_model=TeacherInviteCreateResponse,
    status_code=201,
    tags=["管理员"],
    summary="生成教师邀请码",
)
def create_teacher_invite(
    request: TeacherInviteCreateRequest,
    session: tuple[str, str] = Depends(require_admin),
):
    user_id, _token = session
    username = auth_store.get_username(user_id) or "admin"
    invite_id, code, expires_at = auth_store.create_teacher_invite(
        created_by=username,
        expires_in_days=request.expires_in_days,
        note=request.note,
    )
    # 明文码仅本次返回，数据库只保存哈希
    return TeacherInviteCreateResponse(
        invite_id=invite_id,
        code=code,
        expires_at=expires_at,
        note=request.note,
    )


# 管理员查询教师邀请码列表 GET /admin/teacher-invites
@router.get(
    "/admin/teacher-invites",
    response_model=list[TeacherInviteItem],
    tags=["管理员"],
    summary="教师邀请码列表",
)
def list_teacher_invites(session: tuple[str, str] = Depends(require_admin)):
    return auth_store.list_teacher_invites()


# 管理员重新签发教师邀请码 POST /admin/teacher-invites/{invite_id}/reissue
@router.post(
    "/admin/teacher-invites/{invite_id}/reissue",
    response_model=TeacherInviteCreateResponse,
    tags=["管理员"],
    summary="重新签发教师邀请码",
)
def reissue_teacher_invite(
    invite_id: str,
    request: TeacherInviteCreateRequest,
    session: tuple[str, str] = Depends(require_admin),
):
    result = auth_store.reissue_teacher_invite(
        invite_id=invite_id,
        expires_in_days=request.expires_in_days,
    )
    # 记录已使用或已吊销时不允许重签，返回冲突提示
    if not result:
        raise HTTPException(status_code=409, detail="邀请码不存在、已使用或已吊销")
    code, expires_at, note = result
    # 明文码同样只在本次返回，数据库只保存新码哈希
    return TeacherInviteCreateResponse(
        invite_id=invite_id,
        code=code,
        expires_at=expires_at,
        note=note,
    )


# 管理员吊销教师邀请码 DELETE /admin/teacher-invites/{invite_id}
@router.delete(
    "/admin/teacher-invites/{invite_id}",
    tags=["管理员"],
    summary="吊销教师邀请码",
)
def revoke_teacher_invite(
    invite_id: str,
    session: tuple[str, str] = Depends(require_admin),
):
    if not auth_store.revoke_teacher_invite(invite_id):
        raise HTTPException(status_code=409, detail="邀请码不存在、已使用或已吊销")
    return {"revoked": True, "invite_id": invite_id}


# ==================== 管理员：账号管理 ====================
# 管理员账号管理对象：账号必须存在，且不能对管理员名单中的账号做危险操作
def require_manageable_user(user_id: str) -> dict:
    user = auth_store.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if is_admin_user(user_id):
        raise HTTPException(status_code=400, detail="不能对管理员账号执行该操作")
    return user


# 组装账号列表展示字段：身份、管理员标记、课程数、在线会话数
def admin_user_payload(user: dict) -> dict:
    user_id = user["user_id"]
    return {
        "user_id": user_id,
        "username": user["username"],
        "role": user["role"],
        "created_at": user["created_at"],
        "disabled": bool(user.get("disabled")),
        "is_admin": is_admin_user(user_id),
        "course_count": course_store.count_user_courses(user_id),
        "active_sessions": auth_store.count_active_sessions(user_id),
    }


# 管理员查看账号列表 GET /admin/users
@router.get("/admin/users", tags=["管理员"], summary="账号列表")
def admin_list_users(session: tuple[str, str] = Depends(require_admin)):
    return {"users": [admin_user_payload(user) for user in auth_store.list_users()]}


# 管理员直接创建账号 POST /admin/users（无需邀请码）
@router.post("/admin/users", status_code=201, tags=["管理员"], summary="创建账号")
def admin_create_user(
    request: AdminUserCreateRequest,
    session: tuple[str, str] = Depends(require_admin),
):
    try:
        user_id = auth_store.register_user(
            request.username,
            request.password.get_secret_value(),
            request.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"user": admin_user_payload(auth_store.get_user(user_id))}


# 管理员修改账号身份 PATCH /admin/users/{user_id}/role
@router.patch("/admin/users/{user_id}/role", tags=["管理员"], summary="修改账号身份")
def admin_update_user_role(
    user_id: str,
    request: AdminUserRoleUpdateRequest,
    session: tuple[str, str] = Depends(require_admin),
):
    require_manageable_user(user_id)
    try:
        auth_store.update_user_role(user_id, request.role)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"user": admin_user_payload(auth_store.get_user(user_id))}


# 管理员重置密码 POST /admin/users/{user_id}/reset-password
@router.post("/admin/users/{user_id}/reset-password", tags=["管理员"], summary="重置账号密码")
def admin_reset_password(
    user_id: str,
    request: AdminPasswordResetRequest,
    session: tuple[str, str] = Depends(require_admin),
):
    require_manageable_user(user_id)
    try:
        auth_store.reset_password(user_id, request.new_password.get_secret_value())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "ok", "message": "密码已重置，该账号原有会话已全部下线"}


# 管理员禁用 / 启用账号 POST /admin/users/{user_id}/disabled
@router.post("/admin/users/{user_id}/disabled", tags=["管理员"], summary="禁用或启用账号")
def admin_set_user_disabled(
    user_id: str,
    request: AdminUserDisabledRequest,
    session: tuple[str, str] = Depends(require_admin),
):
    require_manageable_user(user_id)
    try:
        auth_store.set_user_disabled(user_id, request.disabled)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"user": admin_user_payload(auth_store.get_user(user_id))}


# 管理员强制下线 POST /admin/users/{user_id}/revoke-sessions
@router.post("/admin/users/{user_id}/revoke-sessions", tags=["管理员"], summary="强制账号下线")
def admin_revoke_user_sessions(
    user_id: str,
    session: tuple[str, str] = Depends(require_admin),
):
    require_manageable_user(user_id)
    revoked = auth_store.revoke_all_sessions(user_id)
    return {"revoked": revoked}


# 管理员删除账号 DELETE /admin/users/{user_id}
@router.delete("/admin/users/{user_id}", tags=["管理员"], summary="删除账号")
def admin_delete_user(
    user_id: str,
    session: tuple[str, str] = Depends(require_admin),
):
    require_manageable_user(user_id)
    owned = course_store.count_owned_courses(user_id)
    if owned:
        raise HTTPException(
            status_code=409,
            detail=f"该账号名下还有 {owned} 门课程，请先在课程管理中删除",
        )
    removed = course_store.remove_user_from_all_courses(user_id)
    auth_store.delete_user(user_id)
    delete_prefix(f"user:{user_id}:courses")
    return {"deleted": True, "removed_memberships": removed}


# ==================== 管理员：全局课程管理 ====================
def admin_course_payload(course: dict) -> dict:
    course_id = course["course_id"]
    documents = knowledge_library.document_summary(course_id)
    qa = qa_event_store.dashboard_summary(course_id)
    return {
        "course_id": course_id,
        "course_name": course["course_name"],
        "description": course["description"],
        "owner_teacher_id": course["owner_teacher_id"],
        "owner_username": auth_store.get_username(course["owner_teacher_id"]),
        "invite_code": course["invite_code"],
        "created_at": course["created_at"],
        "member_count": int(course.get("member_count") or 0),
        "document_count": documents["document_count"],
        "qa_count": qa["qa_count"],
        "citation_rate": qa["citation_rate"],
    }


# 管理员查看全部课程 GET /admin/courses
@router.get("/admin/courses", tags=["管理员"], summary="全部课程列表")
def admin_list_courses(session: tuple[str, str] = Depends(require_admin)):
    return {"courses": [admin_course_payload(course) for course in course_store.list_all_courses()]}


# 管理员删除课程 DELETE /admin/courses/{course_id}，级联清理文档、向量、任务、问答与学习记录
@router.delete("/admin/courses/{course_id}", tags=["管理员"], summary="删除课程")
def admin_delete_course(
    course_id: str,
    session: tuple[str, str] = Depends(require_admin),
):
    course = course_store.get_course(course_id)
    if not course:
        raise HTTPException(status_code=404, detail="课程不存在")

    members = course_store.list_members(course_id)
    documents = knowledge_library.delete_course_documents(course_id)

    # 清理向量：Qdrant 按文档逐个删除，Chroma 按课程一次性删除
    try:
        if settings.vector_backend.lower() == "qdrant":
            from app.vectorstores.qdrant_store import delete_by_source_id
            for document in documents:
                delete_by_source_id(document["source_id"])
        else:
            from langchain_chroma import Chroma
            from app.models import embeddings
            db = Chroma(
                collection_name="scholarflow",
                embedding_function=embeddings(),
                persist_directory=settings.vector_db_dir,
            )
            db.delete(where={"course_id": course_id})
    except Exception:
        logger.exception(
            "admin.course_vector_cleanup_failed",
            extra={"event": "admin.course_vector_cleanup_failed", "details": {"course_id": course_id}},
        )

    # 删除物理文件
    for document in documents:
        Path(document["file_path"]).unlink(missing_ok=True)

    removed_tasks = task_store.delete_course_tasks(course_id)
    removed_events = qa_event_store.delete_course_events(course_id)
    removed_feedback = feedback_store.delete_course_feedback(course_id)
    removed_history = learning_history_store.delete_course_history(course_id)
    course_store.delete_course(course_id)

    # 失效课程缓存与所有成员的课程列表缓存
    delete_prefix(f"course:{course_id}:")
    for member in members:
        delete_prefix(f"user:{member['user_id']}:courses")

    return {
        "deleted": True,
        "course_id": course_id,
        "course_name": course["course_name"],
        "removed_documents": len(documents),
        "removed_tasks": removed_tasks,
        "removed_qa_events": removed_events,
        "removed_feedback": removed_feedback,
        "removed_history": removed_history,
    }


# ==================== 管理员：全平台数据统计 ====================
@router.get("/admin/stats", tags=["管理员"], summary="全平台数据统计")
def admin_stats(session: tuple[str, str] = Depends(require_admin)):
    users = auth_store.list_users()
    courses = course_store.list_all_courses()

    course_rows = []
    for course in courses:
        docs = knowledge_library.document_summary(course["course_id"])
        qa = qa_event_store.dashboard_summary(course["course_id"])
        course_rows.append({
            "course_id": course["course_id"],
            "course_name": course["course_name"],
            "owner_username": auth_store.get_username(course["owner_teacher_id"]),
            "member_count": int(course.get("member_count") or 0),
            "document_count": docs["document_count"],
            "qa_count": qa["qa_count"],
            "citation_rate": qa["citation_rate"],
        })
    course_rows.sort(key=lambda item: item["qa_count"], reverse=True)

    return {
        "users": {
            "total": len(users),
            "teacher": sum(1 for user in users if user["role"] == "teacher"),
            "student": sum(1 for user in users if user["role"] == "student"),
            "disabled": sum(1 for user in users if user["disabled"]),
        },
        "courses": {
            "total": len(courses),
            "enrollments": sum(int(course.get("member_count") or 0) for course in courses),
        },
        "documents": knowledge_library.global_summary(),
        "qa": qa_event_store.global_summary(),
        "feedback": feedback_store.global_summary(),
        "course_rows": course_rows,
        "top_questions": qa_event_store.global_top_questions(10),
    }
