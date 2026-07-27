r"""`n连接性测试脚本：
用于验证 .env 配置、阿里百炼 Qwen 聊天模型、阿里百炼 text-embedding-v3 向量模型是否能正常工作。

推荐运行方式：
    在项目根目录 D:\python\ai-project\scholarflow 下执行：
    python -m scripts.check_model
"""
from app.models import chat_model, embeddings


print(chat_model().invoke("只回答：Qwen 连接成功").content)
vector = embeddings().embed_query("LangGraph 状态图")
print(f"向量维度: {len(vector)}")
