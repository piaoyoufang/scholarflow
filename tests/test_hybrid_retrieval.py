from langchain_core.documents import Document

# 导入待测试的BM25打分函数、混合检索融合函数
from app.retrieval.hybrid import bm25_scores, hybrid_candidates


def test_bm25_prefers_exact_identifier():
    """
    单元测试：验证BM25能够优先命中精确专有名词
    场景：查询 chunk_overlap，包含该标识符的文档得分更高
    """
    # 普通文本文档，不含关键词 chunk_overlap
    generic = Document(page_content="切片可以保留上下文")
    # 文档包含精确标识符 chunk_overlap
    exact = Document(page_content="chunk_overlap 控制切片重叠")
    # 批量计算两篇文档BM25分数
    scores = bm25_scores("chunk_overlap", [generic, exact])
    # 断言：包含关键词的文档分数 > 普通文档
    assert scores[1] > scores[0]


def test_hybrid_contains_dense_and_keyword_candidates():
    """
    单元测试：混合检索同时保留【关键词匹配文档】和【向量语义匹配文档】
    校验向量检索结果、BM25关键词结果不会互相覆盖丢失
    """
    # 关键词文档：字面包含chunk_overlap，BM25会高分
    keyword_doc = Document(
        page_content="chunk_overlap 参数说明",
        metadata={"source_id": "keyword", "chunk_index": 0},
    )
    # 语义文档：不含关键词，但向量相似度高，向量检索召回
    semantic_doc = Document(
        page_content="相邻片段保持上下文连续",
        metadata={"source_id": "semantic", "chunk_index": 0},
    )
    # 执行混合检索
    # vector_results：向量只召回语义文档
    # all_documents：参与BM25打分的全部文档（两篇）
    results = hybrid_candidates(
        "chunk_overlap",
        [(semantic_doc, 0.1)],
        [keyword_doc, semantic_doc],
        top_k=2,
    )
    # 提取最终结果里所有文档的source_id
    source_ids = {
        document.metadata["source_id"]
        for document, _score in results
    }
    # 断言：两种类型文档都存在，证明向量召回、BM25召回的文档都被保留
    assert source_ids == {"keyword", "semantic"}
