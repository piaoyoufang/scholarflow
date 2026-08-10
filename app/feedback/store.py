# 启用延迟注解，支持前向类型提示，Python低版本兼容
from __future__ import annotations

# sqlite数据库驱动
import sqlite3
# 获取带时区的UTC时间，用于记录创建时间
from datetime import datetime, timezone
# 文件路径处理工具
from pathlib import Path
# 生成全局唯一ID
from uuid import uuid4

# 导入项目根路径配置
from app.config import PROJECT_ROOT

# 反馈数据库文件完整路径：项目根目录/data/feedback/feedback.sqlite
FEEDBACK_DB_PATH = PROJECT_ROOT / "data" / "feedback" / "feedback.sqlite"


def utc_now() -> str:
    """获取UTC标准时间，序列化为iso字符串存入数据库"""
    return datetime.now(timezone.utc).isoformat()


class FeedbackStore:
    """问答反馈存储类，管理用户对AI回答的点赞/点踩反馈数据"""
    def __init__(self, db_path: Path = FEEDBACK_DB_PATH):
        # 赋值数据库路径，可传入自定义路径，默认使用全局常量
        self.db_path = db_path
        # 如果data/feedback文件夹不存在，自动创建，parents=True递归创建多级目录，exist_ok=True目录已存在不报错
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # 初始化数据表，实例化对象时自动执行建表
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        """建立sqlite数据库连接，设置row_factory可以通过列名获取数据"""
        conn = sqlite3.connect(self.db_path)
        # row_factory=sqlite3.Row：查询结果可以用 row["字段名"] 获取值，不用数字下标
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """初始化数据表，不存在则创建qa_feedback问答反馈表"""
        # with上下文管理器，自动关闭数据库连接
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS qa_feedback (
                    feedback_id TEXT PRIMARY KEY, -- 反馈记录唯一id，uuid
                    course_id TEXT NOT NULL,     -- 所属课程id，按课程隔离反馈
                    user_id TEXT NOT NULL,       -- 提交反馈的用户id
                    thread_id TEXT NOT NULL,     -- 所属会话线程id
                    question TEXT NOT NULL,      -- 用户原始提问
                    answer TEXT NOT NULL,        -- AI返回的回答
                    rating TEXT NOT NULL,        -- 评价：up点赞 / down点踩
                    reason TEXT NOT NULL DEFAULT '', -- 点踩原因
                    comment TEXT NOT NULL DEFAULT '',-- 用户额外文字备注
                    created_at TEXT NOT NULL     -- 反馈提交UTC时间
                )
                """
            )

    def create_feedback(
        self,
        *, # *代表后面全部是关键字传参，调用时必须写参数名，防止传参顺序错乱
        course_id: str,
        user_id: str,
        thread_id: str,
        question: str,
        answer: str,
        rating: str,
        reason: str = "",
        comment: str = "",
    ) -> str:
        """新增一条问答反馈记录，返回feedback_id"""
        # 校验rating只能是up/down，防止非法值存入数据库
        if rating not in {"up", "down"}:
            raise ValueError("rating 只能是 up 或 down")
        # 生成uuid作为这条反馈的主键id
        feedback_id = str(uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO qa_feedback(
                    feedback_id, course_id, user_id, thread_id, question, answer,
                    rating, reason, comment, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                # sqlite参数占位符?，防止SQL注入
                (
                    feedback_id,
                    course_id,
                    user_id,
                    thread_id,
                    question,
                    answer,
                    rating,
                    reason,
                    comment,
                    utc_now(), # 当前UTC时间
                ),
            )
        # 返回新生成的反馈id给上层接口
        return feedback_id

    def summary(self, course_id: str) -> dict:
        """统计某一门课程的点赞、点踩总数，返回 {"up":数字,"down":数字}"""
        with self.connect() as conn:
            # 根据course_id过滤，按rating分组统计数量
            rows = conn.execute(
                """
                SELECT rating, COUNT(*) AS count
                FROM qa_feedback
                WHERE course_id = ?
                GROUP BY rating
                """,
                (course_id,),
            ).fetchall() # fetchall拿到全部分组结果
        # 初始化默认值，没有数据时up、down都为0
        data = {"up": 0, "down": 0}
        # 遍历查询结果，把统计值填入字典
        for row in rows:
            data[row["rating"]] = row["count"]
        return data

    def recent_down_feedback(self, course_id: str, limit: int = 20) -> list[dict]:
        """获取课程最近的点踩(down)反馈，默认最多返回20条，按时间倒序，最新的在前"""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM qa_feedback
                WHERE course_id = ? AND rating = 'down'
                ORDER BY created_at DESC -- 创建时间倒序，新记录排在前面
                LIMIT ? -- 限制返回条数
                """,
                (course_id, limit),
            ).fetchall()
        # 将sqlite3.Row对象全部转为普通python字典，方便接口序列化返回json
        return [dict(row) for row in rows]

# 全局单例对象，项目其他地方直接 from app.feedback.store import feedback_store 使用
feedback_store = FeedbackStore()