# 兼容低版本Python，支持类内自身类型注解
from __future__ import annotations

# dataclass工具：dataclass定义指标数据结构，asdict将数据类转为字典用于输出快照
from dataclasses import asdict, dataclass
# 线程互斥锁，保证多并发请求读写指标数据不出现数据错乱
from threading import Lock


# 单个组件运行指标数据模型，存储某一类模块的全量统计数据
@dataclass
class ComponentMetrics:
    # 该组件总调用次数
    calls: int = 0
    # 调用成功次数
    successes: int = 0
    # 调用失败次数
    failures: int = 0
    # 调用过程中重试总次数
    retries: int = 0
    # 触发降级/兜底逻辑的次数（如LLM失败走关键词分流）
    fallbacks: int = 0
    # 该组件所有调用累计总耗时，单位毫秒
    total_duration_ms: float = 0.0


# 全局运行时指标采集管理器，线程安全，用于统计各节点、模型、MCP接口性能数据
class RuntimeMetrics:
    # 实例初始化
    def __init__(self) -> None:
        # 存储各组件指标，key为组件名称字符串，value为ComponentMetrics实例
        self._items: dict[str, ComponentMetrics] = {}
        # 线程锁，多请求并发记录指标时保证原子操作
        self._lock = Lock()

    # 记录单次组件调用的核心指标（成功/耗时/重试次数）
    def record(
        self,
        component: str,          # 组件标识，如supervisor、knowledge_agent、mcp_search
        *,
        success: bool,           # 本次调用是否成功
        duration_ms: float,      # 本次调用耗时，单位毫秒
        retries: int = 0,        # 本次调用执行的重试次数，默认0
    ) -> None:
        # 加锁，保证下方读写操作原子化，避免并发数据竞争
        with self._lock:
            # 组件不存在则自动新建ComponentMetrics实例，取出对应指标对象
            item = self._items.setdefault(component, ComponentMetrics())
            # 总调用次数+1
            item.calls += 1
            # 成功则成功计数+1，bool转int(True=1,False=0)
            item.successes += int(success)
            # 失败则失败计数+1
            item.failures += int(not success)
            # 累加重试次数，负数强制取0容错
            item.retries += max(0, retries)
            # 累加本次耗时，负数强制取0容错
            item.total_duration_ms += max(0.0, duration_ms)

    # 单独记录一次组件降级兜底触发事件
    def record_fallback(self, component: str) -> None:
        # 加锁保证并发安全
        with self._lock:
            # 不存在该组件指标则自动初始化
            item = self._items.setdefault(component, ComponentMetrics())
            # 降级触发计数+1
            item.fallbacks += 1

    # 生成全量指标快照，计算衍生指标（平均耗时），返回可序列化字典用于日志/监控上报
    def snapshot(self) -> dict[str, dict[str, float | int]]:
        # 加锁防止遍历过程中指标被修改
        with self._lock:
            # 定义快照最终输出容器
            result: dict[str, dict[str, float | int]] = {}
            # 遍历所有组件及其指标数据
            for name, item in self._items.items():
                # 将ComponentMetrics数据类转为普通字典
                data = asdict(item)
                # 计算单次调用平均耗时，保留2位小数；无调用则平均耗时0
                data["average_duration_ms"] = round(
                    item.total_duration_ms / item.calls,
                    2,
                ) if item.calls else 0.0
                # 总耗时四舍五入保留2位小数，优化展示
                data["total_duration_ms"] = round(
                    item.total_duration_ms,
                    2,
                )
                # 将当前组件完整指标存入快照结果
                result[name] = data
            # 返回组装完成的全量监控指标快照
            return result

    # 清空所有统计指标，仅用于自动化测试重置数据
    def reset(self) -> None:
        # 加锁清空指标存储字典，避免并发读写报错
        with self._lock:
            self._items.clear()


# 全局单例指标采集实例，项目全流程统一复用记录性能监控数据
runtime_metrics = RuntimeMetrics()