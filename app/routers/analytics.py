"""分析看板域路由：课程看板、高频/无引用/低质量/负反馈问题——从 api.py 原样搬入"""
from fastapi import APIRouter, Depends, HTTPException

from app.analytics.qa_events import qa_event_store
from app.cache import get_json, set_json
from app.courses.store import course_store
from app.deps import current_session
from app.feedback.store import feedback_store
from app.knowledge.library import knowledge_library

router = APIRouter()

@router.get("/courses/{course_id}/dashboard", tags=["分析看板"], summary="获取课程看板")
def course_dashboard(course_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    cache_key = f"course:{course_id}:dashboard"
    cached = get_json(cache_key)
    if cached is not None:
        return cached

    document_data = knowledge_library.document_summary(course_id)
    qa_data = qa_event_store.dashboard_summary(course_id)
    feedback_data = feedback_store.summary(course_id)
    result = {
        **document_data,
        **qa_data,
        "feedback_up_count": feedback_data.get("up", 0),
        "feedback_down_count": feedback_data.get("down", 0),
    }
    set_json(cache_key, result)
    return result


@router.get("/courses/{course_id}/analytics/top-questions", tags=["分析看板"], summary="获取高频问题")
def top_questions(course_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    cache_key = f"course:{course_id}:analytics:top_questions"
    cached = get_json(cache_key)
    if cached is not None:
        return cached
    result = {"items": qa_event_store.top_questions(course_id)}
    set_json(cache_key, result)
    return result
@router.get("/courses/{course_id}/analytics/no-citation", tags=["分析看板"], summary="获取无引用问题")
def no_citation_questions(course_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    cache_key = f"course:{course_id}:analytics:no_citation"
    cached = get_json(cache_key)
    if cached is not None:
        return cached
    result = {"items": qa_event_store.no_citation_questions(course_id)}
    set_json(cache_key, result)
    return result
@router.get("/courses/{course_id}/analytics/low-quality", tags=["分析看板"], summary="获取低质量问题")
def low_quality_questions(course_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    cache_key = f"course:{course_id}:analytics:low_quality"
    cached = get_json(cache_key)
    if cached is not None:
        return cached
    result = {"items": qa_event_store.low_quality_questions(course_id)}
    set_json(cache_key, result)
    return result


@router.get("/courses/{course_id}/analytics/down-feedback", tags=["分析看板"], summary="获取负反馈问题")
def down_feedback_questions(course_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"items": feedback_store.recent_down_feedback(course_id)}
