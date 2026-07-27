import logging
from time import perf_counter
from uuid import uuid4
# 导入FastAPI依赖注入、框架核心、异常、HTTP状态码工具
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
# 导入Bearer鉴权工具，用于解析请求头中的Authorization令牌
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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
)
# 导入全局认证权限存储单例（用户登录、线程归属校验）
from app.security import auth_store
# 导入项目全局配置模块，读取日志目录、日志等级等配置参数
from app.config import settings
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



# 执行全局日志初始化配置：开启控制台+JSONL文件双输出、加载自定义JSON日志格式化器
configure_logging()
# 获取api模块专属日志实例，命名空间为 scholarflow.api，用于打印接口相关业务日志
logger = get_logger("api")

# 初始化后端API服务实例，设置接口文档标题
app = FastAPI(title="ScholarFlow")
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
@app.get("/")
def root():
    return {
        "message": "ScholarFlow API is running",
        "docs": "http://127.0.0.1:8000/docs",
    }

# 健康检测接口，运维监控/负载均衡用于检测服务存活
@app.get("/health")
def health():
    return {"status": "ok"}


# FastAPI接口装饰器，定义GET存活探针路由，用于容器/集群检测服务进程是否存活
@app.get("/health/live")
def liveness():
    # 简单返回存活标识，只要进程正常运行就能响应，不校验业务依赖
    return {"status": "alive"}


# FastAPI接口装饰器，定义GET就绪探针路由，校验所有数据库、向量目录依赖是否可用
@app.get("/health/ready")
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
    # 调用存储层创建完整双Token会话：短期access、access过期、长效refresh、refresh过期
    access, access_exp, refresh, refresh_exp = auth_store.create_account_session(user_id)
    # 组装标准返回模型，封装用户ID、两套令牌及各自过期时间给前端
    return AccountSessionResponse(
        # 当前登录用户唯一标识
        user_id=user_id,
        # 短期业务鉴权令牌access_token
        access_token=access,
        # access_token的UTC过期ISO字符串
        expires_at=access_exp,
        # 长效续期刷新令牌refresh_token
        refresh_token=refresh,
        # refresh_token的UTC过期ISO字符串
        refresh_expires_at=refresh_exp,
    )


# 用户注册接口 POST /auth/register
# response_model 约束返回数据格式为账号会话模型；status_code=201 标准资源创建成功状态码
@app.post("/auth/register", response_model=AccountSessionResponse, status_code=201)
def register(request: RegisterRequest):
    try:
        # 调用存储层注册方法，传入前端标准化用户名、解密后的明文原始密码
        user_id = auth_store.register_user(
            request.username,
            # SecretStr专用方法，取出加密存储的原始明文密码用于哈希
            request.password.get_secret_value(),
        )
    # 捕获业务校验异常：用户名重复、用户名长度不足等ValueError
    except ValueError as exc:
        # 转换为409冲突接口异常，提示前端资源已存在（用户名重复）
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # 注册成功，生成双Token会话并返回给前端
    return account_response(user_id)


# 账号密码登录接口 POST /auth/login
# response_model 自动序列化双Token会话返回结构
@app.post("/auth/login", response_model=AccountSessionResponse)
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
@app.post("/auth/refresh", response_model=AccountSessionResponse)
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
    # 组装全新双Token会话返回，前端替换本地旧令牌
    return AccountSessionResponse(
        user_id=user_id,
        access_token=access,
        expires_at=access_exp,
        refresh_token=refresh,
        refresh_expires_at=refresh_exp,
    )


# 完整登出接口 POST /auth/logout
# 同时作废当前access短期令牌 + 传入的refresh长效刷新令牌，彻底下线登录会话
@app.post("/auth/logout")
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


# 登录会话创建接口，POST无鉴权，生成全新用户登录凭证，返回标准化会话结构体
# response_model 指定接口返回数据自动按SessionResponse模型校验、格式化
@app.post("/sessions", response_model=SessionResponse)
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
@app.get("/metrics/runtime")
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


# 核心问答接口，需携带Bearer Token鉴权
@app.post("/ask")
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

# 查询指定会话线程信息接口，需要鉴权并校验线程归属
@app.get("/threads/{thread_id}")
def get_thread(thread_id: str, session: tuple[str, str] = Depends(current_session)):
    user_id, _token = session
    # 校验当前登录用户是否拥有该线程访问权限，无权限直接抛异常
    require_owner(user_id, thread_id)
    # 从SQLite持久化存储读取该线程全部状态快照
    state = memory_workflow.get_state(
        {"configurable": {"thread_id": thread_id}}
    )
    # 组装线程信息返回：线程ID、是否存在、历史对话总条数
    return {
        "thread_id": thread_id,
        "exists": bool(state.values),
        "history_count": len(state.values.get("history", [])),
    }

# 删除指定会话线程接口，清空对话记忆与权限绑定关系
@app.delete("/threads/{thread_id}")
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
@app.get("/sessions/current")
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
@app.post("/sessions/refresh", response_model=SessionResponse)
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
@app.delete("/sessions/current")
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
