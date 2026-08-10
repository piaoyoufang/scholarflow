"""
后台任务流程:
更新任务 running
调用原来的 ingest 入库
成功后更新 documents 状态
失败后记录 error"""
# Path：路径工具类，用来把字符串路径转为Path对象，传给ingest文档加载器
from pathlib import Path
# 导入文档 ingestion处理函数：做文档解析、文本切块、生成向量、存入Chroma
from app.ingestion.loader import ingest
# 文档元数据存储单例，用来修改文档在sqlite中的状态
from app.knowledge.library import knowledge_library
# 任务存储单例，用来更新异步任务的进度、状态、错误信息
from app.tasks.store import task_store
from app.cache import delete_prefix


def run_ingestion_task(
    task_id: str,
    source_id: str,
    file_path: str,
    course_id: str | None = None,
) -> None:
    """
    执行文档向量化后台任务
    :param task_id: ingestion任务唯一编号
    :param source_id: 文档元数据唯一标识
    :param file_path: 磁盘上上传文件的字符串路径
    """
    try:
        # 更新任务状态为running运行中，进度10，提示文字：开始处理上传文件
        task_store.update_task(task_id, "running", 10, "开始处理上传文件")

        # 更新进度到30，提示：正在解析文档并切块
        task_store.update_task(task_id, "running", 30, "正在解析文档并切块")

        # 第一版复用已有ingest函数，完成文档解析、切块、embedding、向量入库
        # 后续迭代会把course_id、source_id写入Chroma向量库的metadata元数据
        result = ingest(str(Path(file_path)), course_id=course_id, source_id=source_id)

        # 安全取出返回结果中的chunk_count切块数量；
        # 如果ingest返回是字典，就取chunk_count，否则赋值0，防止报错
        chunk_count = result.get("chunk_count", 0) if isinstance(result, dict) else int(result or 0)

        # 更新进度90，提示正在更新sqlite里的文档记录状态
        task_store.update_task(task_id, "running", 90, "正在更新文档状态")
        # 修改knowledge_library文档元数据表：文档状态改为success成功，写入切块数量
        knowledge_library.update_status(source_id, "success", chunk_count=chunk_count)

        # 更新任务为success成功，进度100，提示入库完成，附带任务结果字典
        task_store.update_task(
            task_id,
            "success",
            100,
            "入库完成",
            result={"source_id": source_id, "chunk_count": chunk_count},
        )
    except Exception as exc:
        # 捕获任意异常：任务流程出错，把sqlite中文档状态更新为failed失败
        knowledge_library.update_status(source_id, "failed")
        # 更新任务状态为failed，进度直接置100，提示入库失败，把异常信息存入error字段
        task_store.update_task(
            task_id,
            "failed",
            100,
            "入库失败",
            error=str(exc),
        )
