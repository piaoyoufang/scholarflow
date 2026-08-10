from __future__ import annotations

import atexit
from uuid import NAMESPACE_URL, uuid4, uuid5

from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.config import settings

def _make_client() -> QdrantClient:
    if settings.qdrant_url.lower() == "local":
        from pathlib import Path
        path = Path(settings.qdrant_path)
        if not path.is_absolute():
            from app.config import PROJECT_ROOT
            path = PROJECT_ROOT / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return QdrantClient(path=str(path))
    return QdrantClient(url=settings.qdrant_url)


client = _make_client()
atexit.register(client.close)


def ensure_collection() -> None:
    collections = client.get_collections().collections
    names = {item.name for item in collections}
    if settings.qdrant_collection in names:
        return
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(size=settings.qdrant_vector_size, distance=Distance.COSINE),
    )


def upsert_documents(documents: list[Document], vectors: list[list[float]], ids: list[str] | None = None) -> None:
    ensure_collection()
    points = []
    for index, (document, vector) in enumerate(zip(documents, vectors)):
        metadata = document.metadata or {}
        payload = {**metadata, "text": document.page_content or ""}
        points.append(PointStruct(id=(str(uuid5(NAMESPACE_URL, ids[index])) if ids else str(uuid4())), vector=vector, payload=payload))
    if points:
        client.upsert(collection_name=settings.qdrant_collection, points=points)


def _course_filter(course_id: str | None = None, source_id: str | None = None) -> Filter | None:
    conditions = []
    if course_id:
        conditions.append(FieldCondition(key="course_id", match=MatchValue(value=course_id)))
    if source_id:
        conditions.append(FieldCondition(key="source_id", match=MatchValue(value=source_id)))
    return Filter(must=conditions) if conditions else None


def search_by_vector(query_vector: list[float], k: int, course_id: str | None = None) -> list[tuple[Document, float]]:
    ensure_collection()
    hits = client.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        query_filter=_course_filter(course_id=course_id),
        limit=k,
        with_payload=True,
    )
    results = []
    for hit in hits:
        payload = hit.payload or {}
        text = str(payload.pop("text", ""))
        results.append((Document(page_content=text, metadata=payload), float(hit.score)))
    return results


def list_documents(course_id: str | None = None, limit: int = 10000) -> list[Document]:
    ensure_collection()
    points, _next = client.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=_course_filter(course_id=course_id),
        limit=limit,
        with_payload=True,
        with_vectors=False,
    )
    docs = []
    for point in points:
        payload = point.payload or {}
        text = str(payload.pop("text", ""))
        docs.append(Document(page_content=text, metadata=payload))
    return docs


def delete_by_source_id(source_id: str) -> None:
    ensure_collection()
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=_course_filter(source_id=source_id),
    )


def collection_status() -> tuple[bool, str]:
    try:
        ensure_collection()
        info = client.get_collection(settings.qdrant_collection)
        return True, f"ok(points={info.points_count})"
    except Exception as exc:
        return False, type(exc).__name__
