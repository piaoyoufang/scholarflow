import sys
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from langchain_chroma import Chroma

from app.api import UPLOAD_DIR, app
from app.config import settings
from app.models import embeddings


def main() -> None:
    unique = uuid4().hex[:10]
    source_id = f"v11_live_{unique}"
    filename = f"{source_id}.md"
    verification_code = f"JADE-{unique.upper()}"
    thread_id = str(uuid4())
    client = (
        httpx.Client(base_url=sys.argv[1].rstrip("/"), timeout=180)
        if len(sys.argv) == 2
        else TestClient(app)
    )

    session_response = client.post("/sessions")
    assert session_response.status_code == 200, session_response.text
    token = session_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    db = Chroma(
        collection_name="scholarflow",
        embedding_function=embeddings(),
        persist_directory=settings.vector_db_dir,
    )
    target = UPLOAD_DIR / filename

    try:
        content = (
            "# ScholarFlow v1.1 在线验收\n\n"
            f"本次上传验收码是 {verification_code}。"
            "该资料通过鉴权上传接口写入 Chroma。"
        ).encode("utf-8")
        upload = client.post(
            "/documents/upload",
            headers=headers,
            files={"file": (filename, content, "text/markdown")},
        )
        assert upload.status_code == 200, upload.text
        assert upload.json()["chunk_count"] > 0

        ask = client.post(
            "/ask",
            headers=headers,
            json={
                "question": "[KNOWLEDGE] 本次上传资料中的验收码是什么？",
                "thread_id": thread_id,
            },
        )
        assert ask.status_code == 200, ask.text
        body = ask.json()
        assert verification_code in body["answer"], body["answer"]
        assert any(
            citation["source_id"] == source_id
            for citation in body.get("citations", [])
        ), body.get("citations", [])

        threads = client.get("/threads", headers=headers)
        assert threads.status_code == 200, threads.text
        current = next(
            item for item in threads.json()["threads"]
            if item["thread_id"] == thread_id
        )
        assert current["title"] == "[KNOWLEDGE] 本次上传资料中的验收码是什么？"
        assert current["history_count"] == 2

        print("在线上传：通过")
        print("上传资料检索与引用：通过")
        print("会话标题与历史：通过")
    finally:
        try:
            client.delete(f"/threads/{thread_id}", headers=headers)
        except Exception:
            pass
        try:
            client.delete("/sessions/current", headers=headers)
        except Exception:
            pass
        client.close()
        db.delete(where={"source_id": source_id})
        target.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
