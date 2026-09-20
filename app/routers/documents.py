"""文档管理域路由：课程文档列表/删除/重新入库/异步上传、全局上传——从 api.py 原样搬入"""
import re
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from starlette.concurrency import run_in_threadpool

from app.cache import delete_prefix
from app.config import PROJECT_ROOT, settings
from app.courses.store import course_store
from app.deps import current_session
from app.ingestion.loader import ingest
from app.knowledge.library import knowledge_library
from app.observability import get_logger
from app.tasks.ingestion import run_ingestion_task
from app.tasks.queue import get_queue
from app.tasks.store import task_store

logger = get_logger("api")

router = APIRouter()

UPLOAD_DIR = PROJECT_ROOT / "data" / "raw" / "uploads"
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".txt", ".md"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def safe_upload_name(filename: str) -> str:
    """Remove path traversal and characters unsafe on Windows/Linux."""
    original = Path(filename).name
    suffix = Path(original).suffix.lower()
    stem = re.sub(
        r"[^A-Za-z0-9_\-\u4e00-\u9fff]",
        "_",
        Path(original).stem,
    ).strip("._")
    stem = stem[:80] or "uploaded_document"
    if stem.upper() in WINDOWS_RESERVED_NAMES:
        stem = f"uploaded_{stem}"
    return f"{stem}{suffix}"


# 获取课程下全部文档列表接口 GET /courses/{course_id}/documents
@router.get("/courses/{course_id}/documents", tags=["文档管理"], summary="获取课程文档列表")
def list_course_documents(course_id: str, session: tuple[str, str] = Depends(current_session)):
    # 从登录会话元组解包，拿到当前登录用户ID，下划线表示token本接口不使用
    user_id, _ = session
    try:
        # 权限校验：课程必须存在，当前用户必须是该课程成员（老师/学生均可查看文档列表）
        course_store.require_course_access(course_id, user_id)
    except LookupError as exc:
        # 捕获课程不存在异常，返回HTTP 404，from exc保留原始异常堆栈信息，方便日志排查
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        # 捕获没有课程访问权限异常，返回HTTP 403禁止访问
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    # 校验通过，调用知识库存储层，查询该课程所有文档，返回给前端
    return {"documents": knowledge_library.list_course_documents(course_id)}

# 定义DELETE接口：删除课程下指定文档，路径参数：课程id、文档source_id
@router.delete("/courses/{course_id}/documents/{source_id}", tags=["文档管理"], summary="删除课程文档")
def delete_course_document(
    course_id: str,
    source_id: str,
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
        document = knowledge_library.get_document(source_id)
        if not document or document["course_id"] != course_id:
            raise LookupError("文档不存在")
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    deleted = knowledge_library.delete_document_record(source_id)
    if settings.vector_backend.lower() == "qdrant":
        from app.vectorstores.qdrant_store import delete_by_source_id
        delete_by_source_id(source_id)
    else:
        from langchain_chroma import Chroma
        from app.models import embeddings
        db = Chroma(
            collection_name="scholarflow",
            embedding_function=embeddings(),
            persist_directory=settings.vector_db_dir,
        )
        db.delete(where={"source_id": source_id})

    file_path = Path(deleted["file_path"])
    file_path.unlink(missing_ok=True)
    delete_prefix(f"course:{course_id}:")
    return {"deleted": True, "source_id": source_id, "filename": deleted["original_name"]}
@router.post("/courses/{course_id}/documents/{source_id}/reingest", tags=["文档管理"], summary="重新入库课程文档")
def reingest_course_document(
    # 路径参数：课程ID
    course_id: str,
    # 路径参数：目标文档的source_id
    source_id: str,
    # FastAPI内置后台任务对象，把耗时的文档解析任务放到后台异步执行，不阻塞HTTP响应
    background_tasks: BackgroundTasks,
    # 依赖注入：校验登录会话，返回(user_id, token)，未登录直接返回401
    session: tuple[str, str] = Depends(current_session),
):
    # 解包会话，获取当前登录用户ID，丢弃token
    user_id, _ = session
    try:
        # 权限校验：只有该课程的教师，才有权限重新向量化文档，学生无权限
        course_store.require_course_teacher(course_id, user_id)
        # 根据source_id从SQLite查询文档元数据记录
        document = knowledge_library.get_document(source_id)
        # 校验：文档不存在，或者文档所属课程和URL传入course_id不一致，防止跨课程越权操作
        if not document or document["course_id"] != course_id:
            raise LookupError("文档不存在")
    # 捕获查找异常，返回404
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # 捕获权限异常，不是教师返回403禁止访问
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    # 取出数据库存储的原始文件路径，转为Path对象
    file_path = Path(document["file_path"])
    # 判断磁盘上原始文件是否还存在，文件丢失则无法重新解析，直接报错返回
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="原始文件不存在，无法重新入库")

    # 更新SQLite文档状态为processing处理中，重置chunk_count为0
    knowledge_library.update_status(source_id, "processing", chunk_count=0)
    delete_prefix(f"course:{course_id}:")

    # 在task_store任务表创建一条异步任务记录，拿到task_id
    task_id = task_store.create_task(
        course_id=course_id,
        source_id=source_id,
        owner_user_id=user_id,
    )

    # 添加后台异步任务，HTTP接口立刻返回，文档解析向量化在后台跑
    background_tasks.add_task(
        run_ingestion_task,       # 需要后台执行的函数：文档摄入任务
        task_id,                  # 参数1：任务id，用于更新任务进度
        source_id,                # 参数2：文档source_id
        str(file_path),           # 参数3：原始文件路径（转字符串）
        course_id,                # 参数4：课程id，写入向量metadata做隔离
    )

    # 接口直接返回，不等待文档处理完成；前端拿着task_id轮询/tasks/{task_id}查询进度
    return {
        "task_id": task_id,
        "source_id": source_id,
        "status": "pending",
        "message": "已创建重新入库任务",
    }


@router.post("/courses/{course_id}/documents/upload-async", tags=["文档管理"], summary="异步上传课程文档")
async def upload_course_document_async(
    course_id: str,
    file: UploadFile = File(...),
    session: tuple[str, str] = Depends(current_session),
):
    """
    课程级异步上传接口。

    作用：
    1. 校验当前用户必须是课程老师。
    2. 把上传文件保存到 data/raw/uploads/courses/{course_id}/。
    3. 在 documents.sqlite 里登记一条 processing 文档记录。
    4. 在 tasks.sqlite 里创建一条 pending 后台任务。
    5. 把真正耗时的解析、切块、embedding、Chroma 入库放到后台执行。
    """
    user_id, _ = session
    try:
        course_store.require_course_teacher(course_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    filename = safe_upload_name(file.filename or "")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="只支持 PDF、TXT 和 Markdown 文件",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件不能超过 10 MB")
    if not content:
        raise HTTPException(status_code=400, detail="不能上传空文件")

    upload_dir = UPLOAD_DIR / "courses" / course_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_name = f"{uuid4().hex}_{filename}"
    target = upload_dir / saved_name
    target.write_bytes(content)

    document = knowledge_library.register_document(
        course_id=course_id,
        uploader_user_id=user_id,
        original_name=filename,
        saved_name=saved_name,
        file_path=str(target),
        file_type=suffix.lstrip("."),
        file_size=len(content),
        status="processing",
    )
    task_id = task_store.create_task(
        course_id=course_id,
        source_id=document.source_id,
        owner_user_id=user_id,
    )

    delete_prefix(f"course:{course_id}:")
    delete_prefix(f"course:{course_id}:")
    # 不再用进程内 BackgroundTasks，改为投递到 Redis 队列，由独立 worker 进程执行
    # 接口契约不变：前端照常轮询 /tasks/{task_id}，前端代码零改动
    queue = await get_queue()
    await queue.enqueue_job(
        "ingestion_job",          # 对应 app/tasks/worker.py 里的函数名
        task_id,
        document.source_id,
        str(target),
        course_id,
    )

    return {
        "task_id": task_id,
        "source_id": document.source_id,
        "filename": document.original_name,
        "status": "pending",
        "message": "文件已上传，后台正在解析、切块和向量入库",
    }


@router.post("/documents/upload", tags=["文档管理"], summary="上传文档")
async def upload_document(
    file: UploadFile = File(...),
    session: tuple[str, str] = Depends(current_session),
):
    user_id, _token = session
    filename = safe_upload_name(file.filename or "")
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="只支持 PDF、TXT 和 Markdown 文件",
        )

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件不能超过 10 MB")
    if not content:
        raise HTTPException(status_code=400, detail="不能上传空文件")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOAD_DIR / filename
    previous_content = target.read_bytes() if target.exists() else None
    target.write_bytes(content)
    try:
        chunk_count = await run_in_threadpool(ingest, str(target))
    except Exception as exc:
        if previous_content is None:
            target.unlink(missing_ok=True)
        else:
            target.write_bytes(previous_content)
        logger.exception(
            "document.upload.failed",
            extra={
                "event": "document.upload.failed",
                "details": {"user_id": user_id, "filename": filename},
            },
        )
        raise HTTPException(
            status_code=422,
            detail="文档解析或入库失败，请检查文件内容后重试",
        ) from exc

    logger.info(
        "document.upload.completed",
        extra={
            "event": "document.upload.completed",
            "details": {
                "user_id": user_id,
                "filename": filename,
                "chunk_count": chunk_count,
            },
        },
    )
    return {"filename": filename, "chunk_count": chunk_count}
