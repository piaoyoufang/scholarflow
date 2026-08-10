# 文件记录管理，让上传文件能属于课程。
# 启用注解前向兼容，允许在类定义之前使用本类作为类型提示
from __future__ import annotations

# sqlite数据库驱动
import sqlite3
# dataclass数据类，快速构建数据实体对象
from dataclasses import dataclass
# UTC时间处理，统一数据库时间，避免时区问题
from datetime import datetime, timezone
# Path跨平台文件路径处理
from pathlib import Path
# uuid生成全局唯一id，作为文档主键source_id
from uuid import uuid4

# 导入项目根目录配置
from app.config import PROJECT_ROOT

# 知识库文档sqlite数据库路径：项目根目录/data/knowledge/documents.sqlite
DOCUMENT_DB_PATH = PROJECT_ROOT / "data" / "knowledge" / "documents.sqlite"


def utc_now() -> str:
    """获取UTC当前时间，返回iso格式化字符串，存入sqlite"""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DocumentRecord:
    """文档记录数据实体，对应documents表一行记录"""
    source_id: str          # 文档全局唯一ID，RAG检索时的元数据source_id
    course_id: str          # 归属的课程ID，文档归属于某一门课程
    uploader_user_id: str   # 上传者用户id
    original_name: str      # 用户上传的原始文件名，例如"大模型.pdf"
    saved_name: str         # 服务器磁盘保存后的文件名（防止重名覆盖）
    file_path: str          # 文件在磁盘上的完整相对路径
    file_type: str          # 文件类型 pdf / txt / md
    file_size: int          # 文件字节大小
    chunk_count: int        # 文档切分后的chunk块数量，向量化完成后回填
    status: str             # 文档状态 processing处理中 / success成功 / failed失败
    created_at: str         # 上传创建时间 UTC‑iso字符串
    updated_at: str         # 更新时间 UTC‑iso字符串


class KnowledgeLibrary:
    """知识库存储层：管理课程上传文档元数据，documents表的全部数据库操作"""
    def __init__(self, db_path: Path = DOCUMENT_DB_PATH):
        # 数据库文件路径
        self.db_path = db_path
        # 如果data/knowledge文件夹不存在，则递归创建目录，存在不报错
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # 实例化对象自动执行建表
        self.init_db()

    def connect(self) -> sqlite3.Connection:
        """获取数据库连接；row_factory允许使用 row["字段名"] 取值"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """初始化数据表，不存在才创建，不会覆盖已有数据"""
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    source_id TEXT PRIMARY KEY,        -- 文档唯一主键uuid，RAG元数据使用
                    course_id TEXT NOT NULL,           -- 归属课程id
                    uploader_user_id TEXT NOT NULL,    -- 上传人user_id
                    original_name TEXT NOT NULL,       -- 用户原始文件名
                    saved_name TEXT NOT NULL,          -- 服务器存储文件名
                    file_path TEXT NOT NULL,           -- 文件磁盘路径
                    file_type TEXT NOT NULL,           -- 文件后缀类型
                    file_size INTEGER NOT NULL,        -- 文件字节大小
                    chunk_count INTEGER NOT NULL DEFAULT 0, -- 切块数量，默认0，解析完成更新
                    status TEXT NOT NULL DEFAULT 'processing', -- 默认状态：处理中
                    created_at TEXT NOT NULL,          -- 创建时间
                    updated_at TEXT NOT NULL           -- 更新时间
                )
                """
            )

    def register_document(
        self,
        course_id: str,
        uploader_user_id: str,
        original_name: str,
        saved_name: str,
        file_path: str,
        file_type: str,
        file_size: int,
        status: str = "processing",
    ) -> DocumentRecord:
        """
        注册一条新上传的文档记录
        文件刚上传到磁盘，还没有做解析切块，先写入数据库，状态默认为processing处理中
        返回组装好的DocumentRecord对象
        """
        now = utc_now()
        # 生成文档全局唯一source_id，后续RAG检索元数据绑定这个id
        source_id = str(uuid4())
        # 组装dataclass实体对象
        record = DocumentRecord(
            source_id=source_id,
            course_id=course_id,
            uploader_user_id=uploader_user_id,
            original_name=original_name,
            saved_name=saved_name,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
            chunk_count=0,
            status=status,
            created_at=now,
            updated_at=now,
        )
        with self.connect() as conn:
            # 将文档元数据插入documents数据表
            conn.execute(
                """
                INSERT INTO documents(
                    source_id, course_id, uploader_user_id, original_name, saved_name,
                    file_path, file_type, file_size, chunk_count, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.source_id,
                    record.course_id,
                    record.uploader_user_id,
                    record.original_name,
                    record.saved_name,
                    record.file_path,
                    record.file_type,
                    record.file_size,
                    record.chunk_count,
                    record.status,
                    record.created_at,
                    record.updated_at,
                ),
            )
        return record

    def list_course_documents(self, course_id: str) -> list[dict]:
        """查询某一门课程下全部上传文档，按创建时间倒序，新上传的排在前面"""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM documents
                WHERE course_id = ?
                ORDER BY created_at DESC
                """,
                (course_id,),
            ).fetchall()
        # sqlite.Row对象转为普通字典，方便接口返回JSON
        return [dict(row) for row in rows]

    def get_document(self, source_id: str) -> dict | None:
        """根据source_id查询单条文档元数据，找不到返回None"""
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE source_id = ?", (source_id,)).fetchone()
        return dict(row) if row else None

    def update_status(self, source_id: str, status: str, chunk_count: int | None = None) -> None:
        """
        更新文档处理状态；文档解析、向量化完成/失败时调用
        status可选：processing / success / failed
        chunk_count不为None时，同步更新切块数量（解析完成回填）
        """
        # 校验状态只能传指定三个值
        if status not in {"processing", "success", "failed"}:
            raise ValueError("status 只能是 processing/success/failed")
        now = utc_now()
        with self.connect() as conn:
            # chunk_count不传，只更新状态和更新时间
            if chunk_count is None:
                conn.execute(
                    "UPDATE documents SET status = ?, updated_at = ? WHERE source_id = ?",
                    (status, now, source_id),
                )
            else:
                # 传入chunk_count，同时更新状态、切块数、更新时间
                conn.execute(
                    "UPDATE documents SET status = ?, chunk_count = ?, updated_at = ? WHERE source_id = ?",
                    (status, chunk_count, now, source_id),
                )

    def delete_document_record(self, source_id: str) -> dict:
        """
        删除文档数据库记录；
        返回被删除的文档记录，上层拿到返回值后再去删除磁盘文件 + 删除chroma向量库数据
        """
        document = self.get_document(source_id)
        if not document:
            raise LookupError("文档不存在")
        with self.connect() as conn:
            conn.execute("DELETE FROM documents WHERE source_id = ?", (source_id,))
        return document

    def document_summary(self, course_id: str) -> dict:
        """统计课程文档处理状态汇总，给教师知识库看板使用"""
        # 获取sqlite数据库连接，with上下文自动关闭连接、提交事务
        with self.connect() as conn:
            # SQL：按status分组统计该课程下每种状态的文档数量
            rows = conn.execute(
                """
                SELECT status, COUNT(*) AS count
                FROM documents
                WHERE course_id = ?
                GROUP BY status
                """,
                (course_id,),  # SQL参数，防止SQL注入
            ).fetchall()  # fetchall()取出全部分组查询结果，返回list[Row]

        # 初始化统计字典，全部默认置0；数据库没有的状态不会返回row，靠初始化兜底
        data = {
            "document_count": 0,  # 文档总数量
            "success_document_count": 0,  # 处理成功文档数
            "failed_document_count": 0,  # 处理失败文档数
            "processing_document_count": 0,  # 正在处理文档数
        }

        # 遍历分组查询返回的每一行结果
        for row in rows:
            count = row["count"]  # 当前状态对应的文档数量
            data["document_count"] += count  # 累加得到文档总数量

            # 根据status，把数量赋值到对应key
            if row["status"] == "success":
                data["success_document_count"] = count
            elif row["status"] == "failed":
                data["failed_document_count"] = count
            elif row["status"] == "processing":
                data["processing_document_count"] = count
        return data

# 全局单例，业务代码直接导入使用，不需要手动new实例
knowledge_library = KnowledgeLibrary()