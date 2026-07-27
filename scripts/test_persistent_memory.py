# 导入命令行参数解析模块，实现脚本多模式运行（写入/读取/清空）
import argparse

# 导入持久化SQLite记忆存储器、带会话记忆的Agent流程图
from app.graph.builder import memory_store, memory_workflow

# 固定本次测试使用的会话唯一标识，全程复用同一个thread_id
THREAD_ID = "persistent-memory-test"
# 封装LangGraph执行所需的会话配置，绑定测试专用thread_id
CONFIG = {"configurable": {"thread_id": THREAD_ID}}


def write_first_turn() -> None:
    """模式1：写入首轮对话数据，将状态持久保存到SQLite数据库"""
    # 先清空该会话旧数据，避免历史残留干扰本次测试
    memory_store.delete_thread(THREAD_ID)
    # 执行Agent完整流程，发送首轮测试提问，对话状态自动存入sqlite文件
    result = memory_workflow.invoke(
        {"question": "FastAPI 在 ScholarFlow 中负责什么？"},
        config=CONFIG,
    )
    # 断言校验：一轮对话包含user+assistant两条消息，历史长度必须为2
    assert len(result.get("history", [])) == 2
    # 控制台打印执行成功提示
    print("第一进程写入成功")
    # 打印当前测试会话ID，方便核对数据库数据
    print("thread_id:", THREAD_ID)


def read_after_restart() -> None:
    """模式2：模拟程序重启后，从SQLite读取已保存的历史，继续追问"""
    # 从数据库读取该会话上次保存的完整状态
    before = memory_workflow.get_state(CONFIG)
    # 断言校验：必须能读取到上一步写入的会话数据，否则持久化失效
    assert before.values, "没有读到第一进程写入的状态"
    # 校验读取到的历史消息数量，确认首轮对话完整落地
    assert len(before.values.get("history", [])) == 2

    # 发送依赖上文的追问，程序自动读取sqlite中保存的历史上下文进行问题改写
    result = memory_workflow.invoke(
        {"question": "那它接收什么，又输出什么？"},
        config=CONFIG,
    )
    # 断言校验：两轮对话合计4条消息，证明历史正常累加
    assert len(result.get("history", [])) == 4
    # 断言校验：改写后的独立问句包含FastAPI，证明成功读取历史补全指代内容
    assert "FastAPI" in result.get("retrieval_question", "")
    # 打印读取恢复成功提示
    print("第二进程恢复成功")
    # 打印结合历史改写后的完整检索问句，直观查看改写效果
    print("独立问题：", result.get("retrieval_question"))


def clear_test_thread() -> None:
    """模式3：清空测试会话，删除数据库中该thread_id的所有持久化数据"""
    # 调用存储器接口，删除当前测试会话全部记录
    memory_store.delete_thread(THREAD_ID)
    # 再次读取该会话状态
    state = memory_workflow.get_state(CONFIG)
    # 断言校验：删除后状态数据为空，确认清理彻底
    assert not state.values
    # 打印清空完成提示
    print("测试线程已清除")


def main() -> None:
    """脚本入口：解析命令行参数，根据传入的mode执行对应测试逻辑"""
    # 创建命令行参数解析器实例
    parser = argparse.ArgumentParser()
    # 定义必填参数mode，限制只能传入write/read/clear三种值
    parser.add_argument(
        "mode",
        choices=["write", "read", "clear"],
    )
    # 解析终端传入的命令行参数
    args = parser.parse_args()

    # 根据传入的mode分支执行对应函数
    if args.mode == "write":
        # 执行写入首轮对话测试
        write_first_turn()
    elif args.mode == "read":
        # 执行重启读取历史+追问测试
        read_after_restart()
    else:
        # 执行会话数据清空测试
        clear_test_thread()


# 脚本直接运行时，启动主函数解析命令行参数执行测试
if __name__ == "__main__":
    main()