# 开启Python前向注解，允许函数参数/返回值使用本文件内未提前定义的类型
from __future__ import annotations

# 导入sqlite3数据库驱动，用于校验SQLite文件可用性
import sqlite3
# 导入路径工具类，跨平台统一处理文件/目录路径
from pathlib import Path

# 导入项目根目录常量、全局配置实例
from app.config import PROJECT_ROOT, settings


# 将传入路径解析为完整绝对路径，相对路径会自动拼接项目根目录
# value：原始文件/目录路径字符串
# 返回：标准化绝对Path对象
def resolve_project_path(value: str) -> Path:
    # 转换为Path路径对象
    path = Path(value)
    # 判断是否为非绝对路径（相对路径）
    if not path.is_absolute():
        # 拼接项目根目录，转为项目内绝对路径
        path = PROJECT_ROOT / path
    # 返回处理完成的绝对路径
    return path


# 校验SQLite数据库文件是否存在、能否正常连接查询
# path：数据库文件绝对Path对象
# 返回元组：(是否可用布尔值, 状态描述字符串)
def check_sqlite(path: Path) -> tuple[bool, str]:
    # 文件不存在直接返回失败，标记状态为missing
    if not path.exists():
        return False, "missing"
    try:
        # 建立SQLite连接，超时1秒，自动关闭连接资源
        with sqlite3.connect(str(path), timeout=1) as connection:
            # 执行最简查询验证数据库无损坏、可读写
            connection.execute("SELECT 1").fetchone()
    # 捕获连接、查询全部异常（文件损坏、占用、权限不足等）
    except Exception as exc:
        # 返回失败状态，值为异常类名（TimeoutError/OperationalError等）
        return False, type(exc).__name__
    # 无异常：数据库正常可用，状态ok
    return True, "ok"


# 项目就绪性健康检查总入口，校验依赖库全部存储资源状态
# 返回：健康检查结果字典，供健康接口返回
def readiness_report() -> dict[str, object]:
    # 解析认证数据库完整绝对路径
    auth_path = resolve_project_path(settings.auth_db_path)
    # 解析会话断点数据库完整绝对路径
    checkpoint_path = resolve_project_path(settings.checkpoint_db_path)
    # 解析向量库存储目录完整绝对路径
    vector_path = resolve_project_path(settings.vector_db_dir)

    # 校验认证库状态，解包是否可用、状态文本
    auth_ok, auth_status = check_sqlite(auth_path)
    # 校验断点持久化库状态
    checkpoint_ok, checkpoint_status = check_sqlite(checkpoint_path)
    # 向量目录三重校验：目录存在、是文件夹、目录内存在chroma核心库文件
    vector_ok = (
        vector_path.exists()
        and vector_path.is_dir()
        and (vector_path / "chroma.sqlite3").exists()
    )

    # 组装各存储组件校验状态集合
    checks = {
        "auth_database": auth_status,        # 认证库状态：missing/ok/异常类名
        "checkpoint_database": checkpoint_status, # 断点库状态
        "vector_directory": "ok" if vector_ok else "missing", # 向量目录状态
    }
    # 整体就绪条件：三个存储组件全部校验通过
    return {
        "ready": auth_ok and checkpoint_ok and vector_ok,
        "checks": checks,
    }
