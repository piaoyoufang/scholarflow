"""Alibaba DashScope text rerank client."""
# 支持函数内直接使用未定义的类型注解（前向引用）
from __future__ import annotations

# 通用类型注解
from typing import Any

# HTTP异步/同步请求库，用于调用通义千问重排API
import httpx
# LangChain文档对象，承载文本块与元数据
from langchain_core.documents import Document

# 项目全局配置，读取模型名称、地址、密钥、超时等参数
from app.config import settings
# 封装重试逻辑工具，网络异常自动重试
from app.resilience import run_with_retry


def rerank_documents(
    query: str,
    candidates: list[tuple[Document, float]],
    *,
    top_k: int,
) -> list[tuple[Document, float]]:
    """
    调用阿里DashScope重排接口，对混合检索结果二次精排
    :param query: 用户原始查询问题
    :param candidates: 混合检索得到的候选列表 [(文档对象,混合融合分数)]
    :param top_k: 重排后最终保留的文档数量
    :return: [(Document, 重排相关性分数)]，分数越大相关性越高，降序排列
    """
    # 校验返回条数参数合法性
    if top_k < 1:
        raise ValueError("top_k 必须大于等于 1")
    # 没有候选文档，直接返回空列表，无需调用API
    if not candidates:
        return []

    # 组装DashScope重排接口请求体
    payload = {
        "model": settings.rerank_model,  # 重排模型名称，从配置读取
        "input": {
            "query": query,  # 用户查询文本
            # 遍历候选文档，只提取正文文本送入重排服务
            "documents": [
                document.page_content
                for document, _hybrid_score in candidates
            ],
        },
        "parameters": {
            "return_documents": False,  # 不需要服务端返回原文，只返回索引和分数，节省流量
        },
    }

    def request() -> list[tuple[Document, float]]:
        """内部请求函数，被重试装饰器包装，失败自动重试"""
        # 发起POST请求调用DashScope重排接口
        response = httpx.post(
            settings.rerank_base_url,  # 重排服务接口地址
            headers={
                # 鉴权密钥
                "Authorization": f"Bearer {settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,  # 携带构造好的请求体
            timeout=settings.rerank_timeout_seconds,  # 请求超时时间
        )
        # 如果HTTP状态码4xx/5xx，直接抛出异常，触发重试机制
        response.raise_for_status()
        # 解析接口返回JSON
        body: dict[str, Any] = response.json()
        # 获取重排结果数组
        results = body.get("output", {}).get("results", [])
        # 校验返回结果格式，无结果抛出异常
        if not isinstance(results, list) or not results:
            raise ValueError("阿里 rerank 返回结果为空")

        ranked: list[tuple[Document, float]] = []
        # 遍历重排接口返回的每条打分结果
        for item in results:
            index = int(item["index"])  # 对应传入documents数组的下标
            # 兼容两种字段名：relevance_score / score，防止接口字段变动
            score = float(
                item.get("relevance_score", item.get("score", 0.0))
            )
            # 防御校验：下标不能超出候选文档范围
            if not 0 <= index < len(candidates):
                raise ValueError("阿里 rerank 返回了越界索引")
            # 根据下标找回原始Document对象，绑定重排分数
            ranked.append((candidates[index][0], score))

        # 按照重排分数从高到低排序
        ranked.sort(key=lambda item: item[1], reverse=True)
        # 截取top_k条返回
        return ranked[:top_k]

    # 使用重试工具执行请求函数，标记组件名称用于监控埋点
    return run_with_retry(
        request,
        component="retrieval.rerank",
    )
