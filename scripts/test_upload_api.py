from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import app.api as api_module
from app.api import app, current_session


def main() -> None:
    client = TestClient(app)
    unauthorized = client.post(
        "/documents/upload",
        files={"file": ("lesson.md", b"test", "text/markdown")},
    )
    assert unauthorized.status_code == 401, unauthorized.text

    app.dependency_overrides[current_session] = lambda: (
        "upload-test-user",
        "upload-test-token",
    )

    try:
        with TemporaryDirectory() as directory:
            upload_dir = Path(directory)
            with patch.object(api_module, "UPLOAD_DIR", upload_dir):
                with patch.object(api_module, "ingest", return_value=2):
                    success = client.post(
                        "/documents/upload",
                        files={
                            "file": (
                                "lesson.md",
                                b"ScholarFlow upload lesson",
                                "text/markdown",
                            )
                        },
                    )
                assert success.status_code == 200, success.text
                assert success.json()["chunk_count"] == 2
                assert (upload_dir / "lesson.md").exists()

                unsupported = client.post(
                    "/documents/upload",
                    files={
                        "file": (
                            "lesson.docx",
                            b"x",
                            "application/octet-stream",
                        )
                    },
                )
                assert unsupported.status_code == 400, unsupported.text

                empty = client.post(
                    "/documents/upload",
                    files={"file": ("empty.txt", b"", "text/plain")},
                )
                assert empty.status_code == 400, empty.text

                too_large = client.post(
                    "/documents/upload",
                    files={
                        "file": (
                            "large.txt",
                            b"x" * (10 * 1024 * 1024 + 1),
                            "text/plain",
                        )
                    },
                )
                assert too_large.status_code == 413, too_large.text

                assert api_module.safe_upload_name("../../CON.txt") == "uploaded_CON.txt"
    finally:
        app.dependency_overrides.clear()

    print("上传API离线测试：6/6 通过")


if __name__ == "__main__":
    main()
