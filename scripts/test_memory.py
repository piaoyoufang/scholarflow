# 导入uuid工具，生成随机唯一字符串，用来区分不同测试会话thread_id
from uuid import uuid4

# 导入带会话记忆的Agent流程图实例、全局内存存储器（会话数据读写/删除）
from app.graph.builder import memory_store, memory_workflow

def invoke(thread_id: str, question: str):
    """封装统一调用函数：执行带记忆Agent流程，简化重复代码
    :param thread_id: 会话唯一标识，用来绑定独立对话历史
    :param question: 用户输入的提问文本
    :return: Agent完整状态字典（包含history、answer、检索数据等）
    """
    # 执行带记忆的流程图，传入当前提问与会话ID配置
    return memory_workflow.invoke(
        {"question": question},
        config={"configurable": {"thread_id": thread_id}},
    )

def main() -> None:
    """主测试函数：校验LangGraph记忆三大核心特性
    1. 同thread_id多轮对话历史累加
    2. 不同thread_id会话完全隔离互不干扰
    3. delete_thread可以彻底清空指定会话所有状态数据
    """
    # 生成测试会话A的唯一ID，拼接测试标识避免和线上会话冲突
    thread_a = f"memory-test-a-{uuid4()}"
    # 生成测试会话B的唯一ID，独立于thread_a
    thread_b = f"memory-test-b-{uuid4()}"

    # 给会话A发送第一轮提问：FastAPI 在 ScholarFlow 中负责什么？
    first = invoke(thread_a, "FastAPI 在 ScholarFlow 中负责什么？")
    # 断言校验：一轮完整对话包含user+assistant两条消息，history长度必须等于2
    assert len(first.get("history", [])) == 2

    # 给同一个会话A发送追问，依赖上文FastAPI上下文
    follow_up = invoke(thread_a, "那它接收什么，又输出什么？")
    # 断言校验：两轮对话合计4条消息，历史正常累加
    assert len(follow_up.get("history", [])) == 4
    # 断言校验：问题改写节点读取了历史，问句里补全了FastAPI关键词
    assert "FastAPI" in follow_up.get("retrieval_question", "")

    # 切换全新独立会话B，发送无上下文的指代追问“它负责什么？”
    isolated = invoke(thread_b, "它负责什么？")
    # 断言校验：会话B全新空历史，仅生成2条消息，不受会话A数据污染
    assert len(isolated.get("history", [])) == 2
    # 断言校验：会话B无FastAPI上下文，改写后的问句不会包含FastAPI关键词，证明会话隔离生效
    assert "FastAPI" not in isolated.get("retrieval_question", "")

    # 调用存储器接口，彻底删除会话A的全部记忆与状态
    memory_store.delete_thread(thread_a)
    # 根据会话A的ID读取当前状态
    deleted_state = memory_workflow.get_state(
        {"configurable": {"thread_id": thread_a}}
    )
    # 断言校验：删除后状态values为空，代表记忆彻底清空
    assert not deleted_state.values

    # 全部断言无报错则打印测试通过提示
    print("同线程追问：通过")
    print("不同线程隔离：通过")
    print("删除线程记忆：通过")

# 脚本直接运行时自动执行记忆完整测试用例
if __name__ == "__main__":
    main()