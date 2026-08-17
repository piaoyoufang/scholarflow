import logging
import re
from pathlib import Path
from time import perf_counter
from uuid import uuid4
# 导入FastAPI依赖注入、框架核心、异常、HTTP状态码工具
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
# 导入Bearer鉴权工具，用于解析请求头中的Authorization令牌
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

# 导入持久化会话存储、带记忆的Agent流程图实例
from app.graph.builder import memory_store, memory_workflow
# 导入请求校验模型、登录会话返回结构化模型
from app.schemas import (
    AccountSessionResponse,
    AskRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    SessionResponse,
    CourseCreateRequest,
    CourseJoinRequest,
    CourseMemberAddRequest,
)
# 导入全局认证权限存储单例（用户登录、线程归属校验）
from app.security import auth_store
# 导入项目全局配置模块，读取日志目录、日志等级等配置参数
from app.config import PROJECT_ROOT, settings
from app.ingestion.loader import ingest
# 导入可观测性日志工具包内三个核心日志工具
from app.observability import (
    # 全局日志初始化配置函数，配置控制台+文件双输出、JSON日志格式化
    configure_logging,
    # 分模块获取日志器的工具函数，生成scholarflow.xxx命名空间日志对象
    get_logger,
    # 请求上下文变量，存储单次HTTP请求唯一request_id，全链路日志自动携带追踪ID
    request_id_context,
)
# 从项目限流工具模块导入三类限流控制全局对象
from app.rate_limit import (
    # 问答接口独立固定窗口限流器，专门管控 /ask RAG对话请求频率
    ask_rate_limiter,
    # 全局通用限流器，管控登录、注册、刷新等/auth账号接口请求频率
    global_rate_limiter,
    # 大模型并发控制信号量，限制同时调用模型中转API的并发请求数量
    model_semaphore,
)
# 导入全局运行时指标单例，统一采集各模型、MCP工具、Agent的调用耗时、成败、降级次数监控数据
from app.runtime_metrics import runtime_metrics
# 导入服务健康就绪检查函数，用于接口校验数据库、向量目录等存储资源是否正常就绪
from app.health import readiness_report
# 从 app 包下 courses 模块里的 store 文件，导入全局单例对象 course_store
from app.courses.store import course_store
# 从 app.knowledge.library 模块导入全局单例对象 knowledge_library
from app.knowledge.library import knowledge_library
# 导入FastAPI后台任务组件：可以把函数丢到接口返回之后异步执行，不用额外写线程代码
from fastapi import BackgroundTasks
# 导入任务存储单例，用来创建 ingestion任务、读写任务数据库
from app.tasks.store import task_store
# 导入文档处理异步任务函数，真正执行文档解析、切块、向量入库逻辑
from app.tasks.ingestion import run_ingestion_task
# 导入调试检索工具函数，输出RAG召回的完整中间结果，用于排查检索效果
from app.retrieval.debug import debug_retrieval
# 导入Pydantic请求模型：接收前端提交生成学习计划的请求参数(goal、days、difficulty、daily_minutes)
from app.schemas import LearningPlanRequest
# 导入业务函数：基于课程知识库RAG+大模型生成结构化学习计划的核心逻辑
from app.agents.learning_plan import generate_learning_plan
# 导入Pydantic请求模型，接收前端生成测验题的入参（topic、question_count、question_type、difficulty）
from app.schemas import QuizRequest
# 导入出题业务函数，内部完成RAG检索+大模型结构化输出，返回QuizResponse对象
from app.agents.quiz import generate_quiz
from app.learning_history.store import learning_history_store
# 从分析模块的qa_events文件导入全局单例对象 qa_event_store
from app.analytics.qa_events import qa_event_store
# 导入反馈存储单例对象，调用create_feedback / summary / recent_down_feedback等数据库方法
from app.feedback.store import feedback_store
from app.cache import delete_prefix, get_json, set_json
# 导入Pydantic请求模型FeedbackRequest，用于接口接收校验前端提交的JSON请求体
from app.schemas import FeedbackRequest
# 从 app/schemas 模块导入Pydantic请求体模型 QAEventProcessRequest
from app.schemas import QAEventProcessRequest


# 执行全局日志初始化配置：开启控制台+JSONL文件双输出、加载自定义JSON日志格式化器
configure_logging()
# 获取api模块专属日志实例，命名空间为 scholarflow.api，用于打印接口相关业务日志
logger = get_logger("api")

# 初始化后端API服务实例，设置接口文档标题
app = FastAPI(
    title="高校课程AI学习助手平台",
    openapi_tags=[
        {"name": "系统", "description": "服务首页、健康检查、存活检查和就绪检查。"},
        {"name": "认证", "description": "注册、登录、刷新令牌和退出登录。"},
        {"name": "会话", "description": "会话、线程和历史对话记录管理。"},
        {"name": "课程管理", "description": "课程创建、课程查询和课程成员管理。"},
        {"name": "文档管理", "description": "课程文档上传、删除、重新入库和文档列表查询。"},
        {"name": "任务中心", "description": "异步上传、文档入库等后台任务查询。"},
        {"name": "问答", "description": "课程问答、全局问答、问答反馈和问答事件处理。"},
        {"name": "分析看板", "description": "课程看板、高频问题、无引用问题和低质量问题分析。"},
        {"name": "检索调试", "description": "查看检索召回过程和命中文档片段。"},
        {"name": "学习工具", "description": "学习计划生成和自动出题。"},
        {"name": "运行监控", "description": "运行时指标和系统调用统计。"},
    ],
)
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


# FastAPI 全局HTTP请求限流中间件，所有接口进入时先做IP粒度全局限流校验
@app.middleware("http")
async def limit_http_request(request: Request, call_next):
    # 判断配置是否开启限流，关闭限流则直接放行请求，跳过所有限流逻辑
    if not settings.rate_limit_enabled:
        return await call_next(request)

    # 取出客户端IP，无客户端信息时标记为unknown
    client_ip = request.client.host if request.client else "unknown"
    # 拼接限流唯一标识：以IP作为区分key，实现单IP独立计数窗口
    key = f"ip:{client_ip}"
    # 调用全局限流器执行校验，传入IP标识、配置文件中单窗口最大请求次数
    decision = global_rate_limiter.check(
        key,
        settings.rate_limit_max_requests,
    )

    # 限流判定：当前IP窗口请求数达到上限，拒绝本次请求
    if not decision.allowed:
        # 打印WARNING级别限流拦截日志，用于统计恶意高频访问
        logger.warning(
            "rate_limit.blocked",
            extra={
                # 自定义日志事件标识，筛选限流拦截记录专用
                "event": "rate_limit.blocked",
                # 扩展业务字段，记录拦截完整元数据
                "details": {
                    "scope": "ip",                     # 限流维度：按IP限流
                    "client_ip": client_ip,            # 被拦截的客户端IP
                    "path": request.url.path,          # 被拦截的接口路径
                    "retry_after": decision.retry_after# 需要等待多少秒后重试
                },
            },
        )
        # 返回标准429请求过多响应
        return JSONResponse(
            # HTTP 429 标准状态码：请求频率超限
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            # 返回给前端的业务错误提示
            content={"detail": "请求过于频繁，请稍后重试"},
            # 写入限流标准响应头，前端可读取限流相关信息
            headers={
                "Retry-After": str(decision.retry_after),          # 建议等待秒数
                "X-RateLimit-Limit": str(decision.limit),          # 窗口最大允许请求数
                "X-RateLimit-Remaining": "0",                     # 当前窗口剩余可用次数（已用尽为0）
            },
        )

    # 未触发限流，放行请求执行接口逻辑，拿到接口原始响应
    response = await call_next(request)
    # 在正常响应头中追加限流配额信息，前端展示剩余可请求次数
    response.headers["X-RateLimit-Limit"] = str(decision.limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    # 把携带限流头的响应返回给前端
    return response


# FastAPI全局HTTP请求中间件，所有接口请求都会先经过此函数
@app.middleware("http")
async def observe_http_request(request: Request, call_next):
    """
    请求链路观测中间件
    1. 生成/复用请求追踪ID，存入全局上下文，全链路日志自动携带request_id
    2. 统计接口执行耗时毫秒数
    3. 正常请求打印完成日志，慢请求自动提升为WARN级别日志
    4. 捕获全局未处理异常，打印带堆栈的错误日志后向上抛出
    5. 响应头回传X-Request-ID给前端，用于问题定位
    6. 请求结束清理上下文变量，避免不同请求ID串扰
    """
    # 从前端请求头读取用户传入的X-Request-ID追踪标识
    incoming_request_id = request.headers.get("X-Request-ID", "").strip()
    # 截断外部传入ID最大128字符；无传入则自动生成全新UUID作为request_id
    request_id = incoming_request_id[:128] or str(uuid4())
    # 将当前请求ID存入全局上下文变量，保存重置句柄用于finally释放
    context_token = request_id_context.set(request_id)
    # 记录请求开始高精度时间戳，用于计算接口耗时
    started_at = perf_counter()

    try:
        # 放行请求到对应的接口函数，等待接口执行完成拿到响应对象
        response = await call_next(request)
    except Exception:
        # 捕获接口抛出的所有未处理异常，计算本次请求总耗时(毫秒)，保留两位小数
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        # 打印ERROR级异常日志，logger.exception会自动追加完整异常堆栈信息
        logger.exception(
            "request.failed",
            extra={
                # 自定义事件标识，日志过滤使用
                "event": "request.failed",
                # 扩展业务字段：请求方法、路径、耗时
                "details": {
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            },
        )
        # 向上抛出异常，交给FastAPI全局异常处理器返回标准错误响应
        raise
    else:
        # 无异常分支：计算接口执行总耗时毫秒
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        # 在返回给前端的响应头中塞入本次请求追踪ID，方便前端反馈问题时提供
        response.headers["X-Request-ID"] = request_id

        # 判断是否为慢请求：耗时超过配置阈值则日志级别设为WARNING，否则INFO
        log_level = (
            logging.WARNING
            if duration_ms >= settings.slow_request_ms
            else logging.INFO
        )
        # 打印请求正常完成日志，携带完整请求元数据
        logger.log(
            log_level,
            "request.completed",
            extra={
                # 正常完成事件标记
                "event": "request.completed",
                # 完整请求详情：请求方式、接口路径、HTTP状态码、耗时
                "details": {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                },
            },
        )
        # 把构造好的响应对象返回给前端
        return response
    finally:
        # 无论请求成功/异常，都强制清空上下文request_id，防止多个请求ID互相污染
        request_id_context.reset(context_token)


# 首页根路径接口，访问展示服务运行状态与文档地址
@app.get("/", tags=["系统"], summary="服务首页")
def root():
    return {
        "message": "ScholarFlow API is running",
        "docs": "http://127.0.0.1:8000/docs",
    }

# 健康检测接口，运维监控/负载均衡用于检测服务存活
@app.get("/health", tags=["系统"], summary="健康检查")
def health():
    return {"status": "ok"}


# FastAPI接口装饰器，定义GET存活探针路由，用于容器/集群检测服务进程是否存活
@app.get("/health/live", tags=["系统"], summary="存活检查")
def liveness():
    # 简单返回存活标识，只要进程正常运行就能响应，不校验业务依赖
    return {"status": "alive"}


# FastAPI接口装饰器，定义GET就绪探针路由，校验所有数据库、向量目录依赖是否可用
@app.get("/health/ready", tags=["系统"], summary="就绪检查")
def readiness():
    # 执行全量存储资源健康检查，获取数据库、向量目录状态报告
    report = readiness_report()
    # 判断任意存储资源异常，服务未就绪
    if not report["ready"]:
        # 抛出503服务不可用异常，携带完整故障明细给负载均衡/容器编排
        raise HTTPException(
            # HTTP状态码503：服务暂时无法处理请求
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            # detail携带完整检查明细，方便运维定位故障库/目录
            detail=report,
        )
    # 全部存储资源正常，返回健康明细报告
    return report



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


@app.post("/auth/register", response_model=AccountSessionResponse, status_code=201, tags=["认证"], summary="注册账号")
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
@app.post("/auth/login", response_model=AccountSessionResponse, tags=["认证"], summary="账号登录")
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
@app.post("/auth/refresh", response_model=AccountSessionResponse, tags=["认证"], summary="刷新登录令牌")
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
@app.post("/auth/logout", tags=["认证"], summary="退出登录")
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


# 创建课程接口 POST /courses
@app.post("/courses", tags=["课程管理"], summary="创建课程")
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
@app.get("/courses", tags=["课程管理"], summary="获取课程列表")
def list_courses(session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    cache_key = f"user:{user_id}:courses"
    cached = get_json(cache_key)
    if cached is not None:
        return cached
    result = {"courses": course_store.list_user_courses(user_id)}
    set_json(cache_key, result)
    return result


@app.post("/courses/join", tags=["课程管理"], summary="通过课程码加入课程")
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


@app.get("/courses/{course_id}", tags=["课程管理"], summary="获取课程详情")
def get_course(course_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    try:
        course_store.require_course_access(course_id, user_id)
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
@app.post("/courses/{course_id}/members", tags=["课程管理"], summary="添加课程成员")
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
@app.get("/courses/{course_id}/members", tags=["课程管理"], summary="获取课程成员")
def list_course_members(course_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _ = session
    try:
        # 权限校验：只有课程老师才可以查看成员列表
        course_store.require_course_teacher(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    # 查询并返回课程所有成员
    return {"members": course_store.list_members(course_id)}

# 获取课程下全部文档列表接口 GET /courses/{course_id}/documents
@app.get("/courses/{course_id}/documents", tags=["文档管理"], summary="获取课程文档列表")
def list_course_documents(course_id: str, session: tuple[str, str] = Depends(current_session)):
    # 从登录会话元组解包，拿到当前登录用户ID，下划线表示token本接口不使用
    user_id, _ = session
    try:
        # 权限校验：课程必须存在，当前用户必须是该课程成员（老师/学生均可查看文档列表）
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        # 捕获课程不存在异常，返回HTTP 404，from exc保留原始异常堆栈信息，方便日志排查
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        # 捕获没有课程访问权限异常，返回HTTP 403禁止访问
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    # 校验通过，调用知识库存储层，查询该课程所有文档，返回给前端
    return {"documents": knowledge_library.list_course_documents(course_id)}

# 定义DELETE接口：删除课程下指定文档，路径参数：课程id、文档source_id
@app.delete("/courses/{course_id}/documents/{source_id}", tags=["文档管理"], summary="删除课程文档")
def delete_course_document(
    course_id: str,
    source_id: str,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
        document = knowledge_library.get_document(source_id)
        if not document or document["course_id"] != course_id:
            raise LookupError("文档不存在")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    deleted = knowledge_library.delete_document_record(source_id)
    if settings.vector_backend.lower() == "qdrant":
        from app.vectorstores.qdrant_store import delete_by_source_id
        delete_by_source_id(source_id)
    else:
        from langchain_chroma import Chroma
        from app.models import embeddings
        db = Chroma(
            collection_name="scholarflow",
            embedding_function=embeddings(),
            persist_directory=settings.vector_db_dir,
        )
        db.delete(where={"source_id": source_id})

    file_path = Path(deleted["file_path"])
    file_path.unlink(missing_ok=True)
    delete_prefix(f"course:{course_id}:")
    return {"deleted": True, "source_id": source_id, "filename": deleted["original_name"]}
@app.post("/courses/{course_id}/documents/{source_id}/reingest", tags=["文档管理"], summary="重新入库课程文档")
def reingest_course_document(
    # 路径参数：课程ID
    course_id: str,
    # 路径参数：目标文档的source_id
    source_id: str,
    # FastAPI内置后台任务对象，把耗时的文档解析任务放到后台异步执行，不阻塞HTTP响应
    background_tasks: BackgroundTasks,
    # 依赖注入：校验登录会话，返回(user_id, token)，未登录直接返回401
    session: tuple[str, str] = Depends(current_session),
):
    # 解包会话，获取当前登录用户ID，丢弃token
    user_id, _ = session
    try:
        # 权限校验：只有该课程的教师，才有权限重新向量化文档，学生无权限
        course_store.require_course_teacher(course_id, user_id)
        # 根据source_id从SQLite查询文档元数据记录
        document = knowledge_library.get_document(source_id)
        # 校验：文档不存在，或者文档所属课程和URL传入course_id不一致，防止跨课程越权操作
        if not document or document["course_id"] != course_id:
            raise LookupError("文档不存在")
    # 捕获查找异常，返回404
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # 捕获权限异常，不是教师返回403禁止访问
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 取出数据库存储的原始文件路径，转为Path对象
    file_path = Path(document["file_path"])
    # 判断磁盘上原始文件是否还存在，文件丢失则无法重新解析，直接报错返回
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="原始文件不存在，无法重新入库")

    # 更新SQLite文档状态为processing处理中，重置chunk_count为0
    knowledge_library.update_status(source_id, "processing", chunk_count=0)
    delete_prefix(f"course:{course_id}:")

    # 在task_store任务表创建一条异步任务记录，拿到task_id
    task_id = task_store.create_task(
        course_id=course_id,
        source_id=source_id,
        owner_user_id=user_id,
    )

    # 添加后台异步任务，HTTP接口立刻返回，文档解析向量化在后台跑
    background_tasks.add_task(
        run_ingestion_task,       # 需要后台执行的函数：文档摄入任务
        task_id,                  # 参数1：任务id，用于更新任务进度
        source_id,                # 参数2：文档source_id
        str(file_path),           # 参数3：原始文件路径（转字符串）
        course_id,                # 参数4：课程id，写入向量metadata做隔离
    )

    # 接口直接返回，不等待文档处理完成；前端拿着task_id轮询/tasks/{task_id}查询进度
    return {
        "task_id": task_id,
        "source_id": source_id,
        "status": "pending",
        "message": "已创建重新入库任务",
    }


@app.post("/courses/{course_id}/documents/upload-async", tags=["文档管理"], summary="异步上传课程文档")
async def upload_course_document_async(
    course_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: tuple[str, str] = Depends(current_session),
):
    """
    课程级异步上传接口。

    作用：
    1. 校验当前用户必须是课程老师。
    2. 把上传文件保存到 data/raw/uploads/courses/{course_id}/。
    3. 在 documents.sqlite 里登记一条 processing 文档记录。
    4. 在 tasks.sqlite 里创建一条 pending 后台任务。
    5. 把真正耗时的解析、切块、embedding、Chroma 入库放到后台执行。
    """
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    filename = safe_upload_name(file.filename or "")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="只支持 PDF、TXT 和 Markdown 文件",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件不能超过 10 MB")
    if not content:
        raise HTTPException(status_code=400, detail="不能上传空文件")

    upload_dir = UPLOAD_DIR / "courses" / course_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_name = f"{uuid4().hex}_{filename}"
    target = upload_dir / saved_name
    target.write_bytes(content)

    document = knowledge_library.register_document(
        course_id=course_id,
        uploader_user_id=user_id,
        original_name=filename,
        saved_name=saved_name,
        file_path=str(target),
        file_type=suffix.lstrip("."),
        file_size=len(content),
        status="processing",
    )
    task_id = task_store.create_task(
        course_id=course_id,
        source_id=document.source_id,
        owner_user_id=user_id,
    )

    delete_prefix(f"course:{course_id}:")
    delete_prefix(f"course:{course_id}:")
    background_tasks.add_task(
        run_ingestion_task,
        task_id,
        document.source_id,
        str(target),
        course_id,
    )

    return {
        "task_id": task_id,
        "source_id": document.source_id,
        "filename": document.original_name,
        "status": "pending",
        "message": "文件已上传，后台正在解析、切块和向量入库",
    }


@app.get("/courses/{course_id}/tasks", tags=["任务中心"], summary="查看课程任务列表")
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

@app.get("/tasks/{task_id}", tags=["任务中心"], summary="查看任务详情")
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

@app.post("/courses/{course_id}/ask", tags=["问答"], summary="课程内问答")
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
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        # 捕获异常：course_id不存在，返回404
        # from exc：保留原始异常堆栈，方便后台日志排查
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        # 捕获异常：课程存在，但用户没有访问权限，返回403禁止访问
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

# PATCH接口：局部更新问答事件处理状态，路径携带课程id和事件id
@app.patch("/courses/{course_id}/qa-events/{event_id}/status", tags=["问答"], summary="更新问答事件处理状态")
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
@app.get("/courses/{course_id}/dashboard", tags=["分析看板"], summary="获取课程看板")
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
@app.post("/courses/{course_id}/feedback", tags=["问答"], summary="提交问答反馈")
def create_feedback(
    course_id: str,
    request: FeedbackRequest,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_access(course_id, user_id)
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
@app.get("/courses/{course_id}/analytics/top-questions", tags=["分析看板"], summary="获取高频问题")
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
@app.get("/courses/{course_id}/analytics/no-citation", tags=["分析看板"], summary="获取无引用问题")
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
@app.get("/courses/{course_id}/analytics/low-quality", tags=["分析看板"], summary="获取低质量问题")
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
@app.post("/courses/{course_id}/retrieval/debug", tags=["检索调试"], summary="检索调试")
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

# FastAPI POST接口路由：为指定课程生成AI学习计划
@app.post("/courses/{course_id}/agents/learning-plan", tags=["学习工具"], summary="生成学习计划")
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
    result = generate_learning_plan(
        course_id=course_id,                # 传递课程ID，让RAG检索只读取本课程文档，实现知识库隔离
        goal=request.goal,                  # 用户学习目标，来自请求体
        days=request.days,                  # 计划总天数，来自请求体
        difficulty=request.difficulty,      # 难度等级 beginner/intermediate/advanced，来自请求体
        daily_minutes=request.daily_minutes,# 每日学习分钟数，来自请求体
    )
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


@app.get("/courses/{course_id}/agents/learning-plan/history", tags=["学习工具"], summary="获取学习计划历史")
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


@app.get("/courses/{course_id}/agents/learning-plan/history/{record_id}", tags=["学习工具"], summary="获取学习计划历史详情")
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


@app.delete("/courses/{course_id}/agents/learning-plan/history/{record_id}", tags=["学习工具"], summary="删除学习计划历史")
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
@app.post("/courses/{course_id}/agents/quiz", tags=["学习工具"], summary="生成测验题")
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
    result = generate_quiz(
        course_id=course_id,                # 传递课程ID，用于RAG知识库隔离
        topic=request.topic,                # 出题主题，取自前端请求体
        question_count=request.question_count, # 题目数量，取自前端请求体
        question_type=request.question_type,   # 题型，取自前端请求体
        difficulty=request.difficulty,          # 难度，取自前端请求体
    )
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


@app.get("/courses/{course_id}/agents/quiz/history", tags=["学习工具"], summary="获取自动出题历史")
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


@app.get("/courses/{course_id}/agents/quiz/history/{record_id}", tags=["学习工具"], summary="获取自动出题历史详情")
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


@app.delete("/courses/{course_id}/agents/quiz/history/{record_id}", tags=["学习工具"], summary="删除自动出题历史")
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


# 登录会话创建接口，POST无鉴权，生成全新用户登录凭证，返回标准化会话结构体
# response_model 指定接口返回数据自动按SessionResponse模型校验、格式化
@app.post("/sessions", response_model=SessionResponse, tags=["会话"], summary="创建会话")
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


# FastAPI接口装饰器，定义GET请求路由，用于查询全系统运行时性能监控指标
@app.get("/metrics/runtime", tags=["运行监控"], summary="查看运行时指标")
def get_runtime_metrics(
    # 依赖注入校验当前登录会话，返回(user_id, token)二元组，未登录会直接拦截请求
    session: tuple[str, str] = Depends(current_session),
):
    # 解包会话元组，提取用户ID（token此处无业务使用，下划线丢弃）
    user_id, _token = session
    # 组装并返回监控指标响应体
    return {
        # 当前请求操作者的用户ID，用于接口访问日志溯源
        "user_id": user_id,
        # 调用全局指标单例生成完整统计快照，包含各组件调用次数、耗时、失败、降级数据
        "components": runtime_metrics.snapshot(),
    }


UPLOAD_DIR = PROJECT_ROOT / "data" / "raw" / "uploads"
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".txt", ".md"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def safe_upload_name(filename: str) -> str:
    """Remove path traversal and characters unsafe on Windows/Linux."""
    original = Path(filename).name
    suffix = Path(original).suffix.lower()
    stem = re.sub(
        r"[^A-Za-z0-9_\-\u4e00-\u9fff]",
        "_",
        Path(original).stem,
    ).strip("._")
    stem = stem[:80] or "uploaded_document"
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"uploaded_{stem}"
    return f"{stem}{suffix}"


@app.post("/documents/upload", tags=["文档管理"], summary="上传文档")
async def upload_document(
    file: UploadFile = File(...),
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _token = session
    filename = safe_upload_name(file.filename or "")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="只支持 PDF、TXT 和 Markdown 文件",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件不能超过 10 MB")
    if not content:
        raise HTTPException(status_code=400, detail="不能上传空文件")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / filename
    previous_content = target.read_bytes() if target.exists() else None
    target.write_bytes(content)
    try:
        chunk_count = await run_in_threadpool(ingest, str(target))
    except Exception as exc:
        if previous_content is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(previous_content)
        logger.exception(
            "document.upload.failed",
            extra={
                "event": "document.upload.failed",
                "details": {"user_id": user_id, "filename": filename},
            },
        )
        raise HTTPException(
            status_code=422,
            detail="文档解析或入库失败，请检查文件内容后重试",
        ) from exc

    logger.info(
        "document.upload.completed",
        extra={
            "event": "document.upload.completed",
            "details": {
                "user_id": user_id,
                "filename": filename,
                "chunk_count": chunk_count,
            },
        },
    )
    return {"filename": filename, "chunk_count": chunk_count}


# 核心问答接口，需携带Bearer Token鉴权
@app.post("/ask", tags=["问答"], summary="全局问答")
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

# 查询当前用户拥有的全部会话线程，用于前端刷新页面/重启容器后找回历史入口
@app.get("/threads", tags=["会话"], summary="获取线程列表")
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
@app.get("/threads/{thread_id}", tags=["会话"], summary="获取线程详情")
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
@app.delete("/threads/{thread_id}", tags=["会话"], summary="删除线程")
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
@app.get("/sessions/current", tags=["会话"], summary="获取当前登录会话")
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
@app.post("/sessions/refresh", response_model=SessionResponse, tags=["会话"], summary="刷新当前会话")
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
@app.delete("/sessions/current", tags=["会话"], summary="清除当前会话")
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

