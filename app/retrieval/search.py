from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import settings
from app.models import embeddings
from app.retrieval.hybrid import hybrid_candidates
from app.retrieval.rerank import rerank_documents
from app.runtime_metrics import runtime_metrics


def search(query: str, k: int = 6) -> list[tuple[Document, float]]:
    """
    检索入口主函数：向量+BM25混合召回 + 阿里Rerank精排
    容灾策略：Rerank接口调用失败，自动降级直接返回混合检索结果
    :param query: 用户查询文本
    :param k: 最终向外输出的文档数量
    :return: [(Document, 相关性分数)] 降序排列
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
    # Chroma稠密向量检索，返回 [(Document, distance)]
    vector_results = db.similarity_search_with_score(
        query,
        k=candidate_k,
    )

    # 取出向量库内全部文档文本+元数据，用于本地BM25关键词打分
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
