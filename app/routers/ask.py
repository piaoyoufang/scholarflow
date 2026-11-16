"""问答域路由：课程问答（含流式）、全局问答、问答反馈、问答事件处理——从 api.py 原样搬入"""
import asyncio
from json import dumps as json_dumps
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.analytics.qa_events import qa_event_store
from app.cache import delete_prefix
from app.config import settings
from app.courses.store import course_store
from app.deps import current_session, ensure_course_access
from app.feedback.store import feedback_store
from app.graph.builder import memory_workflow, retrieval_workflow
from app.graph.nodes import build_citations, stream_answer_text, update_memory_summary
from app.observability import get_logger
from app.rate_limit import ask_rate_limiter, model_semaphore
from app.schemas import AskRequest, FeedbackRequest, QAEventProcessRequest
from app.security import auth_store

logger = get_logger("api")

router = APIRouter()

@router.post("/courses/{course_id}/ask", tags=["问答"], summary="课程内问答")
def ask_course(
    course_id: str,                          # 路径参数：要提问的课程ID
    request: AskRequest,                     # 请求体，Pydantic模型，里面包含question、thread_id等字段
    session: tuple[str, str] = Depends(current_session),  # 依赖注入，校验登录，返回(user_id,token)
):
    """
    课程知识库问答接口
    作用：在指定课程的知识库中执行RAG+LangGraph Agent问答，绑定会话线程
    """
    # 解包session，拿到当前登录用户id
    user_id, _ = session

    try:
        # 权限校验：校验该用户是否有权访问这个课程
        # 内部逻辑：用户要么是课程老师，要么是课程学生；无权限直接抛异常
        ensure_course_access(course_id, user_id)
    except LookupError as exc:
        # 捕获异常：course_id不存在，返回404
        # from exc：保留原始异常堆栈，方便后台日志排查
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        # 捕获异常：课程存在，但用户没有访问权限，返回403禁止访问
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        # 课程问答也必须绑定 thread_id 归属，否则前端历史会话列表查不到该会话
        auth_store.claim_thread(user_id, request.thread_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 调用LangGraph工作流memory_workflow
    # 输入state：把用户问题、当前课程id传入graph状态
    # course_id会向下传递给内部search检索函数，实现只检索本课程知识库
    result = memory_workflow.invoke(
        {"question": request.question, "course_id": course_id},
        # LangGraph会话配置：thread_id对应对话会话，用来维护记忆、多轮上下文
        config={"configurable": {"thread_id": request.thread_id}},
    )
    # LangGraph 返回的 result["answer"] 在你的项目里是 ResearchAnswer 对象。
    # SQLite 只能保存 str/int/float/bytes/None，不能直接保存 Pydantic 对象。
    # 所以这里必须先把 ResearchAnswer 转成普通 dict，再取出 answer 字符串和 citations 列表。
    answer_obj = result.get("answer") if isinstance(result, dict) else result
    if hasattr(answer_obj, "model_dump"):
        answer_payload = answer_obj.model_dump()
    elif isinstance(answer_obj, dict):
        answer_payload = answer_obj
    else:
        answer_payload = {
            "answer": str(answer_obj),
            "citations": [],
            "confidence": 0,
            "missing_information": [],
        }

    # answer_text 是真正要写入 qa_events.answer TEXT 字段的字符串。
    # 不能把 ResearchAnswer 对象直接传给 SQLite，否则会报：
    # sqlite3.ProgrammingError: type 'ResearchAnswer' is not supported
    answer_text = str(answer_payload.get("answer", ""))
    citations = answer_payload.get("citations", []) or []

    # 调用埋点存储，把本次问答事件写入sqlite qa_events日志表
    qa_event_store.record_event(
        course_id=course_id,  # 当前课程ID
        user_id=user_id,  # 当前登录用户ID
        thread_id=request.thread_id,  # 对话会话ID，LangGraph记忆的线程id
        question=request.question,  # 用户原始提问
        answer=answer_text,  # 大模型输出的回答文本，必须是字符串，不能是 ResearchAnswer 对象
        citation_count=len(citations),  # 统计引用来源数量，计算列表长度存入数据库
    )

    try:
        # 用首次问题生成会话标题，让左侧历史会话列表可以显示有意义的标题
        auth_store.update_thread_title(user_id, request.thread_id, request.question)
    except (LookupError, PermissionError):
        logger.exception(
            "course.ask.thread_title_update_failed",
            extra={
                "event": "course.ask.thread_title_update_failed",
                "details": {"user_id": user_id, "thread_id": request.thread_id},
            },
        )

    # 课程级问答完成日志：用于后续排查“哪门课程、哪个用户、哪个线程、引用数量多少”
    # 这不是业务数据入库，业务数据已经由 qa_event_store.record_event 写入 SQLite。
    # logger.info 只是写运行日志，方便线上问题定位和 Diagnosis Agent 后续读取分析。
    logger.info(
        "course.ask.completed",
        extra={
            "event": "course.ask.completed",
            "details": {
                "course_id": course_id,
                "user_id": user_id,
                "thread_id": request.thread_id,
                "citation_count": len(citations),
            },
        },
    )

    # 只把前端真正需要的结构化回答返回出去。
    # 不直接 return result，是因为 result 里面可能包含 LangChain Document、Pydantic 对象等复杂类型，
    # 对前端没有必要，也更容易触发 JSON 序列化问题。
    return answer_payload


# 流式问答接口：与 ask_course 同一业务逻辑，只把返回形式改成 SSE 事件流。
# 检索/分析先同步跑完（retrieval_workflow），回答正文由 stream_answer_text 逐段生成，
# 这样前端不用等整段回答生成完就能渲染，同时保持引用与证据编号对齐。
@router.post("/courses/{course_id}/ask/stream", tags=["问答"], summary="课程内问答（流式）")
async def ask_course_stream(
    course_id: str,
    request: AskRequest,
    http_request: Request,
    session: tuple[str, str] = Depends(current_session),
):
    """
    课程知识库问答接口（SSE 流式版）
    事件类型：meta=阶段信息 / delta=增量正文 / done=最终答案与引用 / error=中途出错
    """
    user_id, _ = session

    # 权限与线程归属校验：与 ask_course 完全相同（流式也要在响应头发出前拦截越权请求）
    try:
        ensure_course_access(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    try:
        auth_store.claim_thread(user_id, request.thread_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 与非流式接口共用同一份限流额度，避免绕过限制刷问答
    if settings.rate_limit_enabled:
        decision = ask_rate_limiter.check(
            f"ask:user:{user_id}",
            settings.ask_rate_limit_max_requests,
        )
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="问答请求过于频繁，请稍后重试",
                headers={"Retry-After": str(decision.retry_after)},
            )

    # 流式响应一旦开始就无法再改状态码，所以并发信号量必须在返回响应前抢占
    if not model_semaphore.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="当前提问人数较多，请稍后重试",
            headers={"Retry-After": "3"},
        )

    def sse(event: str, data: dict) -> str:
        """一帧 SSE 报文：event 行 + data 行，两个换行结束一帧（SSE 协议格式）"""
        return f"event: {event}\ndata: {json_dumps(data, ensure_ascii=False)}\n\n"

    async def event_stream():
        """SSE 事件流生成器：每 yield 一个字符串就是一帧，前端逐帧消费"""
        started_at = perf_counter()
        try:
            yield sse("meta", {"stage": "retrieving", "thread_id": request.thread_id})

            # 检索/分析阶段同步执行（放到线程里避免阻塞事件循环），完成后 state 里已有证据
            try:
                state = await asyncio.to_thread(
                    retrieval_workflow.invoke,
                    {"question": request.question, "course_id": course_id},
                    config={"configurable": {"thread_id": request.thread_id}},
                )
            except Exception:
                logger.exception(
                    "course.ask_stream.retrieve_failed",
                    extra={
                        "event": "course.ask_stream.retrieve_failed",
                        "details": {
                            "course_id": course_id,
                            "user_id": user_id,
                            "thread_id": request.thread_id,
                        },
                    },
                )
                yield sse("error", {"stage": "retrieving", "message": "检索阶段失败，请稍后重试"})
                return

            state = state if isinstance(state, dict) else {}
            sources = sorted({
                str((doc.metadata or {}).get("source_name") or "未知来源")
                for doc in state.get("documents", [])
            })
            yield sse("meta", {"stage": "answering", "sources": sources})

            # 记忆摘要最多每三轮触发一次 LLM 压缩，放到线程里避免阻塞事件循环
            memory_summary = await asyncio.to_thread(update_memory_summary, state)

            answer_parts: list[str] = []
            iterator = stream_answer_text(state, memory_summary).__aiter__()
            try:
                while True:
                    try:
                        piece = await asyncio.wait_for(iterator.__anext__(), timeout=15)
                    except asyncio.TimeoutError:
                        # 模型长时间无输出时发送心跳注释，避免连接被代理提前断开
                        yield ": keep-alive\n\n"
                        continue
                    except StopAsyncIteration:
                        break
                    if await http_request.is_disconnected():
                        logger.info(
                            "course.ask_stream.client_closed",
                            extra={
                                "event": "course.ask_stream.client_closed",
                                "details": {
                                    "course_id": course_id,
                                    "user_id": user_id,
                                    "thread_id": request.thread_id,
                                },
                            },
                        )
                        return
                    answer_parts.append(piece)
                    yield sse("delta", {"text": piece})
            except Exception:
                logger.exception(
                    "course.ask_stream.generate_failed",
                    extra={
                        "event": "course.ask_stream.generate_failed",
                        "details": {
                            "course_id": course_id,
                            "user_id": user_id,
                            "thread_id": request.thread_id,
                        },
                    },
                )
                yield sse("error", {"stage": "answering", "message": "生成回答失败，请稍后重试"})
                return

            answer_text = "".join(answer_parts).strip()
            citations = [item.model_dump() for item in build_citations(state)]

            # 把本轮问答写回 checkpoint，保证下一轮仍能读取多轮上下文
            try:
                await asyncio.to_thread(
                    retrieval_workflow.update_state,
                    {"configurable": {"thread_id": request.thread_id}},
                    {
                        "history": [
                            {"role": "user", "content": request.question},
                            {"role": "assistant", "content": answer_text},
                        ],
                        "memory_summary": memory_summary,
                        "turn_count": int(state.get("turn_count", 0) or 0) + 1,
                    },
                )
            except Exception:
                logger.exception(
                    "course.ask_stream.checkpoint_failed",
                    extra={
                        "event": "course.ask_stream.checkpoint_failed",
                        "details": {
                            "course_id": course_id,
                            "user_id": user_id,
                            "thread_id": request.thread_id,
                        },
                    },
                )

            if not answer_text:
                quality_score = 0
            elif not citations:
                quality_score = 50
            else:
                quality_score = 100

            qa_event_store.record_event(
                course_id=course_id,
                user_id=user_id,
                thread_id=request.thread_id,
                question=request.question,
                answer=answer_text,
                citation_count=len(citations),
                pass_result=bool(answer_text),
                quality_score=quality_score,
                error="",
            )
            delete_prefix(f"course:{course_id}:")

            try:
                auth_store.update_thread_title(user_id, request.thread_id, request.question)
            except (LookupError, PermissionError):
                logger.exception(
                    "course.ask_stream.thread_title_update_failed",
                    extra={
                        "event": "course.ask_stream.thread_title_update_failed",
                        "details": {"user_id": user_id, "thread_id": request.thread_id},
                    },
                )

            yield sse(
                "done",
                {
                    "thread_id": request.thread_id,
                    "answer": answer_text,
                    "citations": citations,
                    "confidence": 0.85 if citations else 0.6,
                    "latency_ms": round((perf_counter() - started_at) * 1000, 2),
                },
            )
        finally:
            # 无论正常结束、异常还是客户端断开，都必须释放模型并发名额
            model_semaphore.release()

    # text/event-stream 声明 SSE 协议；no-cache 与 X-Accel-Buffering 防止反向代理缓冲事件流
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# PATCH接口：局部更新问答事件处理状态，路径携带课程id和事件id
@router.patch("/courses/{course_id}/qa-events/{event_id}/status", tags=["问答"], summary="更新问答事件处理状态")
def update_qa_event_status(
    course_id: str,
    event_id: str,
    request: QAEventProcessRequest,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
        qa_event_store.update_process_status(event_id=event_id, status=request.status, note=request.note)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    delete_prefix(f"course:{course_id}:")
    return {"event_id": event_id, "status": request.status}


@router.post("/courses/{course_id}/feedback", tags=["问答"], summary="提交问答反馈")
def create_feedback(
    course_id: str,
    request: FeedbackRequest,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        ensure_course_access(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        feedback_id = feedback_store.create_feedback(
            course_id=course_id,
            user_id=user_id,
            thread_id=request.thread_id,
            question=request.question,
            answer=request.answer,
            rating=request.rating,
            reason=request.reason,
            comment=request.comment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    delete_prefix(f"course:{course_id}:")
    return {"feedback_id": feedback_id, "status": "ok"}


# 核心问答接口，需携带Bearer Token鉴权
@router.post("/ask", tags=["问答"], summary="全局问答")
def ask(request: AskRequest, session: tuple[str, str] = Depends(current_session)):
    user_id, _token = session
    # 判断配置是否开启限流功能，开启才执行问答接口用户级限流校验
    if settings.rate_limit_enabled:
        # 调用问答专用限流器，限流key拼接为 ask:user:{user_id}，按登录用户独立计数
        decision = ask_rate_limiter.check(
            f"ask:user:{user_id}",
            # 读取配置文件中单个用户单窗口最大问答请求次数
            settings.ask_rate_limit_max_requests,
        )
        # 校验结果为不允许，代表该用户当前窗口问答次数已打满，触发限流拦截
        if not decision.allowed:
            # 打印警告日志，记录问答用户限流拦截事件，用于监控恶意刷问答
            logger.warning(
                "rate_limit.blocked",
                extra={
                    # 自定义日志事件标识，筛选限流拦截记录专用
                    "event": "rate_limit.blocked",
                    # 扩展业务详情字段，记录拦截维度、用户、接口、等待时长
                    "details": {
                        "scope": "ask_user",  # 限流维度：登录用户粒度的问答限流
                        "user_id": user_id,  # 被拦截的用户唯一ID
                        "path": "/ask",  # 触发限流的问答接口路径
                        "retry_after": decision.retry_after  # 需要等待多少秒后才能再次提问
                    },
                },
            )
            # 抛出标准429请求过多异常，携带等待时长响应头
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="问答请求过于频繁，请稍后重试",
                headers={"Retry-After": str(decision.retry_after)},
            )
    try:
        # 将本次对话线程绑定至当前登录用户；已绑定其他用户则抛出权限异常
        auth_store.claim_thread(user_id, request.thread_id)
        auth_store.update_thread_title(
            user_id,
            request.thread_id,
            request.question,
        )
    except PermissionError as exc:
        # 捕获线程归属冲突异常，转换为403接口错误
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 组装LangGraph会话配置，绑定前端传入的thread_id
    config = {"configurable": {"thread_id": request.thread_id}}

    # 记录RAG智能体开始执行的高精度时间戳，用于计算检索+生成耗时
    agent_started_at = perf_counter()
    # 非阻塞尝试获取模型并发信号量，blocking=False 拿不到锁立刻返回False，不会卡住等待
    acquired = model_semaphore.acquire(blocking=False)
    # 判断信号量已满，当前模型并发达到配置上限，拒绝新提问请求
    if not acquired:
        # 打印警告日志，标记模型并发占满事件，便于监控接口负载情况
        logger.warning(
            "model.concurrency.full",
            extra={
                # 自定义日志事件标识，用于筛选模型满载记录
                "event": "model.concurrency.full",
                # 扩展业务详情字段，记录请求用户、对话线程、最大并发阈值
                "details": {
                    "user_id": user_id,                          # 当前提问用户唯一ID
                    "thread_id": request.thread_id,              # 本次对话线程ID
                    "max_concurrency": settings.model_max_concurrency, # 系统配置的模型最大并发数
                },
            },
        )
        # 抛出503服务不可用标准异常，提示用户模型繁忙
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="模型任务繁忙，请稍后重试",
            # 响应头告知前端建议1秒后重试
            headers={"Retry-After": "1"},
        )

    try:
        # 成功拿到并发信号量，执行LangGraph RAG问答工作流，调用大模型中转接口
        result = memory_workflow.invoke(
            {"question": request.question},
            config=config,
        )
    finally:
        # 无论问答执行成功还是抛出异常，都强制释放并发信号量，防止死锁耗尽并发额度
        model_semaphore.release()
    # 计算智能体总耗时，秒转毫秒、保留2位小数
    agent_duration_ms = round((perf_counter() - agent_started_at) * 1000, 2)

    # 从工作流返回结果中提取回答主体数据
    answer = result["answer"]
    # 判断answer是否为Pydantic模型对象，存在model_dump方法则序列化为字典；否则直接使用原值
    answer_data = answer.model_dump() if hasattr(answer, "model_dump") else answer
    # 安全提取引用文献列表：仅当answer_data是字典时读取citations字段，无引用则返回空数组
    citations = answer_data.get("citations", []) if isinstance(answer_data, dict) else []

    # 打印INFO级别日志，标记智能体问答流程执行完成
    logger.info(
        "agent.answer.completed",
        extra={
            # 自定义日志事件标识，方便筛选问答完成记录
            "event": "agent.answer.completed",
            # 扩展业务详情字段，用于统计与排查问题
            "details": {
                # 当前登录用户ID，区分不同用户请求
                "user_id": user_id,
                # 当前对话线程ID，区分不同会话
                "thread_id": request.thread_id,
                # 智能体整体执行耗时（毫秒）
                "duration_ms": agent_duration_ms,
                # 本次回答引用的文献片段数量，用于统计资料检索覆盖率
                "citation_count": len(citations),
                # 读取流程执行轨迹列表，无数据则默认空数组，用于记录本轮问答所有运行过的节点
                "agent_trace": result.get("agent_trace", []),
                # 记录本次Supervisor分流选中的Agent标识，供日志/前端展示
                "selected_agent": (
                    # 存在分流决策对象时，取出决策指定的目标Agent名称
                    result["supervisor_decision"].next_agent
                    # 兜底判断：不存在分流决策时
                    if result.get("supervisor_decision")
                    # 无决策则标记为unknown未知类型
                    else "unknown"
                ),
                "degraded": result.get("degraded", False),
                "degradation_reasons": result.get(
                    "degradation_reasons",
                    [],
                ),
            },
        },
    )
    # 将问答结果返回给接口上层，序列化后响应给前端页面
    return answer
