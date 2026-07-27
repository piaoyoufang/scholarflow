"""通过 Chroma API 查看向量库中的文档片段，而不是直接猜 SQLite 内部表。"""
from __future__ import annotations

import argparse
from pathlib import Path

import chromadb

from app.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(description="查看 ScholarFlow Chroma 文档片段")
    parser.add_argument("--limit", type=int, default=20, help="最多显示多少个片段")
    args = parser.parse_args()

    db_path = Path(settings.vector_db_dir)
    client = chromadb.PersistentClient(path=str(db_path))
    try:
        collection = client.get_collection("scholarflow")
    except Exception as exc:
        raise SystemExit(
            f"找不到 collection scholarflow，请先运行 scripts.ingest。数据库目录：{db_path}"
        ) from exc

    result = collection.get(include=["documents", "metadatas"])
    total = len(result["ids"])
    print(f"数据库目录：{db_path}")
    print(f"collection：scholarflow")
    print(f"片段总数：{total}")
    print("=" * 80)

    for index, (doc_id, document, metadata) in enumerate(
        zip(result["ids"], result["documents"], result["metadatas"]), start=1
    ):
        if index > args.limit:
            break
        metadata = metadata or {}
        print(f"[{index}] id={doc_id}")
        print(f"来源：{metadata.get('source_name', metadata.get('source_id', '未知'))}")
        print(f"source_id：{metadata.get('source_id', '未知')}")
        print(f"内容：{(document or '').strip()}")
        print("-" * 80)


if __name__ == "__main__":
    main()
