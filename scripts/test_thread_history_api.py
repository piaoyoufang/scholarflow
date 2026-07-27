from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from fastapi.testclient import TestClient

import app.api as api_module
from app.api import app
from app.schemas import ResearchAnswer


@dataclass
class FakeState:
    values: dict


class FakeMemoryWorkflow:
    def __init__(self) -> None:
        self.states: dict[str, dict] = {}

    def invoke(self, inputs: dict, config: dict) -> dict:
        thread_id = config["configurable"]["thread_id"]
        history = [
            {"role": "user", "content": inputs["question"]},
            {"role": "assistant", "content": "这是离线测试回答。"},
        ]
        self.states[thread_id] = {"history": history}
        return {
            "answer": ResearchAnswer(
                answer="这是离线测试回答。",
                citations=[],
                confidence=1.0,
                missing_information=[],
            ),
            "history": history,
            "agent_trace": ["test_agent"],
        }

    def get_state(self, config: dict) -> FakeState:
        thread_id = config["configurable"]["thread_id"]
        return FakeState(values=self.states.get(thread_id, {}))


def main() -> None:
    original_memory_workflow = api_module.memory_workflow
    api_module.memory_workflow = FakeMemoryWorkflow()

    try:
        client = TestClient(app)
        username = f"history_api_{uuid4().hex[:10]}"
        password = "Password12345"

        register_response = client.post(
            "/auth/register",
            json={"username": username, "password": password},
        )
        assert register_response.status_code == 201, register_response.text
        token = register_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        thread_id = str(uuid4())
        ask_response = client.post(
            "/ask",
            headers=headers,
            json={
                "question": "测试线程历史是否能被前端恢复",
                "thread_id": thread_id,
            },
        )
        assert ask_response.status_code == 200, ask_response.text

        list_response = client.get("/threads", headers=headers)
        assert list_response.status_code == 200, list_response.text
        threads = list_response.json()["threads"]
        current_thread = next(
            item for item in threads if item["thread_id"] == thread_id
        )
        assert current_thread["exists"] is True
        assert current_thread["history_count"] == 2

        detail_response = client.get(f"/threads/{thread_id}", headers=headers)
        assert detail_response.status_code == 200, detail_response.text
        detail = detail_response.json()
        assert detail["exists"] is True
        assert detail["history_count"] == 2
        assert detail["history"][0]["role"] == "user"
        assert detail["history"][1]["role"] == "assistant"
    finally:
        api_module.memory_workflow = original_memory_workflow

    print("线程列表接口：通过")
    print("线程历史恢复接口：通过")


if __name__ == "__main__":
    main()
