# 开启Python向前注解支持，支持类内部直接写本类作为类型提示
from __future__ import annotations

# SQLite数据库驱动
import sqlite3
# 导入日期时间、时区工具，生成UTC标准时间戳
from datetime import datetime, timezone
# 路径工具，处理数据库文件路径，自动创建目录
from pathlib import Path
# uuid4生成全局唯一事件ID
from uuid import uuid4

# 导入项目根路径配置
from app.config import PROJECT_ROOT

# QA评估事件数据库文件完整路径：项目根目录/data/analytics/qa_events.sqlite
QA_EVENT_DB_PATH = PROJECT_ROOT / "data" / "analytics" / "qa_events.sqlite"


def utc_now() -> str:
    """获取UTC时区的当前时间，输出ISO格式字符串，存入数据库"""
    return datetime.now(timezone.utc).isoformat()


class QAEventStore:
    """
    QA问答事件存储类：记录RAG问答的评估日志，用于后期数据分析、问题排查
    记录每一次问答：用户、课程、会话、问题、回答、引用数量、评估结果、质量分数、错误信息
    """
    def __init__(self, db_path: Path = QA_EVENT_DB_PATH):
        # 赋值数据库文件路径
        self.db_path = db_path
        # 如果上级目录不存在，自动创建目录；parents递归创建多级目录，exist_ok目录存在不报错
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # 初始化数据库表，没有表就创建
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        """建立SQLite数据库连接，设置row_factory，可以通过列名读取返回行数据"""
        conn = sqlite3.connect(self.db_path)
        # row_factory = sqlite3.Row：查询结果可以 row["字段名"] 取值
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """初始化数据表，不存在则创建qa_events事件表"""
        # with上下文管理器，自动关闭数据库连接
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_events (
                    event_id TEXT PRIMARY KEY,       -- 单条事件唯一ID，uuid
                    course_id TEXT NOT NULL,         -- 所属课程ID
                    user_id TEXT NOT NULL,           -- 操作用户ID
                    thread_id TEXT NOT NULL,         -- 对话会话ID
                    question TEXT NOT NULL,          -- 用户提问
                    answer TEXT NOT NULL,            -- RAG生成的回答
                    citation_count INTEGER NOT NULL, -- 回答携带的引用来源数量
                    pass_result INTEGER NOT NULL DEFAULT 1, -- 评估是否通过 1=True通过 0=False不通过
                    quality_score INTEGER NOT NULL DEFAULT 100, -- 问答质量分数
                    error TEXT NOT NULL DEFAULT '',  -- 发生错误时记录错误信息，正常为空字符串
                    process_status TEXT NOT NULL DEFAULT 'pending',  --任务处理状态，默认pending待处理
                    process_note TEXT NOT NULL DEFAULT '',           --任务备注、错误信息、进度描述
                    processed_at TEXT NOT NULL DEFAULT '',           --任务真正处理完成的UTC时间，未完成为空字符串
                    created_at TEXT NOT NULL        -- 事件UTC创建时间
                )
                """
            )
            # 查询 qa_events 表现有的全部字段名称，存入集合，集合用于快速判断字段是否存在
            existing_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(qa_events)").fetchall()
            }

            # 如果表里面没有 process_status 字段，执行SQL给表新增该列，默认值为 pending
            if "process_status" not in existing_columns:
                conn.execute("ALTER TABLE qa_events ADD COLUMN process_status TEXT NOT NULL DEFAULT 'pending'")

            # 如果没有 process_note 字段，新增，默认空字符串
            if "process_note" not in existing_columns:
                conn.execute("ALTER TABLE qa_events ADD COLUMN process_note TEXT NOT NULL DEFAULT ''")

            # 如果没有 processed_at 字段，新增，默认空字符串
            if "processed_at" not in existing_columns:
                conn.execute("ALTER TABLE qa_events ADD COLUMN processed_at TEXT NOT NULL DEFAULT ''")

    def update_process_status(
            self,
            event_id: str,  # qa_events表的事件唯一ID
            status: str,  # 需要更新成的处理状态
            note: str = "",  # 处理备注，错误/处理说明，选填，默认空字符串
    ) -> None:
        # 校验status只能是约定的4种状态，防止非法状态存入数据库
        if status not in {"pending", "processing", "resolved", "ignored"}:
            raise ValueError("status 只能是 pending/processing/resolved/ignored")

        # 获取数据库连接，with上下文自动关闭连接、提交事务
        with self.connect() as conn:
            # 执行update更新SQL语句
            cursor = conn.execute(
                """
                UPDATE qa_events
                SET process_status = ?,
                    process_note   = ?,
                    processed_at   = ?
                WHERE event_id = ?
                """,
                # sqlite占位符? 参数，顺序对应上面SQL的?
                (status, note, utc_now(), event_id),
            )
            # cursor.rowcount：拿到本次SQL影响的数据行数
            # rowcount ==0：WHERE条件没有匹配到任何event_id，记录不存在
            if cursor.rowcount == 0:
                raise LookupError("问答事件不存在")

    def dashboard_summary(self, course_id: str) -> dict:
        """获取课程问答仪表盘汇总统计数据，给教师后台看板使用"""
        # 打开sqlite数据库连接，with上下文自动提交、自动关闭连接
        with self.connect() as conn:
            # 查询该课程全部问答事件总数量
            total = conn.execute(
                "SELECT COUNT(*) AS count FROM qa_events WHERE course_id = ?",
                (course_id,),  # sqlite占位符参数，防止sql注入
            ).fetchone()["count"]  # fetchone拿到单行Row对象，取出count字段值

            # 查询：该课程引用数量=0 的问答（回答没有引用文档来源）
            no_citation = conn.execute(
                "SELECT COUNT(*) AS count FROM qa_events WHERE course_id = ? AND citation_count = 0",
                (course_id,),
            ).fetchone()["count"]

            # 查询低质量回答数量：评判不通过 / 质量分数低于60 / 存在报错信息
            low_quality = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM qa_events
                WHERE course_id = ? AND (pass_result = 0 OR quality_score < 60 OR error != '')
                """,
                (course_id,),
            ).fetchone()["count"]

        # 计算引用率：(总问答‑无引用问答)/总问答；total=0避免除以0报错，直接赋值0
        citation_rate = 0 if total == 0 else round((total - no_citation) / total, 4)

        # 返回统计字典，提供给接口返回前端仪表盘
        return {
            "qa_count": total,  # 当前课程问答总条数
            "no_citation_count": no_citation,  # 无引用回答数量
            "low_quality_count": low_quality,  # 低质量回答数量
            "citation_rate": citation_rate,  # 文档引用率，0~1，保留4位小数
        }

    def record_event(
        self,
        *,  # * 代表后面全部为关键字参数，调用必须写参数名，防止传参顺序出错
        course_id: str,
        user_id: str,
        thread_id: str,
        question: str,
        answer: str,
        citation_count: int,
        pass_result: bool = True,
        quality_score: int = 100,
        error: str = "",
    ) -> str:
        """
        写入一条问答事件记录
        :return: event_id 返回本次记录的唯一事件id
        """
        # 生成uuid作为这条日志的唯一主键
        event_id = str(uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO qa_events(
                    event_id, course_id, user_id, thread_id, question, answer,
                    citation_count, pass_result, quality_score, error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    course_id,
                    user_id,
                    thread_id,
                    question,
                    answer,
                    citation_count,
                    1 if pass_result else 0,  # sqlite没有bool类型，布尔转整数1/0存储
                    quality_score,
                    error,
                    utc_now(),  # 存入UTC时间
                ),
            )
        return event_id

    def top_questions(self, course_id: str, limit: int = 20) -> list[dict]:
        """统计该课程被提问最多的topN问题，用于分析高频提问"""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT question, COUNT(*) AS count
                FROM qa_events
                WHERE course_id = ?
                GROUP BY question        -- 根据问题分组，相同问题合并
                ORDER BY count DESC      -- 按提问次数从大到小排序
                LIMIT ?
                """,
                (course_id, limit),
            ).fetchall()
        # sqlite.Row对象转为python字典返回，方便序列化输出接口
        return [dict(row) for row in rows]

    def no_citation_questions(self, course_id: str, limit: int = 20) -> list[dict]:
        """查询该课程下，回答引用数量=0的问答记录，排查RAG引用失效问题"""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, question, answer, citation_count, created_at
                FROM qa_events
                WHERE course_id = ? AND citation_count = 0
                ORDER BY created_at DESC  -- 最新的记录放前面
                LIMIT ?
                """,
                (course_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def low_quality_questions(self, course_id: str, limit: int = 20) -> list[dict]:
        """
        查询低质量问答记录：
        评估不通过(pass_result=0) OR 质量分数小于60 OR 存在错误信息
        用于定位RAG幻觉、报错、质量差的样本
        """
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, question, answer, quality_score, pass_result, error, created_at
                FROM qa_events
                WHERE course_id = ? AND (pass_result = 0 OR quality_score < 60 OR error != '')
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (course_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]


# 全局单例对象，项目其他模块直接导入使用 qa_event_store.record_event(...)
qa_event_store = QAEventStore()
