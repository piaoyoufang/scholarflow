"""学习工具域路由：学习计划生成/历史、自动出题/历史——从 api.py 原样搬入"""
from fastapi import APIRouter, Depends, HTTPException

from app.agents.learning_plan import generate_learning_plan
from app.agents.quiz import generate_quiz
from app.courses.store import course_store
from app.deps import current_session
from app.learning_history.store import learning_history_store
from app.observability import get_logger
from app.schemas import LearningPlanRequest, QuizRequest

logger = get_logger("api")

router = APIRouter()

# FastAPI POST接口路由：为指定课程生成AI学习计划
@router.post("/courses/{course_id}/agents/learning-plan", tags=["学习工具"], summary="生成学习计划")
def learning_plan(
    course_id: str,                          # 路径参数：课程ID，限定本次生成计划使用哪一个课程的知识库
    request: LearningPlanRequest,            # 请求体参数，Pydantic模型，接收前端传入的学习目标、天数、难度、每日时长
    session: tuple[str, str] = Depends(current_session), # 依赖注入：校验用户登录；返回元组 (user_id, token)，未登录直接返回401
):
    """
    课程Agent接口：基于课程知识库RAG生成结构化学习计划
    """
    # 解包session元组，取出登录用户ID；下划线 _ 代表丢弃token，本接口不需要使用token
    user_id, _ = session

    try:
        # 权限校验函数：①判断课程是否存在 ②判断当前用户是否属于该课程（老师/学生）
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        # 捕获LookupError异常：传入的course_id课程不存在
        # from exc：保留原始异常堆栈信息，服务端日志可以看到原始报错
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        # 捕获PermissionError异常：课程存在，但该用户不是课程成员，没有访问权限
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 调用业务逻辑函数generate_learning_plan生成学习计划
    # 内部逻辑：RAG检索本课程知识库 → 组装上下文 → LLM结构化输出LearningPlanResponse
    try:
        result = generate_learning_plan(
            course_id=course_id,                # 传递课程ID，让RAG检索只读取本课程文档，实现知识库隔离
            goal=request.goal,                  # 用户学习目标，来自请求体
            days=request.days,                  # 计划总天数，来自请求体
            difficulty=request.difficulty,      # 难度等级 beginner/intermediate/advanced，来自请求体
            daily_minutes=request.daily_minutes,# 每日学习分钟数，来自请求体
        )
    except Exception as exc:
        if "Timeout" in exc.__class__.__name__:
            raise HTTPException(status_code=504, detail="大模型生成超时，请稍后重试或缩短学习目标") from exc
        raise
    result_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    record_id = ""
    try:
        record_id = learning_history_store.save_plan(
            user_id=user_id,
            course_id=course_id,
            goal=request.goal,
            days=request.days,
            difficulty=request.difficulty,
            daily_minutes=request.daily_minutes,
            result=result_dict,
        )
    except Exception:
        logger.exception(
            "learning_plan.history_save_failed",
            extra={
                "event": "learning_plan.history_save_failed",
                "details": {"course_id": course_id, "user_id": user_id},
            },
        )
    return {**result_dict, "record_id": record_id}


@router.get("/courses/{course_id}/agents/learning-plan/history", tags=["学习工具"], summary="获取学习计划历史")
def list_learning_plan_history(
    course_id: str,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"items": learning_history_store.list_plans(user_id, course_id)}


@router.get("/courses/{course_id}/agents/learning-plan/history/{record_id}", tags=["学习工具"], summary="获取学习计划历史详情")
def get_learning_plan_history(
    course_id: str,
    record_id: str,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    record = learning_history_store.get_plan(record_id, user_id, course_id)
    if not record:
        raise HTTPException(status_code=404, detail="学习计划记录不存在")
    return {"record": record}


@router.delete("/courses/{course_id}/agents/learning-plan/history/{record_id}", tags=["学习工具"], summary="删除学习计划历史")
def delete_learning_plan_history(
    course_id: str,
    record_id: str,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    deleted = learning_history_store.delete_plan(record_id, user_id, course_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="学习计划记录不存在")
    return {"deleted": True}


# FastAPI POST接口路由：为指定课程生成测验题目
@router.post("/courses/{course_id}/agents/quiz", tags=["学习工具"], summary="生成测验题")
def quiz(
    course_id: str,                          # 路径参数：课程ID，限定RAG检索只使用该课程知识库
    request: QuizRequest,                    # 请求体，Pydantic自动校验参数范围、类型，非法参数直接返回422
    session: tuple[str, str] = Depends(current_session), # 依赖注入校验登录状态；返回元组(user_id, token)，未登录返回401
):
    """
    课程Agent接口：基于课程知识库RAG自动生成测验题
    """
    # 解包会话元组，拿到登录用户ID；下划线_丢弃token，本接口不需要使用token
    user_id, _ = session

    try:
        # 权限校验：校验课程是否存在、当前用户是否为本课程的老师/学生
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        # 捕获异常：course_id对应的课程不存在，返回HTTP 404
        # from exc：保留原始异常堆栈，服务端日志可以查看原始报错信息
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        # 捕获异常：课程存在，但用户不是课程成员，没有权限访问该课程资源，返回HTTP 403
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 调用业务函数generate_quiz生成测验，传入全部参数
    # 内部逻辑：search检索课程知识库 → 拼接上下文 → LLM结构化输出QuizResponse
    try:
        result = generate_quiz(
            course_id=course_id,                # 传递课程ID，用于RAG知识库隔离
            topic=request.topic,                # 出题主题，取自前端请求体
            question_count=request.question_count, # 题目数量，取自前端请求体
            question_type=request.question_type,   # 题型，取自前端请求体
            difficulty=request.difficulty,          # 难度，取自前端请求体
        )
    except Exception as exc:
        if "Timeout" in exc.__class__.__name__:
            raise HTTPException(status_code=504, detail="大模型生成超时，请稍后重试或减少题目数量") from exc
        raise
    result_dict = result.model_dump() if hasattr(result, "model_dump") else dict(result)
    record_id = ""
    try:
        record_id = learning_history_store.save_quiz(
            user_id=user_id,
            course_id=course_id,
            topic=request.topic,
            question_count=request.question_count,
            question_type=request.question_type,
            difficulty=request.difficulty,
            result=result_dict,
        )
    except Exception:
        logger.exception(
            "quiz.history_save_failed",
            extra={
                "event": "quiz.history_save_failed",
                "details": {"course_id": course_id, "user_id": user_id},
            },
        )
    return {**result_dict, "record_id": record_id}


@router.get("/courses/{course_id}/agents/quiz/history", tags=["学习工具"], summary="获取自动出题历史")
def list_quiz_history(
    course_id: str,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"items": learning_history_store.list_quizzes(user_id, course_id)}


@router.get("/courses/{course_id}/agents/quiz/history/{record_id}", tags=["学习工具"], summary="获取自动出题历史详情")
def get_quiz_history(
    course_id: str,
    record_id: str,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    record = learning_history_store.get_quiz(record_id, user_id, course_id)
    if not record:
        raise HTTPException(status_code=404, detail="题单记录不存在")
    return {"record": record}


@router.delete("/courses/{course_id}/agents/quiz/history/{record_id}", tags=["学习工具"], summary="删除自动出题历史")
def delete_quiz_history(
    course_id: str,
    record_id: str,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    deleted = learning_history_store.delete_quiz(record_id, user_id, course_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="题单记录不存在")
    return {"deleted": True}
