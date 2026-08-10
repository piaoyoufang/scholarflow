
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.models import embeddings


def load_file(path: str, course_id: str | None = None, source_id: str | None = None):
    """?? PDF / Markdown / TXT??? LangChain Document?????????????"""
    file = Path(path)
    if file.suffix.lower() == ".pdf":
        docs = PyPDFLoader(str(file)).load()
    elif file.suffix.lower() in {".md", ".txt"}:
        docs = TextLoader(str(file), encoding="utf-8-sig").load()
    else:
        raise ValueError("??? PDF?Markdown ? TXT")

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120, add_start_index=True)
    chunks = splitter.split_documents(docs)
    real_source_id = source_id or file.stem

    for i, doc in enumerate(chunks):
        doc.metadata.update({
            "source_id": real_source_id,
            "source_name": file.name,
            "chunk_index": i,
        })
        if course_id:
            doc.metadata["course_id"] = course_id
    return chunks


def ingest(path: str, course_id: str | None = None, source_id: str | None = None) -> int:
    """????????????????? embedding???? Qdrant ? Chroma?"""
    chunks = load_file(path, course_id=course_id, source_id=source_id)
    real_source_id = source_id or Path(path).stem
    prefix = course_id or "default"
    ids = [f"{prefix}:{real_source_id}:{index}" for index in range(len(chunks))]

    if settings.vector_backend.lower() == "qdrant":
        from app.vectorstores.qdrant_store import delete_by_source_id, upsert_documents

        delete_by_source_id(real_source_id)
        vectors = embeddings().embed_documents([doc.page_content for doc in chunks])
        upsert_documents(chunks, vectors=vectors, ids=ids)
    else:
        from langchain_chroma import Chroma

        db = Chroma(
            collection_name="scholarflow",
            embedding_function=embeddings(),
            persist_directory=settings.vector_db_dir,
        )
        db.delete(where={"source_id": real_source_id})
        db.add_documents(chunks, ids=ids)
    return len(chunks)
