"""Chroma dense retrieval + local BM25 hybrid retrieval."""
# 允许在类型注解中使用还未定义的类，解决前向引用问题
from __future__ import annotations

import math
import re
# Counter用于快速统计词频
from collections import Counter

# LangChain文档对象，承载文本块+元数据(source_id、chunk_index等)
from langchain_core.documents import Document


# 分词正则规则
# 英文：变量名/单词；中文：逐个汉字切分，无需额外中文分词库
TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """文本分词，统一小写，返回token列表"""
    # 正则匹配所有token，并全部转为小写，消除大小写影响
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def bm25_scores(query: str, documents: list[Document]) -> list[float]:
    """
    批量计算BM25相关性分数
    :param query: 用户检索问句
    :param documents: 待打分文档列表
    :return: 和documents顺序一一对应的BM25分数数组
    """
    # 对查询语句分词
    query_tokens = tokenize(query)
    # 空查询/无文档，直接返回全部0分
    if not query_tokens or not documents:
        return [0.0] * len(documents)

    # 对每一篇文档执行分词
    tokenized = [tokenize(document.page_content) for document in documents]
    # 记录每个文档token长度
    lengths = [len(tokens) for tokens in tokenized]
    # 所有文档平均长度，BM25公式需要
    average_length = sum(lengths) / max(1, len(lengths))

    # 统计【文档频率df】：包含某个词的文档数量
    document_frequency: Counter[str] = Counter()
    for tokens in tokenized:
        # set去重，一个文档内多次出现只计数1次
        document_frequency.update(set(tokens))

    # BM25经典超参
    k1 = 1.5   # 词频饱和系数
    b = 0.75   # 文档长度归一化系数
    document_count = len(documents)
    scores: list[float] = []

    # 遍历每个文档计算总分
    for tokens, length in zip(tokenized, lengths):
        counts = Counter(tokens)
        score = 0.0
        # 遍历查询中的每个关键词累加分数
        for term in query_tokens:
            frequency = counts.get(term, 0)
            # 文档不含该词，无贡献，跳过
            if frequency == 0:
                continue
            # 获取该词的文档频率
            df = document_frequency.get(term, 0)
            # BM25 IDF计算公式
            idf = math.log(
                1 + (document_count - df + 0.5) / (df + 0.5)
            )
            # BM25分母：文档长度平滑项
            denominator = frequency + k1 * (
                1 - b + b * length / max(1.0, average_length)
            )
            # 单项得分累加
            score += idf * frequency * (k1 + 1) / denominator
        scores.append(score)
    return scores


def normalize(values: list[float]) -> list[float]:
    """
    Min-Max 归一化，映射到区间 [0,1]
    作用：向量相似度、BM25原始分值值域不一样，归一化之后才能加权融合
    """
    if not values:
        return []
    minimum = min(values)
    maximum = max(values)
    # 所有数值相同，边界处理
    if minimum == maximum:
        return [1.0 if maximum > 0 else 0.0 for _ in values]
    # min-max归一公式
    return [(value - minimum) / (maximum - minimum) for value in values]


def document_key(document: Document, fallback_index: int) -> str:
    """
    生成文档唯一标识key
    使用元数据source_id + chunk_index，用来合并向量检索、BM25检索中重复的文本块
    fallback_index：元数据缺失时使用数组下标兜底
    """
    source_id = document.metadata.get("source_id", "unknown")
    chunk_index = document.metadata.get("chunk_index", fallback_index)
    return f"{source_id}:{chunk_index}"


def hybrid_candidates(
    query: str,
    vector_results: list[tuple[Document, float]],
    all_documents: list[Document],
    *,
    top_k: int,
    vector_weight: float = 0.65,
    bm25_weight: float = 0.35,
) -> list[tuple[Document, float]]:
    """
    混合检索：稠密向量检索(Chroma) + 本地BM25关键词检索分数加权融合
    返回融合后分数从高到低排序的top_k文档
    :param query: 用户查询文本
    :param vector_results: Chroma向量检索结果 [(Document, distance)]
    :param all_documents: 参与打分的全部候选文档
    :param top_k: 最终返回条数
    :param vector_weight: 向量检索权重
    :param bm25_weight: BM25关键词检索权重
    :return: [(Document, fused_score)] 按分数降序
    """
    # 参数合法性校验
    if top_k < 1:
        raise ValueError("top_k 必须大于等于 1")
    if vector_weight < 0 or bm25_weight < 0:
        raise ValueError("检索权重不能是负数")
    if vector_weight + bm25_weight == 0:
        raise ValueError("两种检索权重不能同时为 0")

    # 构建key -> Document映射，用于去重
    documents_by_key: dict[str, Document] = {}
    for index, document in enumerate(all_documents):
        documents_by_key[document_key(document, index)] = document

    # 存储每个文档key对应的向量相似度
    vector_similarity_by_key: dict[str, float] = {}
    for index, (document, distance) in enumerate(vector_results):
        key = document_key(document, index)
        documents_by_key.setdefault(key, document)
        # Chroma返回的是距离值：距离越小越相似
        # 转换为相似度： 1/(1+distance)，值域(0,1]，越大越相关
        vector_similarity_by_key[key] = 1.0 / (
            1.0 + max(0.0, float(distance))
        )

    # 取出全部不重复文档
    documents = list(documents_by_key.values())
    # 批量计算BM25原始分数
    bm25 = bm25_scores(query, documents)
    # 生成每个文档对应的唯一key
    keys = [document_key(document, index) for index, document in enumerate(documents)]
    # 取出每个文档对应的向量相似度；没有向量结果则填充0
    dense = [vector_similarity_by_key.get(key, 0.0) for key in keys]

    # 分别归一化两套分数
    dense_normalized = normalize(dense)
    bm25_normalized = normalize(bm25)
    total_weight = vector_weight + bm25_weight

    results: list[tuple[Document, float]] = []
    # 加权融合得分
    for index, document in enumerate(documents):
        fused_score = (
            vector_weight * dense_normalized[index]
            + bm25_weight * bm25_normalized[index]
        ) / total_weight
        results.append((document, fused_score))

    # 融合分数降序排序，截取top_k返回
    results.sort(key=lambda item: item[1], reverse=True)
    return results[:top_k]
