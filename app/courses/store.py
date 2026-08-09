# 课程表、课程成员表、课程权限校验都放这里。
# 启用 Python 3.10+ 的注解前向兼容，允许在类定义前使用该类作为类型提示
from __future__ import annotations

# SQLite 数据库驱动
import sqlite3
# 数据类，快速定义数据载体实体，自动生成 __init__ __repr__ 等
from dataclasses import dataclass
# 处理UTC标准时间，保证数据库时间统一无时区混乱
from datetime import datetime, timezone
# 路径对象，跨平台处理文件目录
from pathlib import Path
# 生成全局唯一ID，用作课程主键
from uuid import uuid4

# 从项目配置读取项目根目录
from app.config import PROJECT_ROOT

# 拼接课程数据库完整路径：项目根目录/data/courses/courses.sqlite
COURSE_DB_PATH = PROJECT_ROOT / "data" / "courses" / "courses.sqlite"


def utc_now() -> str:
    """获取当前UTC时间，返回ISO格式化字符串，存入数据库"""
    # 获取UTC时区的当前时间，转为iso字符串方便sqlite存储
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CourseRecord:
    """课程实体数据类，代表一条课程记录"""
    course_id: str          # 课程唯一id(uuid)
    course_name: str        # 课程名称
    description: str        # 课程描述
    owner_teacher_id: str   # 创建课程的老师user_id
    created_at: str         # 创建时间 UTC‑iso字符串
    updated_at: str         # 更新时间 UTC‑iso字符串


class CourseStore:
    """课程数据存储层：封装courses、course_members两张表所有数据库操作"""
    def __init__(self, db_path: Path = COURSE_DB_PATH):
        # 数据库文件路径，默认使用全局常量路径
        self.db_path = db_path
        # 如果父目录不存在，递归创建目录，exist_ok=True代表存在就不报错
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # 对象初始化时自动执行建表逻辑
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        """建立sqlite数据库连接，返回连接对象；设置row_factory可以通过key取字段"""
        conn = sqlite3.connect(self.db_path)
        # row_factory = sqlite3.Row：查询结果可以 row["column_name"] 按列名取值
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """初始化数据表，程序启动自动调用，不存在则创建表，已存在不会覆盖"""
        # with上下文管理连接，自动commit/close
        with self.connect() as conn:
            # 课程主表
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS courses (
                    course_id TEXT PRIMARY KEY,        -- 课程uuid主键
                    course_name TEXT NOT NULL,         -- 课程名非空
                    description TEXT NOT NULL DEFAULT '', -- 课程描述，默认空字符串
                    owner_teacher_id TEXT NOT NULL,    -- 创建该课程的老师id
                    created_at TEXT NOT NULL,          -- 创建时间
                    updated_at TEXT NOT NULL           -- 更新时间
                )
                """
            )
            # 课程成员关联表：一门课多个用户，一个用户多门课；联合主键(course_id,user_id)防止重复加入
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS course_members (
                    course_id TEXT NOT NULL,           -- 关联课程id
                    user_id TEXT NOT NULL,             -- 关联用户id
                    role_in_course TEXT NOT NULL,      -- 用户角色 teacher / student
                    joined_at TEXT NOT NULL,           -- 加入课程时间
                    PRIMARY KEY (course_id, user_id)   -- 联合主键，同一个用户不能重复加入同一课程
                )
                """
            )

    def create_course(self, course_name: str, description: str, owner_teacher_id: str) -> CourseRecord:
        """创建新课程；创建者自动加入课程，角色为teacher，返回课程实体对象"""
        now = utc_now()
        # 生成uuid作为课程唯一id
        course_id = str(uuid4())
        with self.connect() as conn:
            # 向courses表插入课程基础信息
            conn.execute(
                """
                INSERT INTO courses(course_id, course_name, description, owner_teacher_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (course_id, course_name, description, owner_teacher_id, now, now),
            )
            # 创建课程同时，把创建老师加入成员表，角色teacher
            conn.execute(
                """
                INSERT INTO course_members(course_id, user_id, role_in_course, joined_at)
                VALUES (?, ?, ?, ?)
                """,
                (course_id, owner_teacher_id, "teacher", now),
            )
        # 返回封装好的数据对象
        return CourseRecord(course_id, course_name, description, owner_teacher_id, now, now)

    def list_user_courses(self, user_id: str) -> list[dict]:
        """查询当前用户加入的全部课程；关联成员表，同时返回该用户在课程中的角色，按更新时间倒序"""
        with self.connect() as conn:
            # JOIN关联两张表；根据user_id筛选成员；updated_at DESC最新修改的课程排在最上面
            rows = conn.execute(
                """
                SELECT c.course_id, c.course_name, c.description, c.owner_teacher_id,
                       c.created_at, c.updated_at, m.role_in_course
                FROM courses c
                JOIN course_members m ON c.course_id = m.course_id
                WHERE m.user_id = ?
                ORDER BY c.updated_at DESC
                """,
                (user_id,),
            ).fetchall() # fetchall取出全部查询结果
        # 将sqlite.Row对象全部转为普通字典，方便上层接口使用
        return [dict(row) for row in rows]

    def get_course(self, course_id: str) -> dict | None:
        """根据course_id查询单条课程信息，找不到返回None"""
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM courses WHERE course_id = ?", (course_id,)).fetchone()
        return dict(row) if row else None

    def add_member(self, course_id: str, user_id: str, role_in_course: str = "student") -> None:
        """向课程添加成员，默认角色student；INSERT OR REPLACE：已经存在就覆盖角色"""
        # 校验角色只能二选一
        if role_in_course not in {"teacher", "student"}:
            raise ValueError("role_in_course 只能是 teacher 或 student")
        # 校验课程是否真实存在
        if not self.get_course(course_id):
            raise LookupError("课程不存在")
        with self.connect() as conn:
            # INSERT OR REPLACE：联合主键冲突时，更新这条记录，实现修改角色、新增成员两用
            conn.execute(
                """
                INSERT OR REPLACE INTO course_members(course_id, user_id, role_in_course, joined_at)
                VALUES (?, ?, ?, ?)
                """,
                (course_id, user_id, role_in_course, utc_now()),
            )

    def list_members(self, course_id: str) -> list[dict]:
        """获取某一门课程的全部成员列表，按加入时间升序"""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT course_id, user_id, role_in_course, joined_at
                FROM course_members
                WHERE course_id = ?
                ORDER BY joined_at ASC
                """,
                (course_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_member_role(self, course_id: str, user_id: str) -> str | None:
        """查询用户在该课程的角色；用户不在课程返回None"""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT role_in_course
                FROM course_members
                WHERE course_id = ? AND user_id = ?
                """,
                (course_id, user_id),
            ).fetchone()
        # 查到返回角色字符串，查不到返回None
        return row["role_in_course"] if row else None

    def require_course_access(self, course_id: str, user_id: str) -> None:
        """权限校验：用户必须可以访问这门课；不满足直接抛异常，上层接口捕获"""
        if not self.get_course(course_id):
            raise LookupError("课程不存在")
        # get_member_role返回None代表用户不在课程成员列表
        if not self.get_member_role(course_id, user_id):
            raise PermissionError("你没有访问这门课程的权限")

    def require_course_teacher(self, course_id: str, user_id: str) -> None:
        """权限校验：用户必须是课程teacher角色；否则抛出权限异常"""
        if not self.get_course(course_id):
            raise LookupError("课程不存在")
        role = self.get_member_role(course_id, user_id)
        if role != "teacher":
            raise PermissionError("只有课程老师可以执行该操作")


# 全局单例实例，项目其他地方直接 import course_store 使用，不用反复 new 对象
course_store = CourseStore()