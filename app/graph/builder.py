# 程序退出钩子模块，可注册函数在程序关闭时自动执行（关闭数据库连接）
import atexit
# SQLite 数据库原生操作库，用于本地文件型数据库连接
import sqlite3
# aiosqlite：sqlite3 的 asyncio 封装，AsyncSqliteSaver 的连接对象由它创建
import aiosqlite
# 路径工具类，用于拼接、读取本地文件路径
from pathlib import Path

# LangGraph SQLite持久化存储：将会话记忆落地到sqlite文件，替代内存临时存储
from langgraph.checkpoint.sqlite import SqliteSaver
# 异步版SQLite持久化存储：SqliteSaver 不支持 async 调用（astream_events 需要），流式接口专用
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
# LangGraph序列化工具：支持复杂对象（Pydantic模型、自定义结构体）转JSON存入数据库
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

# 项目根目录常量（全局配置）
from app.config import PROJECT_ROOT, settings

# 导入流程图核心组件：END流程终点、START流程起点、状态图构建器
from langgraph.graph import END, START, StateGraph

# 导入分流总控节点，负责区分用户问题走向知识/报告分支
from app.agents.supervisor import supervisor_node
# 导入三类工作智能体节点，分别处理知识检索、评估报表、最终生成回答
from app.agents.workers import (
    # 知识检索智能体：向量库召回文档+MCP补充资料
    knowledge_agent_node,
    # 评估报表智能体：专用MCP查询评估报表数据，跳过向量检索
    report_agent_node,
    diagnosis_agent_node,
    # 最终回答生成智能体：整合素材调用大模型输出完整回复
    answer_agent_node,
)
# 导入问题改写节点，对用户原始提问优化、生成更适合检索的query
from app.graph.nodes import rewrite_question_node

# 导入全局状态模板，整个流程图所有节点共享此状态结构
from app.graph.state import AgentState

# LangGraph分支路由函数，Supervisor分流完成后根据决策选择下一个执行节点
def route_after_supervisor(state: AgentState) -> str:
    # 从全局对话状态中取出 Supervisor 生成的分流决策对象
    decision = state.get("supervisor_decision")
    # 兜底逻辑：不存在分流决策时，默认走知识检索Agent流程
    if not decision:
        return "knowledge_agent"
    # 存在合法分流决策，直接返回决策指定的下一个节点标识（knowledge_agent / report_agent）
    return decision.next_agent

# 构建完整LangGraph问答流程图的工厂函数
# checkpointer：可选参数，传入记忆持久化对象可实现对话历史断点保存
def build_graph(checkpointer=None):
    # 实例化状态图，绑定全局对话状态类AgentState，所有节点共享该状态
    graph = StateGraph(AgentState)

    # 注册【问题改写】节点，节点标识rewrite_question，绑定对应处理函数
    graph.add_node("rewrite_question", rewrite_question_node)
    # 注册【分流总控】节点，节点标识supervisor，绑定分流决策函数
    graph.add_node("supervisor", supervisor_node)
    # 注册【知识检索智能体】节点，处理普通资料问答
    graph.add_node("knowledge_agent", knowledge_agent_node)
    # 注册【评估报表智能体】节点，专门处理评估报告类查询
    graph.add_node("report_agent", report_agent_node)
    graph.add_node("diagnosis_agent", diagnosis_agent_node)
    # 注册【最终回答生成】节点，统一汇总素材输出答案
    graph.add_node("answer_agent", answer_agent_node)

    # 流程起始START节点 → 问题改写节点，对话入口固定先走问题预处理
    graph.add_edge(START, "rewrite_question")
    # 问题改写完成 → 分流总控节点，预处理后交给Supervisor判断分支
    graph.add_edge("rewrite_question", "supervisor")

    # 添加条件分支边：supervisor节点执行完成后，根据路由函数动态选择下游节点
    graph.add_conditional_edges(
        # 分支判断来源节点：分流总控supervisor
        "supervisor",
        # 路由判断函数，返回下一步节点名称字符串
        route_after_supervisor,
        # 路由映射字典：路由返回值 -> 对应目标节点
        {
            # 返回knowledge_agent则流转至知识检索节点
            "knowledge_agent": "knowledge_agent",
            # 返回report_agent则流转至报表处理节点
            "report_agent": "report_agent",
            "diagnosis_agent": "diagnosis_agent",
        },
    )

    # 知识检索节点执行完毕 → 统一进入回答生成节点
    graph.add_edge("knowledge_agent", "answer_agent")
    # 报表处理节点执行完毕 → 统一进入回答生成节点
    graph.add_edge("report_agent", "answer_agent")
    graph.add_edge("diagnosis_agent", "answer_agent")
    # 最终回答生成完成 → END流程结束节点，本轮对话终止
    graph.add_edge("answer_agent", END)

    # 编译流程图，传入断点持久化对象（可选），返回可调用的完整对话图实例
    return graph.compile(checkpointer=checkpointer)

# 给单题脚本和批量评估使用。每次 invoke 都是独立状态。
workflow = build_graph()

# 只允许反序列化本项目明确声明的 Pydantic 类型，兼容 LangGraph 严格模式。
checkpoint_serde = JsonPlusSerializer(
    allowed_msgpack_modules=[
        ("app.schemas", "Citation"),
        ("app.schemas", "ResearchAnswer"),
        ("app.schemas", "RouteDecision"),
        ("app.schemas", "SupervisorDecision"),
    ]
)

# 读取配置文件中定义的会话数据库文件路径，转为Path路径对象方便路径操作
checkpoint_path = Path(settings.checkpoint_db_path)
# 判断读取到的数据库路径是否不是绝对路径（相对路径）
if not checkpoint_path.is_absolute():
    # 如果是相对路径，拼接项目根目录，生成完整绝对路径
    checkpoint_path = PROJECT_ROOT / checkpoint_path
# 获取数据库文件所在的文件夹目录；不存在则递归创建所有层级父目录，已存在也不会报错
checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

# 建立SQLite数据库连接，传入数据库文件绝对路径字符串
checkpoint_connection = sqlite3.connect(
    str(checkpoint_path),
    # 关闭多线程线程校验，适配FastAPI/Streamlit多线程并发访问会话库场景
    check_same_thread=False,
)
# 注册程序退出钩子：程序正常关闭时自动执行数据库close，释放文件锁、关闭连接
atexit.register(checkpoint_connection.close)

# 注释说明：沿用旧变量名memory_store，上层api.py、streamlit页面代码无需修改任何导入逻辑，平滑切换持久化存储
# 使用SQLite持久化存储器替代之前内存临时存储，传入数据库连接与自定义序列化器
memory_store = SqliteSaver(
    checkpoint_connection,
    serde=checkpoint_serde,
)
# 构建带SQLite持久会话记忆的完整Agent流程图，所有对话状态会落地保存到sqlite文件
memory_workflow = build_graph(checkpointer=memory_store)

# 流式接口专用的异步记忆图：与 memory_workflow 共享同一个 checkpoint 文件和序列化器，
# 所以流式/非流式接口读写的是同一份会话记忆；区别只是 checkpointer 换成支持 async 的 AsyncSqliteSaver。
# 必须懒初始化：AsyncSqliteSaver 构造时绑定当前事件循环（asyncio.get_running_loop），
# 模块导入时尚无运行中的循环，只能推迟到第一次有请求到来时再建。
_async_memory_workflow = None


async def get_async_memory_workflow():
    """获取（首次调用时创建）挂 AsyncSqliteSaver 的流程图实例，供 SSE 流式接口使用"""
    global _async_memory_workflow
    if _async_memory_workflow is None:
        # aiosqlite 连接建立在当前事件循环上；表结构由 SqliteSaver 首次使用时已建好，
        # AsyncSqliteSaver 内部的 setup() 也是 CREATE TABLE IF NOT EXISTS，幂等可重入
        conn = await aiosqlite.connect(str(checkpoint_path))
        saver = AsyncSqliteSaver(conn, serde=checkpoint_serde)
        _async_memory_workflow = build_graph(checkpointer=saver)
    return _async_memory_workflow
