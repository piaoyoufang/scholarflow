from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import settings
from app.models import embeddings
from app.retrieval.hybrid import hybrid_candidates
from app.retrieval.rerank import rerank_documents
from app.runtime_metrics import runtime_metrics


def search(query: str, k: int = 6, course_id: str | None = None) -> list[tuple[Document, float]]:
    """
    RAG检索入口函数：执行混合召回，支持按课程过滤知识库
    :param query: 用户输入的查询问题
    :param k: 需要返回的候选文档数量，默认返回6条
    :param course_id: 课程ID，传入后只检索该课程下的向量；None则不做课程过滤
    :return: list[tuple[Document, float]]，元组列表，(文档对象,相关性分数)
    """
    # 校验查询文本，空字符串直接抛出异常
    if not query.strip():
        raise ValueError("query 不能为空")
    # 校验返回条数参数合法性
    if k < 1:
        raise ValueError("k 必须大于等于 1")

    # 初始化Chroma向量数据库实例
    db = Chroma(
        collection_name="scholarflow",    # 向量集合名称
        embedding_function=embeddings(),  # 注入全局Embedding模型
        persist_directory=settings.vector_db_dir,  # 向量库本地持久化目录，读取配置文件
    )

    # 扩容策略：最终只返回k条，提前召回更多候选，给重排留出选择空间
    # 候选数量 = k*4，最低保底24条
    candidate_k = max(k * 4, 24)
    # 判断是否传入course_id，如果有值，开启元数据过滤，只检索该课程下的向量块
    if course_id:
        vector_results = db.similarity_search_with_score(
            query,  # 用户检索的问题文本
            k=candidate_k,  # 本次向量检索召回的候选数量（一般大于最终k，给rerank预留候选）
            filter={"course_id": course_id},  # Chroma元数据过滤条件：只取metadata中course_id匹配的chunk
        )
    # course_id为None，不设置过滤条件，整个向量集合全部参与检索
    else:
        vector_results = db.similarity_search_with_score(
            query,
            k=candidate_k,
        )
    # 判断course_id是否存在（不为None、不为空字符串）
    if course_id:
        """
        db.get()：Chroma原生查询接口，读取集合内的数据，不做相似度检索，是全量筛选
        include=["documents", "metadatas"]：指定返回内容：返回文档文本、元数据；不返回向量embedding（节省内存）
        where={"course_id": course_id}：where过滤条件，只取出metadata中course_id等于传入值的全部记录
        """
        stored = db.get(include=["documents", "metadatas"], where={"course_id": course_id})
    else:
        # course_id为空/None，不设置where过滤条件，读取集合中全部文档与元数据
        stored = db.get(include=["documents", "metadatas"])
    # 将Chroma原始数据批量转为LangChain Document对象
    all_documents = [
        Document(
            page_content=content or "",  # 文档正文，空值兜底
            metadata=metadata or {},    # 元数据source_id、chunk_index等，空字典兜底
        )
        for content, metadata in zip(
            stored.get("documents", []),
            stored.get("metadatas", []),
        )
    ]

    # 执行混合检索：向量相似度 + 本地BM25加权融合
    mixed = hybrid_candidates(
        query,
        vector_results,
        all_documents,
        top_k=candidate_k,
        vector_weight=0.65,   # 向量检索权重
        bm25_weight=0.35,     # BM25关键词检索权重
    )

    try:
        # 调用阿里DashScope Rerank模型进行语义精排
        return rerank_documents(query, mixed, top_k=k)
    except Exception:
        # Rerank API异常（超时、限流、网络错误等）触发降级
        runtime_metrics.record_fallback("retrieval.rerank") # 埋点记录降级事件，监控可见
        # 放弃精排，直接截取混合检索前k条结果返回，保证检索功能不中断
        return mixed[:k]
