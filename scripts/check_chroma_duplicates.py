"""这是向量库完整性校验工具，作用两点：
统计 Chroma 库里所有文档分片，按source_id统计每个文件一共切分了多少向量片段；
强制校验唯一性：(source_id, chunk_index) 二元组合全局不能重复，一旦出现重复分片直接报错退出，防止 RAG 检索重复文本、评估指标失真。"""
from collections import Counter

import chromadb

from app.config import settings


def main() -> None:
    client = chromadb.PersistentClient(path=str(settings.vector_db_dir)) # 持久化 Chroma 客户端，读取本地磁盘保存的向量库
    collection = client.get_collection("scholarflow") # 获取项目唯一向量集合scholarflow，所有 PDF/MD 文档切片全部存在这个集合中
    result = collection.get(include=["metadatas"])
    metadatas = result.get("metadatas") or []

    # 统计每个 source_id 的分片总量
    source_counts = Counter(
        metadata.get("source_id", "unknown")
        for metadata in metadatas
    )
    #
    keys = [
        (
            metadata.get("source_id", "unknown"),
            metadata.get("chunk_index", "unknown"),
        )
        for metadata in metadatas
    ]
    # Counter 统计每个二元元组出现次数
    # 列表推导筛选出出现次数 > 1 的元组，存入duplicate_keys（即重复分片）
    duplicate_keys = [key for key, count in Counter(keys).items() if count > 1]

    print("片段总数：", len(metadatas))
    print("各来源片段数：")
    for source_id, count in sorted(source_counts.items()):
        print(f"- {source_id}: {count}")

    if duplicate_keys:
        print("发现重复的 (source_id, chunk_index)：")
        for key in duplicate_keys:
            print("-", key)
        raise SystemExit(1)

    print("重复检查通过：没有重复的来源片段编号。")


if __name__ == "__main__":
    main()