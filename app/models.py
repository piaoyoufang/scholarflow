# 这个包核心职责是根据配置，创建并管理用于对话和文本处理的 AI 模型实例。
from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings

"""使用@lru_cache这个装饰器后，程序在第一次调用函数时会创建对象，
之后再次调用时直接返回内存中已经创建好的对象，而不会重复创建。这能显著提高程序的运行速度。 """
# 主对话模型 (chat_model)
@lru_cache
def chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.chat_model,   # 读取 .env 中的 qwen-plus
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        temperature=0, # 温度设为0，让回答更严谨、确定
        # 单次完整对话全流程超时阈值，读取全局配置的总超时秒数
        timeout=settings.chat_timeout_seconds,
        # 关闭自动重试，出现异常直接抛出，不执行重试逻辑
        max_retries=0,
    )

# 快速模型 (fast_model)
@lru_cache
def fast_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.fast_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        temperature=0,
        timeout=settings.fast_timeout_seconds,
        max_retries=0,
    )

# 嵌入模型 (embeddings)
@lru_cache
def embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        check_embedding_ctx_length=False,
    )
