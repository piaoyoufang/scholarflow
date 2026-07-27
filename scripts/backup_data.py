# 启用Python前向类型注解，函数返回/参数可使用文件内后置定义的类
from __future__ import annotations

# JSON序列化库，用于生成备份清单文件
import json
# 文件/目录复制工具，用于拷贝向量库、原始数据文件夹
import shutil
# SQLite数据库连接与备份API
import sqlite3
# 获取当前时间戳，用于备份文件夹命名
from datetime import datetime
# 跨平台路径处理工具
from pathlib import Path

# 导入项目根目录常量、全局配置对象
from app.config import PROJECT_ROOT, settings


# 路径标准化工具：相对路径自动拼接项目根目录，输出绝对Path对象
def resolve_path(value: str) -> Path:
    # 字符串转为路径对象
    path = Path(value)
    # 判断非绝对路径（配置里写的相对路径）
    if not path.is_absolute():
        # 拼接项目根目录生成完整绝对路径
        path = PROJECT_ROOT / path
    return path


# SQLite数据库热备份函数，使用sqlite原生backup API安全复制数据库
# source：源数据库文件路径
# destination：备份输出文件路径
def backup_sqlite(source: Path, destination: Path) -> None:
    # 校验源数据库文件是否存在，不存在直接抛出文件缺失异常
    if not source.exists():
        raise FileNotFoundError(f"数据库不存在：{source}")
    # 自动创建备份目标文件夹，多级目录自动生成，已存在不报错
    destination.parent.mkdir(parents=True, exist_ok=True)
    # 打开源数据库连接，5秒超时，自动释放连接
    with sqlite3.connect(str(source), timeout=5) as source_connection:
        # 创建目标备份数据库连接
        with sqlite3.connect(str(destination)) as target_connection:
            # SQLite内置热备份，无需停机、不会锁库损坏数据
            source_connection.backup(target_connection)


# 备份脚本主执行入口
def main() -> None:
    # 生成时间戳字符串，格式：年月日_时分秒，用作备份文件夹名区分批次
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # 拼接本次备份根目录：项目根目录/backups/时间戳
    backup_root = PROJECT_ROOT / "backups" / timestamp
    # 创建本次备份总文件夹，exist_ok=False 防止重复执行生成同名文件夹冲突
    backup_root.mkdir(parents=True, exist_ok=False)

    # 解析认证库原始绝对路径
    auth_source = resolve_path(settings.auth_db_path)
    # 解析会话断点记忆库原始绝对路径
    memory_source = resolve_path(settings.checkpoint_db_path)
    # 解析Chroma向量库目录原始路径
    vector_source = resolve_path(settings.vector_db_dir)

    # 备份认证SQLite库到备份目录auth子文件夹
    backup_sqlite(auth_source, backup_root / "auth" / "auth.sqlite")
    # 备份会话断点SQLite库到memory子文件夹
    backup_sqlite(
        memory_source,
        backup_root / "memory" / "checkpoints.sqlite",
    )

    # 校验向量库目录是否存在，不存在直接中断备份
    if not vector_source.exists():
        raise FileNotFoundError(f"向量库不存在：{vector_source}")
    # 完整复制整个Chroma向量库目录至备份chroma文件夹
    shutil.copytree(vector_source, backup_root / "chroma")

    # 循环拷贝raw原始提问数据、eval评估数据两个目录
    for directory_name in ("raw", "eval"):
        # 拼接源数据目录路径
        source = PROJECT_ROOT / "data" / directory_name
        # 源文件夹存在才复制，不存在跳过不报错中断
        if source.exists():
            shutil.copytree(source, backup_root / directory_name)

    # 处理报表文件目录备份
    reports_source = PROJECT_ROOT / "reports"
    if reports_source.exists():
        shutil.copytree(reports_source, backup_root / "reports")

    # 构建备份清单元数据，记录备份时间、各数据源原始路径
    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "auth_database": str(auth_source),
        "checkpoint_database": str(memory_source),
        "vector_database": str(vector_source),
    }
    # 将清单写入manifest.json，utf8编码、格式化缩进2格方便阅读
    (backup_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 控制台打印备份完成提示，输出备份存储路径
    print("备份完成：", backup_root)


# 脚本直接运行时执行备份逻辑
if __name__ == "__main__":
    main()
