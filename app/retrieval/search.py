# 它的核心职责是：接收用户的自然语言提问，在向量数据库中查找最相关的文档片段，并返回这些片段及其匹配度分数。
from langchain_chroma import Chroma
from app.config import settings
from app.models import embeddings

"""query: str: 接收用户的原始问题（例如："什么是量子纠缠？"）。
k: int = 6: 这是一个超参数，表示“召回数量”,
默认返回最相关的前 6 个文档片段。这个值越大，上下文越丰富，但噪声也可能越多。"""
def search(query: str, k: int = 6):
    db = Chroma(
        collection_name="scholarflow",
        embedding_function=embeddings(),
        persist_directory=settings.vector_db_dir,
    )
    """similarity_search_with_score: 这是 LangChain Chroma 封装的核心方法。
    原理：它计算用户问题的向量与库中所有文档向量的余弦相似度（或欧氏距离）。
    返回值：它不仅仅返回文档内容，还返回一个分数（Score）。
    注意：在 Chroma 中，这个分数通常是距离（Distance）。距离越小（越接近 0），表示相似度越高；距离越大，表示差异越大。这与某些其他数据库（分数越高越相似）的逻辑相反，后续处理结果时需要注意这一点。"""
    return db.similarity_search_with_score(query, k=k)