"""
TaskStore` 只负责任务状态，不负责文档解析。
任务有没有开始
执行到多少进度
当前步骤是什么
成功结果是什么
失败原因是什么
"""

# from __future__ ：Python版本向前兼容，支持函数返回值的类型注解写法
from __future__ import annotations

# json模块：字典对象与json字符串互相转换，数据库存复杂结果用
import json
# sqlite3：SQLite文件数据库驱动
import sqlite3
# datetime时间工具，timezone.utc 使用UTC标准时区，避免时区不一致问题
from datetime import datetime, timezone
# Path：面向对象的路径工具，跨操作系统处理文件/文件夹路径
from pathlib import Path
# uuid4：生成随机全局唯一字符串，用来做task_id
from uuid import uuid4

# 导入项目配置，拿到项目根目录对象
from app.config import PROJECT_ROOT

# 拼接任务数据库完整路径：项目根目录/data/tasks/tasks.sqlite
TASK_DB_PATH = PROJECT_ROOT / "data" / "tasks" / "tasks.sqlite"


def utc_now() -> str:
    """获取当前UTC时间，输出iso格式字符串，统一数据库存储时间格式"""
    # datetime.now(timezone.utc) 获取utc时间；isoformat转为可存入数据库的字符串
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    """文档摄入异步任务存储类，管理文档解析、向量化后台任务"""
    def __init__(self, db_path: Path = TASK_DB_PATH):
        """
        构造函数
        :param db_path: sqlite数据库文件路径，默认全局TASK_DB_PATH；单元测试时可以传入临时路径
        """
        # 保存数据库文件路径到实例变量
        self.db_path = db_path
        # 创建数据库所在文件夹；parents=True递归创建多级目录；exist_ok=True文件夹已存在不会抛异常
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # 调用初始化数据库方法，建表
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        """获取数据库连接对象"""
        # 打开sqlite数据库文件
        conn = sqlite3.connect(self.db_path)
        # row_factory = sqlite3.Row，查询结果可以按字段名取值，方便转字典
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """初始化数据表，表不存在就创建ingestion_tasks任务表"""
        # with上下文管理器，自动关闭数据库连接
        with self.connect() as conn:
            # 执行建表SQL
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_tasks (
                    task_id TEXT PRIMARY KEY,      -- 任务唯一ID，uuid字符串，主键
                    course_id TEXT NOT NULL,       -- 所属课程id
                    source_id TEXT NOT NULL,       -- 关联文档的source_id
                    owner_user_id TEXT NOT NULL,   -- 创建该任务的用户id
                    status TEXT NOT NULL,          -- 任务状态：pending/running/success/failed
                    progress INTEGER NOT NULL DEFAULT 0, -- 任务进度，0~100整数
                    message TEXT NOT NULL DEFAULT '',    -- 任务提示文本，给前端展示
                    result_json TEXT NOT NULL DEFAULT '{}', -- 任务输出结果，json字符串存储
                    error TEXT NOT NULL DEFAULT '',      -- 任务失败时存放错误信息
                    created_at TEXT NOT NULL,            -- 任务创建UTC时间
                    updated_at TEXT NOT NULL             -- 任务最后更新UTC时间
                )
                """
            )

    def create_task(self, course_id: str, source_id: str, owner_user_id: str) -> str:
        """
        创建一条新的文档处理任务
        :param course_id: 课程id
        :param source_id: 文档source_id
        :param owner_user_id: 创建任务用户id
        :return: 返回新生成的task_id
        """
        # 生成uuid字符串作为任务唯一标识
        task_id = str(uuid4())
        # 获取当前UTC时间
        now = utc_now()
        with self.connect() as conn:
            # insert插入任务记录，初始状态pending等待处理，进度0
            conn.execute(
                """
                INSERT INTO ingestion_tasks(
                    task_id, course_id, source_id, owner_user_id, status,
                    progress, message, result_json, error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                # sqlite参数占位符，顺序对应上面字段；初始值：pending、进度0、等待处理、空json、无错误
                (task_id, course_id, source_id, owner_user_id, "pending", 0, "等待处理", "{}", "", now, now),
            )
        # 返回任务id，交给前端/后台worker使用
        return task_id

    def update_task(
        self,
        task_id: str,
        status: str,
        progress: int,
        message: str,
        result: dict | None = None,
        error: str = "",
    ) -> None:
        """
        更新任务状态、进度、结果、错误信息
        :param task_id: 需要更新的任务id
        :param status: 任务状态
        :param progress: 0‑100进度
        :param message: 展示给用户的提示文字
        :param result: 任务产出的字典数据，可以为None
        :param error: 错误字符串，失败时填写
        """
        # 将字典result转为json字符串；如果result是None，存空对象{}；ensure_ascii=False支持中文
        result_json = json.dumps(result or {}, ensure_ascii=False)
        with self.connect() as conn:
            # 根据task_id更新指定任务记录，同时刷新updated_at更新时间
            conn.execute(
                """
                UPDATE ingestion_tasks
                SET status = ?, progress = ?, message = ?, result_json = ?, error = ?, updated_at = ?
                WHERE task_id = ?
                """,
                # 参数依次对应set后面各个字段，最后是where条件task_id
                (status, progress, message, result_json, error, utc_now(), task_id),
            )

    def get_task(self, task_id: str) -> dict | None:
        """
        根据task_id查询单个任务
        :param task_id:任务编号
        :return: 任务字典；任务不存在返回None；自动把result_json解析为result字典
        """
        with self.connect() as conn:
            # 根据task_id查询单条记录，fetchone拿第一条
            row = conn.execute("SELECT * FROM ingestion_tasks WHERE task_id = ?", (task_id,)).fetchone()
        # 查询不到直接返回None
        if not row:
            return None
        # sqlite.Row对象转为普通python字典
        data = dict(row)
        # 弹出数据库里的result_json字符串，解析成字典，重命名为result放入返回字典对外暴露
        data["result"] = json.loads(data.pop("result_json") or "{}")
        return data

    def list_course_tasks(self, course_id: str) -> list[dict]:
        """
        获取某一门课程下全部任务
        :param course_id:课程id
        :return: 任务字典列表，按创建时间倒序，最新任务排在最前面
        """
        with self.connect() as conn:
            # 查询该课程所有任务，ORDER BY created_at DESC 创建时间降序
            rows = conn.execute(
                """
                SELECT * FROM ingestion_tasks
                WHERE course_id = ?
                ORDER BY created_at DESC
                """,
                (course_id,),
            ).fetchall()
        # 准备返回结果列表
        result = []
        # 遍历每一条数据库查询行
        for row in rows:
            # row转为字典
            item = dict(row)
            # json字符串解析成result字典，对外接口屏蔽result_json字段
            item["result"] = json.loads(item.pop("result_json") or "{}")
            result.append(item)
        return result


# 全局单例实例，业务代码直接 from app.tasks.store import task_store 使用，不用反复new对象
task_store = TaskStore()