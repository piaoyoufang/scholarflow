# 兼容低版本Python，支持函数、类内部自引用泛型注解
from __future__ import annotations

# 异步IO库，用于异步休眠等待重试间隔
import asyncio
# 类型抽象：Awaitable 异步可等待对象，Callable 可调用函数
from collections.abc import Awaitable, Callable
# perf_counter高精度计时器统计耗时；sleep同步阻塞休眠
from time import perf_counter, sleep
# 泛型类型变量，统一包装函数返回值类型
from typing import TypeVar

# 项目全局配置，读取重试基础间隔参数
from app.config import settings
# 全局性能指标单例，记录组件调用次数、耗时、重试、成败
from app.runtime_metrics import runtime_metrics

# 定义泛型T，代表被重试函数的返回值类型，实现类型提示通用化
T = TypeVar("T")


def run_with_retry(
    # 需要执行、支持重试的同步业务函数
    operation: Callable[[], T],
    *,
    # 当前统计的组件名称，用于指标区分（如mcp、fast_model）
    component: str,
    # 最大重试次数，不传则读取配置文件默认值
    max_attempts: int | None = None,
) -> T:
    # 计算总执行次数：最小1次，优先使用传入值，无传参则读取全局配置模型最大重试次数
    attempts = max(1, max_attempts or settings.model_max_attempts)
    # 记录整个重试流程的起始高精度时间戳，用于计算总耗时
    started_at = perf_counter()

    # 循环执行，attempt从1到总次数（包含首次执行）
    for attempt in range(1, attempts + 1):
        try:
            # 执行传入的同步业务逻辑函数
            result = operation()
        except Exception:
            # 当前是最后一次尝试，不再重试
            if attempt >= attempts:
                # 记录本次组件调用失败指标
                runtime_metrics.record(
                    component,
                    success=False,
                    # 总耗时秒转毫秒
                    duration_ms=(perf_counter() - started_at) * 1000,
                    # 实际重试次数 = 当前轮次 - 首次执行
                    retries=attempt - 1,
                )
                # 抛出原始异常，上层业务捕获处理
                raise
            # 指数退避休眠：基础延迟 * 2^(当前轮次-1)，越往后等待越久
            sleep(settings.retry_base_delay_seconds * (2 ** (attempt - 1)))
        else:
            # 函数无异常执行成功，记录成功指标
            runtime_metrics.record(
                component,
                success=True,
                duration_ms=(perf_counter() - started_at) * 1000,
                retries=attempt - 1,
            )
            # 成功直接返回业务函数结果，终止重试循环
            return result

    # 理论代码不会走到此处，仅用于语法补全，抛出兜底运行异常
    raise RuntimeError("同步重试执行器到达不可达分支")


async def run_async_with_retry(
    # 需要执行、支持重试的异步业务函数
    operation: Callable[[], Awaitable[T]],
    *,
    # 当前统计组件名称，用于监控指标分类
    component: str,
    # 单次异步操作最大超时时间（秒）
    timeout_seconds: float,
    # 最大尝试总次数（首次执行+重试次数）
    max_attempts: int,
) -> T:
    # 总执行次数最小为1，避免传入0/负数
    attempts = max(1, max_attempts)
    # 记录整个异步重试流程起始时间戳，统计总耗时
    started_at = perf_counter()

    # 循环执行，包含首次执行+多次重试
    for attempt in range(1, attempts + 1):
        try:
            # 带超时执行异步函数，最小超时0.1秒防止配置为0阻塞永久
            result = await asyncio.wait_for(
                operation(),
                timeout=max(0.1, timeout_seconds),
            )
        except Exception:
            # 最后一次尝试失败，不再重试
            if attempt >= attempts:
                # 记录组件调用失败监控指标
                runtime_metrics.record(
                    component,
                    success=False,
                    duration_ms=(perf_counter() - started_at) * 1000,
                    retries=attempt - 1,
                )
                # 向上抛出原始异常
                raise
            # 异步指数退避休眠，不阻塞事件循环
            await asyncio.sleep(
                settings.retry_base_delay_seconds * (2 ** (attempt - 1))
            )
        else:
            # 异步函数执行无异常，记录成功监控指标
            runtime_metrics.record(
                component,
                success=True,
                duration_ms=(perf_counter() - started_at) * 1000,
                retries=attempt - 1,
            )
            # 返回异步执行结果，终止重试流程
            return result

    # 语法兜底异常，正常逻辑永远不会触发
    raise RuntimeError("异步重试执行器到达不可达分支")