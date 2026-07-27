# 导入json序列化工具，用于将日志字典转为JSON字符串写入文件/控制台
import json
# Python标准日志模块，实现项目全链路日志采集、分级输出
import logging
# 系统标准输出流对象，控制台日志打印依赖
import sys
# 上下文变量，用于在单个HTTP请求全程共享request_id，跨函数传递请求标识
from contextvars import ContextVar
# 日期时间+UTC标准时区，统一日志时间戳，避免本地时区偏差
from datetime import datetime, timezone
# 路径工具类，统一日志目录、日志文件路径处理
from pathlib import Path

# 导入项目全局配置：项目根目录、日志存放目录、日志输出级别配置
from app.config import PROJECT_ROOT, settings


# 全局请求上下文变量：存储当前HTTP请求唯一ID，同一次接口调用所有日志共用该ID
# 所有函数无需传参，直接读取即可绑定请求链路，默认值"-"代表无请求上下文
request_id_context: ContextVar[str] = ContextVar(
    "request_id",
    default="-",
)


class JsonFormatter(logging.Formatter):
    """
    自定义日志格式化器
    将原生Python日志对象转换成单行JSON格式，输出jsonl标准日志文件，便于日志检索工具解析
    """

    # 重写格式化方法，接收单条日志记录对象，返回JSON字符串
    def format(self, record: logging.LogRecord) -> str:
        # 初始化标准日志JSON载荷，固定基础字段
        payload = {
            # UTC标准时间戳ISO格式，全局统一时区
            "timestamp": datetime.now(timezone.utc).isoformat(),
            # 日志级别：INFO/WARN/ERROR/DEBUG
            "level": record.levelname,
            # 日志器名称，区分模块（scholarflow.auth / scholarflow.api等）
            "logger": record.name,
            # 自定义事件名，没有则使用日志消息兜底
            "event": getattr(record, "event", record.getMessage()),
            # 日志主体文本消息
            "message": record.getMessage(),
            # 当前请求唯一ID，链路追踪核心标识
            "request_id": request_id_context.get(),
        }

        # 读取日志额外携带的details扩展字段（接口参数、用户ID、Token等业务数据）
        details = getattr(record, "details", None)
        # 如果存在扩展业务数据，加入JSON载荷
        if details is not None:
            payload["details"] = details

        # 如果日志包含异常堆栈（报错日志），格式化异常信息存入exception字段
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # 序列化为JSON字符串，关闭ASCII转义（正常显示中文），未知类型统一转为字符串
        return json.dumps(payload, ensure_ascii=False, default=str)


def log_file_path() -> Path:
    """
    计算日志文件完整绝对路径
    兼容配置内相对/绝对目录，统一基于项目根目录拼接日志文件
    :return: 日志文件Path对象 scholarflow.jsonl
    """
    # 读取配置中日志目录字符串
    directory = Path(settings.log_dir)
    # 判断配置是相对路径，拼接项目根目录转为绝对路径
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    # 拼接日志文件名，返回完整文件路径
    return directory / "scholarflow.jsonl"


def configure_logging() -> None:
    """
    项目日志全局初始化配置函数
    同时开启双输出：控制台打印 + jsonl日志文件持久化存储
    防止uvicorn热重载重复初始化日志、重复打印日志
    """
    # 获取项目根日志器总入口 scholarflow
    logger = logging.getLogger("scholarflow")

    # 标记判断：如果已经完成日志配置，直接返回，避免热重载重复添加处理器
    if getattr(logger, "_scholarflow_configured", False):
        return

    # 读取配置中的日志级别字符串，统一转大写
    level_name = settings.log_level.upper()
    # 映射为logging标准级别，读取失败默认INFO级别
    level = getattr(logging, level_name, logging.INFO)
    # 实例化自定义JSON格式化器
    formatter = JsonFormatter()

    # 获取日志文件完整路径
    file_path = log_file_path()
    # 自动创建日志目录，多级文件夹不存在自动生成
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # 控制台输出处理器：输出到标准输出stdout
    console_handler = logging.StreamHandler(sys.stdout)
    # 控制台日志使用JSON格式化
    console_handler.setFormatter(formatter)

    # 文件输出处理器：持久化写入jsonl日志文件，utf-8编码支持中文
    file_handler = logging.FileHandler(
        file_path,
        encoding="utf-8",
    )
    # 文件日志同样使用JSON格式化
    file_handler.setFormatter(formatter)

    # 设置根日志器的全局日志过滤级别
    logger.setLevel(level)
    # 挂载控制台输出处理器
    logger.addHandler(console_handler)
    # 挂载文件持久化处理器
    logger.addHandler(file_handler)
    # 关闭日志向上传递，避免父日志器重复输出
    logger.propagate = False
    # 给日志器添加自定义标记，标识已完成初始化配置
    logger._scholarflow_configured = True


def get_logger(name: str) -> logging.Logger:
    """
    获取分模块子日志器，统一命名空间 scholarflow.xxx
    :param name: 模块名（auth / api / chat 等）
    :return: 独立模块日志器，继承全局日志配置
    """
    # 拼接统一命名空间，实现日志按模块分类
    return logging.getLogger(f"scholarflow.{name}")