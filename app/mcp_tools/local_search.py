from typing import Any


KNOWLEDGE_BASE = [
    {
        "title": "MCP 的作用",
        "content": "MCP 是 Agent 与外部工具之间的标准通信协议。Server 暴露工具，Client 发现并调用工具。",
        "source_id": "mcp_local_notes",
        "source_name": "MCP 本地补充资料",
        "keywords": ["mcp", "协议", "server", "client", "工具"],
    },
    {
        "title": "MCP 的接入顺序",
        "content": "先测试普通 Python 函数，再测试 MCP Server 和 Client，最后接入 LangGraph。",
        "source_id": "mcp_local_notes",
        "source_name": "MCP 本地补充资料",
        "keywords": ["mcp", "顺序", "接入", "测试", "langgraph"],
    },
    {
        "title": "RAG 的作用",
        "content": "RAG 先检索证据，再让模型根据证据回答，从而提高可追溯性并减少幻觉。",
        "source_id": "rag_local_notes",
        "source_name": "RAG 本地补充资料",
        "keywords": ["rag", "检索", "证据", "幻觉"],
    },
    {
        "title": "为什么第十步先用 [MCP] 前缀",
        "content": (
            "第十步先使用 [MCP] 前缀做显式路由，是为了让 MCP 接入过程稳定、"
            "可调试、可回滚。这样可以分层确认普通 Python 函数、MCP Server、"
            "MCP Client 和 LangGraph 节点都正常，并且不会破坏原来 RAG 的评估基线。"
            "等这些都稳定后，第十一步再升级为 Qwen 自动判断是否调用 MCP。"
        ),
        "source_id": "mcp_local_notes",
        "source_name": "MCP 本地补充资料",
        "keywords": ["mcp", "前缀", "显式路由", "稳定", "调试", "评估基线"],
    },
]


def search_local_knowledge(query: str, top_k: int = 3) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        raise ValueError("query 不能为空")
    if not 1 <= top_k <= 10:
        raise ValueError("top_k 必须在 1 到 10 之间")

    normalized_query = query.lower()
    scored_items = []
    """
    这是核心匹配逻辑，用生成器表达式 + sum 实现：
    遍历当前条目的每个关键词 keyword
    把关键词也转成小写，判断它是否出现在归一化后的查询字符串里
    每命中一个关键词，就产生一个数字 1
    sum() 把所有 1 加起来，最终分数 = 命中的关键词个数
    """
    for item in KNOWLEDGE_BASE:
        score = sum(
            1 for keyword in item["keywords"]
            if keyword.lower() in normalized_query
        )
        if score > 0: # 只有分数 > 0（至少命中一个关键词）的条目才会被保留
            scored_items.append((score, item))  # 把 (分数, 条目) 组成的元组放进 scored_items 列表排序与返回

    scored_items.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "title": item["title"],
            "content": item["content"],
            "source_id": item["source_id"],
            "source_name": item["source_name"],
            "score": score,
        }
        for score, item in scored_items[:top_k] # 切片 scored_items[:top_k]：只取排序后的前 top_k 条
    ]