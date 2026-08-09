# RAG 系统的“数据入库流水线”。它负责把原始文件（PDF/TXT）变成 AI 能检索的向量块，并存入 Chroma 数据库。
"""Path: Python 标准库，用于处理文件路径，比字符串更安全、跨平台。
PyPDFLoader / TextLoader: LangChain 的文档加载器。它们负责读取文件内容并将其转换为 Document 对象（包含文本内容和元数据）。
RecursiveCharacterTextSplitter: 递归字符文本分割器。这是目前最通用的切分策略，它会尝试按段落、句子、单词的顺序进行切分，尽量保持语义完整性。
Chroma: 一个轻量级的开源向量数据库，专门用于存储和检索嵌入向量。
settings & embeddings: 从项目的配置和模型模块中导入全局设置和嵌入模型实例。"""
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma

from app.config import settings
from app.models import embeddings


# load_file 函数：文件的读取、清洗与切分
def load_file(path: str, course_id: str | None = None, source_id: str | None = None):
    file = Path(path)
    if file.suffix.lower() == ".pdf":  # 获取文件后缀并转为小写（如 .PDF -> .pdf），确保兼容性。
        docs = PyPDFLoader(str(file)).load()  # 专门解析 PDF 二进制流，提取文本。注意：它对复杂排版（如双栏、表格）的处理能力有限。
    elif file.suffix.lower() in {".md", ".txt"}:
        # utf-8-sig 兼容普通 UTF-8 和带 BOM 的 UTF-8，并会自动移除 BOM。
        docs = TextLoader(str(file), encoding="utf-8-sig").load()
    else:
        raise ValueError("只支持 PDF、Markdown 和 TXT")  # 异常处理: 如果用户上传了不支持的格式（如 Word 或 Excel），直接抛出错误，避免后续程序崩溃。

    # 语义切分
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=120, add_start_index=True
        # chunk_size=800: 每个切片的最大字符数。chunk_overlap=120: 切片之间的重叠字符数。add_start_index=True: 在元数据中记录该切片在原文件中的起始位置，方便溯源。
    )
    chunks = splitter.split_documents(docs)

    """doc.metadata: LangChain 的 Document 对象自带一个字典，用来存额外信息。
    source_id: 使用文件名（不含后缀）作为 ID。这有助于在数据库中区分不同来源的文件。
    chunk_index: 给每个切片编号（0, 1, 2...）。这在后续做“重排序”或“引用页码”时非常有用。
    source_name: 保留原始文件名，用于在前端展示“来源：xxx.pdf”。"""
    # 如果传入了source_id就用它；没有source_id，就取文件名(不带后缀)作为兜底source_id
    real_source_id = source_id or file.stem

    # 遍历切分后的文本块chunks，i是下标，doc是单个Document块对象
    for i, doc in enumerate(chunks):
        # update批量给doc的metadata元字典批量写入多个字段
        doc.metadata.update(
            {
                "source_id": real_source_id,  # 文档唯一标识，向量库内用来溯源属于哪一份文件
                "source_name": file.name,  # 原始文件名，前端展示引用的时候显示原始文件名字
                "chunk_index": i,  # 当前文本块在整篇文档中的序号，用于定位是第几段
            }
        )
        # 如果course_id不为None/不为空，就把课程id写入元数据
        if course_id:
            doc.metadata["course_id"] = course_id

    # 一定要把切好的 chunks 返回给 ingest。
    # 如果这里不 return，Python 默认返回 None，后面的 len(chunks)、db.add_documents(chunks)
    # 都会出错，课程上传任务就会失败。
    return chunks


# 向量化与存储
def ingest(path: str, course_id: str | None = None, source_id: str | None = None) -> int:
    """
    文档摄入入口函数
    :param path: 文件磁盘路径字符串
    :param course_id: 课程id，可为None
    :param source_id: 业务文档唯一id，可为None
    :return: int 返回切块总数量
    """
    # 调用load_file函数：完成文件加载、文本切分、给每个chunk填充metadata元数据，返回Document块列表
    chunks = load_file(path, course_id=course_id, source_id=source_id)

    # 优先使用传入的source_id；如果source_id为None，就取文件不带后缀的文件名作为兜底id
    # Path(path).stem：把字符串路径转为Path对象，取出不带扩展名的文件名
    real_source_id = source_id or Path(path).stem
    """Chroma(...) 初始化:
    collection_name: 集合名称。类似于 SQL 数据库中的“表名”。这里叫 scholarflow，意味着所有学术相关的知识都存在这一张表里。
    embedding_function: 传入之前定义的嵌入模型。Chroma 会在内部自动调用这个模型，把 chunks 里的文本转成向量。
    persist_directory: 本地存储路径。Chroma 默认是内存数据库，加上这个参数后，数据会保存到硬盘上，重启服务不丢失。"""
    db = Chroma(
        collection_name="scholarflow",
        embedding_function=embeddings(),
        persist_directory=settings.vector_db_dir,
    )

    # 根据metadata里面的source_id条件，删除向量库里所有匹配该source_id的文档块
    db.delete(where={"source_id": real_source_id})

    # 如果course_id有值就用course_id，否则兜底字符串"default"
    prefix = course_id or "default"

    # 列表推导式：循环0 ~ len(chunks)-1，拼接生成每一个chunk的唯一id
    ids = [f"{prefix}:{real_source_id}:{index}" for index in range(len(chunks))]
    db.add_documents(chunks, ids=ids)  # 执行真正的写入操作。
    return len(chunks)  # 返回成功入库的切片数量，用于给用户反馈（例如：“成功导入了 45 个知识片段”）。
