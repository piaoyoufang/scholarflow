# 导入项目检索函数search：混合召回+rerank精排的RAG检索入口
from app.retrieval.search import search


def debug_retrieval(question: str, course_id: str, top_k: int = 5) -> dict:
    """
    检索调试工具函数，用于查看检索中间结果，方便排查RAG召回效果
    :param question: 用户的查询问题
    :param course_id: 指定课程ID，检索会做课程知识库隔离
    :param top_k: 返回检索结果条数，默认5条
    :return: 字典，包含问题、课程id、每条召回块的排名、分数、元数据、内容预览
    """
    # 调用检索函数，传入问题、课程id过滤、返回条数；得到列表[(Document, 分数), ...]
    results = search(query=question, course_id=course_id, k=top_k)

    # 初始化列表，用来整理格式化后的检索结果，方便打印/接口返回查看
    items = []

    # enumerate(start=1)：遍历检索结果，index从1开始代表排名；document是文档块对象，score是相关性分数
    for index, (document, score) in enumerate(results, start=1):
        # 取出文档元数据，做兜底，如果metadata为None，赋值空字典，避免后续.get()报错
        metadata = document.metadata or {}
        # 取出文档文本内容，兜底为空字符串，防止page_content为None报错
        content = document.page_content or ""

        # 将单条检索结果组装成字典，存入items列表
        items.append(
            {
                "rank": index,                          # 召回结果排名，1为最相关
                "score": score,                         # rerank输出的相关性分数，数值越大越相关
                "source_id": metadata.get("source_id", ""),     # 文档唯一id，溯源用
                "source_name": metadata.get("source_name", ""), # 原始文件名，用于前端展示引用
                "chunk_index": metadata.get("chunk_index", ""), # 当前块在原文档中的分片下标
                "course_id": metadata.get("course_id", ""),    # 所属课程id，校验过滤是否生效
                "content_preview": content[:300],       # 文本预览，只截取前300字符，防止输出内容过长
            }
        )
    # 返回完整调试结果字典
    return {"question": question, "course_id": course_id, "items": items}