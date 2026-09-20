"""FastAPI 应用入口：应用实例、全局中间件、按业务域挂载 router
路由实现已拆分到 app/routers/，本文件只做装配，不含业务逻辑"""
import logging
from time import perf_counter
from uuid import uuid4

# 导入FastAPI框架核心、请求对象、HTTP状态码工具
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

# 导入项目全局配置模块，读取限流开关、慢请求阈值等配置参数
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
# 从项目限流工具模块导入全局通用限流器，按客户端IP粒度管控全部接口请求频率
from app.rate_limit import global_rate_limiter
# 按业务域拆分的路由模块，挂载顺序即 /docs 展示顺序
from app.routers import (
    agents_tools,
    analytics,
    ask,
    auth,
    courses,
    documents,
    retrieval,
    system,
    tasks,
    threads,
)

# 执行全局日志初始化配置：开启控制台+JSONL文件双输出、加载自定义JSON日志格式化器
configure_logging()
# 获取api模块专属日志实例，命名空间为 scholarflow.api，用于打印接口相关业务日志
logger = get_logger("api")

# 初始化后端API服务实例，设置接口文档标题
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

# 挂载各业务域 router：顺序与原 openapi_tags 一致，即 /docs 里的展示顺序
app.include_router(system.router)          # 系统 + 运行监控
app.include_router(auth.router)            # 认证
app.include_router(threads.router)         # 会话
app.include_router(courses.router)         # 课程管理
app.include_router(documents.router)       # 文档管理
app.include_router(tasks.router)           # 任务中心
app.include_router(ask.router)             # 问答
app.include_router(analytics.router)       # 分析看板
app.include_router(retrieval.router)       # 检索调试
app.include_router(agents_tools.router)    # 学习工具
