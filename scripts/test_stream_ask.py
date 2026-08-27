"""流式问答接口（/courses/{id}/ask/stream）离线测试
用 TestClient + 假事件流验证 SSE 帧序列，不依赖大模型、MySQL 与网络，可进 CI 离线门禁
运行：python -m scripts.test_stream_ask
"""
from __future__ import annotations

from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

import app.api as api_module
from app.api import app, current_session
from app.schemas import Citation, ResearchAnswer


class FakeStreamWorkflow:
    """模拟 memory_workflow 的流式接口：只实现 astream_events，
    产出与真实 LangGraph 相同结构的 v2 事件（节点开始/结束）"""

    async def astream_events(self, inputs, config, version):
        assert version == "v2"
        answer = ResearchAnswer(
            answer="流式测试回答",
            citations=[
                Citation(
                    source_id="src-1",
                    source_name="测试资料",
                    locator="第 1 页",
                    quote="引用片段",
                )
            ],
            confidence=0.9,
            missing_information=[],
        )
        # 与真实执行顺序一致：各节点 start，answer_agent 最后 end 并携带答案
        for node in ("rewrite_question", "supervisor", "knowledge_agent", "answer_agent"):
            yield {"event": "on_chain_start", "name": node, "data": {}}
        yield {
            "event": "on_chain_end",
            "name": "answer_agent",
            "data": {"output": {"answer": answer}},
        }


def main() -> None:
    client = TestClient(app)

    # 1) 未登录：必须在响应头发出前被 401 拦截（流式一旦开始就无法再用状态码报错）
    course_id = "course-stream-test"
    thread_id = str(uuid4())
    unauthorized = client.post(
        f"/courses/{course_id}/ask/stream",
        json={"question": "什么是 RAG？", "thread_id": thread_id},
    )
    assert unauthorized.status_code == 401, unauthorized.text

    # 2) 已登录但无课程权限：流式开始前返回 403
    app.dependency_overrides[current_session] = lambda: ("stream-test-user", "token")
    with patch.object(
        api_module.course_store,
        "require_course_access",
        side_effect=PermissionError("不是课程成员"),
    ):
        forbidden = client.post(
            f"/courses/{course_id}/ask/stream",
            json={"question": "什么是 RAG？", "thread_id": thread_id},
        )
    assert forbidden.status_code == 403, forbidden.text

    # 3) 正常流式：权限放行 + 假事件流；埋点写入打桩为 Mock，验证与非流式接口行为一致
    record_event = Mock()

    async def fake_get_workflow():
        return FakeStreamWorkflow()

    with (
        patch.object(api_module.course_store, "require_course_access", return_value=None),
        patch.object(api_module.auth_store, "claim_thread", return_value=None),
        patch.object(api_module.auth_store, "update_thread_title", return_value=None),
        patch.object(api_module.qa_event_store, "record_event", record_event),
        patch.object(api_module, "get_async_memory_workflow", fake_get_workflow),
    ):
        response = client.post(
            f"/courses/{course_id}/ask/stream",
            json={"question": "什么是 RAG？", "thread_id": thread_id},
        )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")

    body = response.text
    # 帧序列：status（各节点进度）→ answer（完整答案）→ done（结束）
    assert body.count("event: status") == 4, body
    assert "正在检索课程资料" in body
    assert "正在生成回答" in body
    assert "event: answer" in body and "流式测试回答" in body
    assert "测试资料" in body  # 引用来源随 answer 帧下发
    assert body.rstrip().endswith("event: done\ndata: {}"), body
    # 答案帧必须出现在 done 帧之前
    assert body.index("event: answer") < body.index("event: done")

    # 行为一致性：与非流式 ask_course 一样写问答埋点
    record_event.assert_called_once()
    assert record_event.call_args.kwargs["answer"] == "流式测试回答"
    assert record_event.call_args.kwargs["citation_count"] == 1

    print("流式问答鉴权拦截：通过")
    print("流式问答 SSE 帧序列：通过")
    print("流式问答埋点一致性：通过")


if __name__ == "__main__":
    main()
