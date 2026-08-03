import sys

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import settings
from app.models import embeddings
from app.retrieval.hybrid import bm25_scores, hybrid_candidates
from app.retrieval.rerank import rerank_documents


def short_text(text: str, length: int = 100) -> str:
    """文本缩略工具，去除多余空格，超长内容截断并添加省略号，方便控制台打印查看"""
    # 连续空白字符统一替换为单个空格
    value = " ".join((text or "").split())
    # 文本长度正常直接返回；超过阈值进行截断
    return value if len(value) <= length else f"{value[:length]}..."


def print_rows(title: str, rows: list[tuple[Document, float]]) -> None:
    """格式化打印检索结果，统一输出样式，展示分数、来源元数据、摘要文本"""
    print(f"\n{'=' * 25} {title} {'=' * 25}")
    # 遍历检索结果，序号从1开始
    for index, (document, score) in enumerate(rows, start=1):
        print(
            f"[{index}] score={float(score):.4f} | "
            f"source={document.metadata.get('source_name')} | "
            f"source_id={document.metadata.get('source_id')} | "
            f"chunk={document.metadata.get('chunk_index')}"
        )
        # 输出截断后的文本内容
        print(f"    {short_text(document.page_content)}")


def main() -> None:
    # 校验命令行入参，必须传入查询语句
    if len(sys.argv) != 2:
        raise SystemExit(
            '用法：python -m scripts.inspect_retrieval_pipeline "你的问题"'
        )

    # 获取用户输入的查询问句
    query = sys.argv[1].strip()
    # 检索候选召回数量
    candidate_k = 24
    # 初始化Chroma向量库实例
    db = Chroma(
        collection_name="scholarflow",
        embedding_function=embeddings(),
        persist_directory=settings.vector_db_dir,
    )

    # 1.执行纯向量检索，获取24条向量结果
    vector_rows = db.similarity_search_with_score(query, k=candidate_k)
    # 读取向量库内全部文档内容与元数据，用于BM25打分
    stored = db.get(include=["documents", "metadatas"])
    # 将Chroma原始数据转换成Document对象列表
    all_documents = [
        Document(page_content=text or "", metadata=metadata or {})
        for text, metadata in zip(
            stored.get("documents", []),
            stored.get("metadatas", []),
        )
    ]

    # 2.计算全部文档BM25关键词分数
    keyword_scores = bm25_scores(query, all_documents)
    # BM25分数降序排序，截取前10条用于打印观察
    bm25_rows = sorted(
        zip(all_documents, keyword_scores),
        key=lambda item: item[1],
        reverse=True,
    )[:10]
    # 3.执行混合检索：向量+BM25分数加权融合
    mixed_rows = hybrid_candidates(
        query,
        vector_rows,
        all_documents,
        top_k=candidate_k,
    )
    try:
        reranked_rows = rerank_documents(query, mixed_rows, top_k=6)
    except Exception:
        print("⚠️ Rerank接口调用失败，降级使用混合召回结果")
        reranked_rows = mixed_rows[:6]

    # 控制台输出完整链路各阶段结果，方便调试对比
    print(f"查询：{query}")
    print_rows("向量 Top 10（distance 越小越好）", vector_rows[:10])
    print_rows("BM25 Top 10（score 越大越好）", bm25_rows)
    print_rows("混合召回 Top 10（score 越大越好）", mixed_rows[:10])
    print_rows("阿里 rerank Top 6（score 越大越好）", reranked_rows)


if __name__ == "__main__":
    main()
