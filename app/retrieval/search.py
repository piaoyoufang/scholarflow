
from langchain_core.documents import Document

from app.config import settings
from app.models import embeddings
from app.retrieval.hybrid import hybrid_candidates
from app.retrieval.rerank import rerank_documents
from app.runtime_metrics import runtime_metrics


def search(query: str, k: int = 6, course_id: str | None = None) -> list[tuple[Document, float]]:
    """RAG ????????? + BM25 ???? + ?? Rerank ???"""
    if not query.strip():
        raise ValueError("query ????")
    if k < 1:
        raise ValueError("k ?????? 1")

    candidate_k = max(k * 4, 24)

    if settings.vector_backend.lower() == "qdrant":
        from app.vectorstores.qdrant_store import list_documents, search_by_vector

        query_vector = embeddings().embed_query(query)
        vector_results = search_by_vector(query_vector, k=candidate_k, course_id=course_id)
        all_documents = list_documents(course_id=course_id)
    else:
        from langchain_chroma import Chroma

        db = Chroma(
            collection_name="scholarflow",
            embedding_function=embeddings(),
            persist_directory=settings.vector_db_dir,
        )
        if course_id:
            vector_results = db.similarity_search_with_score(query, k=candidate_k, filter={"course_id": course_id})
            stored = db.get(include=["documents", "metadatas"], where={"course_id": course_id})
        else:
            vector_results = db.similarity_search_with_score(query, k=candidate_k)
            stored = db.get(include=["documents", "metadatas"])
        all_documents = [
            Document(page_content=content or "", metadata=metadata or {})
            for content, metadata in zip(stored.get("documents", []), stored.get("metadatas", []))
        ]

    mixed = hybrid_candidates(
        query,
        vector_results,
        all_documents,
        top_k=candidate_k,
        vector_weight=0.65,
        bm25_weight=0.35,
    )

    try:
        return rerank_documents(query, mixed, top_k=k)
    except Exception:
        runtime_metrics.record_fallback("retrieval.rerank")
        return mixed[:k]
