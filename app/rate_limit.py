# 兼容低版本Python，支持dataclass、类内部自引用注解
from __future__ import annotations

# 导入数据类装饰器，用于封装限流判断返回结果
from dataclasses import dataclass
# 向上取整函数，计算限流需要等待的秒数
from math import ceil
# 有界信号量：控制大模型并发调用上限；Lock：线程互斥锁，保证限流器线程安全
from threading import BoundedSemaphore, Lock
# monotonic单调时钟，不受系统时间修改影响，专门用于计算时间间隔
from time import monotonic

# 导入项目全局配置，读取限流窗口时长、模型最大并发数配置
from app.config import settings


# 冻结数据类，限流校验结果只读，防止外部篡改返回值
@dataclass(frozen=True)
class RateLimitDecision:
    # 是否允许本次请求通过限流
    allowed: bool
    # 当前窗口最大允许请求次数上限
    limit: int
    # 当前窗口剩余可请求次数
    remaining: int
    # 被限流时需要等待的秒数，放行时为0
    retry_after: int


class FixedWindowRateLimiter:
    """
    线程安全的进程内存固定窗口限流器
    基于内存实现，重启服务会清空计数；单进程部署可用，多进程需要Redis分布式限流
    """

    # 限流器实例初始化，传入窗口时长（单位秒）
    def __init__(self, window_seconds: int):
        # 窗口时长最小1秒，防止传入0/负数配置
        self.window_seconds = max(1, window_seconds)
        # 存储每个key的窗口起始时间 + 当前请求计数，格式 {标识key: (窗口开始时间, 请求次数)}
        self._entries: dict[str, tuple[float, int]] = {}
        # 线程互斥锁，多并发请求同时读写_entries字典时避免数据错乱
        self._lock = Lock()

    # 限流校验核心方法，传入唯一标识key、单窗口最大次数，返回限流判断结果
    def check(self, key: str, limit: int) -> RateLimitDecision:
        # 限制次数最小为1，兼容错误配置
        safe_limit = max(1, limit)
        # 获取单调时钟当前时间戳，用于窗口过期判断
        now = monotonic()

        # 加锁，保证下面读写字典是原子操作，并发无竞争
        with self._lock:
            # 读取当前key的窗口信息，无记录则新建窗口：当前时间、计数0
            window_started, count = self._entries.get(key, (now, 0))

            # 判断当前时间距离窗口开始超过窗口时长，窗口过期，重置新窗口
            if now - window_started >= self.window_seconds:
                window_started, count = now, 0

            # 当前窗口请求数达到上限，触发限流拒绝
            if count >= safe_limit:
                # 计算还剩多久窗口结束，向上取整，最小等待1秒
                retry_after = max(
                    1,
                    ceil(self.window_seconds - (now - window_started)),
                )
                # 返回拒绝结果，剩余次数0，携带等待时长
                return RateLimitDecision(
                    allowed=False,
                    limit=safe_limit,
                    remaining=0,
                    retry_after=retry_after,
                )

            # 未达到上限，计数+1
            count += 1
            # 更新当前key的窗口计数到内存字典
            self._entries[key] = (window_started, count)
            # 返回放行结果，计算剩余可用次数，无需等待
            return RateLimitDecision(
                allowed=True,
                limit=safe_limit,
                remaining=max(0, safe_limit - count),
                retry_after=0,
            )

    # 清空全部限流计数，仅测试/本地调试使用
    def reset(self) -> None:
        """只供自动测试或本地调试清空计数。"""
        # 加锁清空存储字典，避免并发读写报错
        with self._lock:
            self._entries.clear()


# 全局接口通用限流器，用于登录、注册、刷新等全部/auth接口限流
global_rate_limiter = FixedWindowRateLimiter(
    settings.rate_limit_window_seconds
)
# 问答接口独立限流器，/ask 模型对话单独限流，和登录接口配额隔离
ask_rate_limiter = FixedWindowRateLimiter(
    settings.rate_limit_window_seconds
)

# 注释说明：/ask问答接口是同步函数，FastAPI会把同步接口丢进线程池执行，使用线程信号量控制并发
# 有界信号量，限制同时调用大模型API的最大并发数量，防止并发过高打爆中转服务
model_semaphore = BoundedSemaphore(
    # 最小并发1，读取配置文件的模型最大并发数值
    value=max(1, settings.model_max_concurrency)
)