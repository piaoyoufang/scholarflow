from langchain_core.documents import Document
# 导入待测试的重排接口封装函数
from app.retrieval.rerank import rerank_documents


def test_rerank_uses_alibaba_result_indexes(monkeypatch):
    """
    单元测试：验证Rerank封装逻辑能够正确解析阿里返回的index索引，完成文档重排序
    使用monkeypatch模拟httpx网络请求，不调用真实DashScope API，无网络、无费用
    """

    # 模拟阿里Rerank接口返回对象
    class FakeResponse:
        # 模拟接口正常状态，不会抛出HTTP异常
        def raise_for_status(self):
            return None

        # 模拟接口返回标准JSON结构
        def json(self):
            return {
                "output": {
                    "results": [
                        # index=1 对应传入的第2个文档，高分
                        {"index": 1, "relevance_score": 0.95},
                        # index=0 对应传入的第1个文档，低分
                        {"index": 0, "relevance_score": 0.10},
                    ]
                }
            }

    # 劫持 httpx.post 请求，替换为返回伪造响应，切断真实网络调用
    monkeypatch.setattr(
        "app.retrieval.rerank.httpx.post",
        lambda *args, **kwargs: FakeResponse(),
    )

    # 构造两条候选文档
    generic = Document(page_content="一般内容")
    exact = Document(page_content="能直接回答问题的内容")

    # 调用rerank函数，传入候选列表顺序：[generic(下标0), exact(下标1)]
    results = rerank_documents(
        "问题",
        [(generic, 0.9), (exact, 0.8)],
        top_k=2,
    )

    # 断言：重排后第一名是exact文档（对应接口返回index=1）
    assert results[0][0] is exact
    # 断言：文档绑定了重排返回的相关性分数0.95
    assert results[0][1] == 0.95
