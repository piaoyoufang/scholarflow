from app.graph.state import AgentState
from app.mcp_tools.client import call_tool_via_mcp_sync
from app.models import chat_model, fast_model
from app.retrieval.search import search
from app.schemas import QuestionRewrite, ResearchAnswer, RouteDecision
from app.resilience import run_with_retry
from app.runtime_metrics import runtime_metrics


def _answer_needs_revision(question: str, answer: str) -> bool:
    """识别明显过短或只有元叙述的复杂回答，最多触发一次重写。"""
    normalized_answer = answer.strip()
    meta_phrases = (
        "问题包含",
        "以下逐项",
        "以下回答",
        "需按规则",
        "严格依据证据回答",
    )
    complex_markers = (
        "解释",
        "为什么",
        "步骤",
        "流程",
        "分别",
        "区别",
        "影响",
        "作用",
        "顺序",
        "接入",
    )
    has_meta_narration = any(phrase in normalized_answer for phrase in meta_phrases)
    is_complex_question = any(marker in question for marker in complex_markers)
    is_too_short = is_complex_question and len(normalized_answer) < 100
    return has_meta_narration or is_too_short


def rewrite_question_node(state: AgentState) -> AgentState:
    """结合当前线程历史改写追问，并清空上一轮临时状态。"""
    # 1. 取出用户原始提问，去除首尾多余空格、换行
    question = state["question"].strip()
    # 2. 从全局状态读取对话历史，最多截取最后12条（6轮对话），避免上下文过长
    history = state.get("history", [])[-12:]

    # 3. 定义本轮全新的临时状态重置字典
    # 每一轮新提问都要清空上一轮检索、MCP、工具标记的旧数据，防止历史残留干扰本轮流程
    reset_state: AgentState = {
        "documents": [],          # 清空上一轮Chroma向量检索结果
        "mcp_results": [],        # 清空上一轮MCP知识库检索返回数据
        "mcp_error": "",          # 清空上一轮MCP调用报错信息
        "selected_tool": "",      # 清空上一轮AI决策选定的工具名称
        "tool_used": "",          # 清空上一轮实际运行的工具标识
        "agent_trace": [], # 初始化Agent执行链路追踪数组，空列表代表当前对话轮次还未运行任何智能体
        "degraded": False,  # 流程降级总标记，默认False代表本轮问答未触发任何降级兜底逻辑
        "degradation_reasons": [], # 降级原因存储列表，默认空数组，出现降级时会存入对应的异常/兜底说明文本
    }

    # 4. 分支判断：无对话历史（首轮提问），无需改写问题，直接使用原问题作为检索问句
    if not history:
        # **reset_state 解包重置字段，同时赋值检索专用问句为原始问题，返回更新后的状态
        return {**reset_state, "retrieval_question": question}

    # 5. 遍历历史消息列表，拼接成人类可读的对话文本，传入大模型作为上下文参考
    history_text = "\n".join(
        # 单条对话格式：角色: 对话内容（区分user用户/assistant模型）
        f"{item['role']}: {item['content']}"
        for item in history
    )

    # 6. 组装问题改写专用提示词，明确模型任务、约束规则、输入上下文与用户新提问
    prompt = f"""你负责把多轮追问改写成可以独立检索的问题，不要回答问题。

规则：
- 只有“它、这个、前者、后者、那一步”等依赖历史的表达才补全上下文。
- 已经完整的问题保持原意，不要擅自增加新需求。
- standalone_question 必须是一句可以脱离聊天历史理解的问题。
- used_history 表示改写是否实际依赖历史。

最近对话：
{history_text}

当前问题：
{question}
"""

    try:
        # 调用同步重试工具执行问题改写模型推理，自动重试并采集监控指标
        rewritten = run_with_retry(
            # 匿名lambda封装完整的轻量模型结构化调用逻辑
            lambda: (
                # 获取高速轻量大模型实例
                fast_model()
                # 约束模型输出为QuestionRewrite结构化格式，防止自由文本乱输出
                .with_structured_output(QuestionRewrite)
                # 传入改写提示词，执行推理生成优化后的检索问题
                .invoke(prompt)
            ),
            # 标记当前组件标识，runtime_metrics会按该名称分类统计性能指标
            component="model.question_rewrite",
        )
        # 8. 重置所有临时状态，将模型改写后的无歧义独立问句存入检索专用字段retrieval_question，返回状态流转至下一个节点
        return {
            **reset_state,
            "retrieval_question": rewritten.standalone_question,
        }
    except Exception:
        # 指标埋点：记录问题改写模型触发降级兜底事件，用于监控统计改写模型异常次数
        runtime_metrics.record_fallback("model.question_rewrite")
        # 返回更新后的全局对话状态字典
        return {
            # 合并前置重置后的基础状态数据
            **reset_state,
            # 放弃改写后的优化query，直接使用用户原始提问作为检索查询词
            "retrieval_question": question,
            # 标记本轮流程触发降级，日志/监控可快速筛选异常链路
            "degraded": True,
            # 记录本次降级的具体原因，便于故障排查定位
            "degradation_reasons": ["问题改写失败，使用原始问题检索"],
        }


def retrieve_node(state: AgentState) -> AgentState:
    # 读取用于检索的标准问句：优先使用经过历史改写的独立检索问句
    # 若状态中不存在改写后的retrieval_question（首轮对话/改写异常），则降级使用用户原始question
    query = state.get("retrieval_question", state["question"])

    # 调用Chroma向量库检索函数search，传入处理完成的检索问句
    # k=6：从向量库中召回匹配度最高的6条文档分片
    # 返回值pairs格式为列表：[(Document文档对象, 相似度匹配分数), (Document, 分数), ...]
    pairs = search(query, k=6)
    return {"documents": [doc for doc, _score in pairs]}


def decide_tool_node(state: AgentState) -> AgentState:
    # 从全局状态取出用户最原始的输入提问，清除首尾多余空格、换行符，存为原始问题变量
    original_question = state["question"].strip()

    # 优先读取经过历史上下文改写后的独立检索问句；
    # 如果状态里不存在改写后的检索问句（首轮对话、改写节点异常），就降级使用清洗后的原始问题；
    # 最后再次去除首尾空白字符，得到统一标准检索问句
    question = state.get("retrieval_question", original_question).strip()

    if original_question.startswith("[MCP]"):
        query = original_question.removeprefix("[MCP]").strip()
        decision = RouteDecision(
            use_mcp=True,
            tool_name="search_local_knowledge",
            query=query or question,
            reason="用户使用 [MCP] 前缀，强制调用本地知识工具。",
        )
        return {
            "tool_decision": decision,
            "selected_tool": decision.tool_name,
            "tool_used": "mcp_forced",
        }

    retrieved_preview = "\n".join(
        f"- {doc.metadata.get('source_name')}：{doc.page_content[:120]}"
        for doc in state.get("documents", [])[:3]
    )

    prompt = f"""你是 ScholarFlow Agent 的工具路由器。
你的任务不是回答问题，而是判断是否需要调用 MCP，以及选择一个工具。

当前可用工具：
1. search_local_knowledge
   查询 MCP、Server、Client、工具接入顺序和 ScholarFlow 本地补充知识。
2. search_evaluation_report
   读取评估 CSV，查询通过率、失败题、未通过原因和最近评估结果。

判断规则：
- 问评估通过率、失败题、测试报告时，选择 search_evaluation_report。
- 问 MCP 概念、接入顺序、Server、Client 时，选择 search_local_knowledge。
- 普通 RAG、Embedding、向量数据库或资料内容问题，如果 Chroma 证据足够，
  use_mcp=false 且 tool_name=none。
- use_mcp=false 时必须选择 none。
- use_mcp=true 时必须选择一个真实工具，不能选择 none。
- 每次最多选择一个工具。

用户原始问题：
{original_question}

用于检索和路由的独立问题：
{question}

Chroma 召回摘要：
{retrieved_preview}
"""

    # 捕获工具路由模型全流程执行逻辑
    try:
        # 使用带重试机制的同步执行器，调用工具路由大模型生成结构化决策
        decision = run_with_retry(
            # lambda封装完整的大模型结构化调用逻辑
            lambda: (
                # 获取主对话大模型实例
                chat_model()
                # 约束模型输出严格匹配RouteDecision结构化数据模型
                .with_structured_output(RouteDecision)
                # 传入路由提示词，执行推理得到工具调用判断结果
                .invoke(prompt)
            ),
            # 标记当前业务组件，用于runtime_metrics分类统计监控指标
            component="model.tool_router",
        )
    # 捕获所有模型调用异常：超时、接口报错、结构化解析失败、重试耗尽等
    except Exception:
        # 监控埋点：记录工具路由模型触发降级兜底事件，统计异常次数
        runtime_metrics.record_fallback("model.tool_router")
        # 手动构造降级路由决策对象
        decision = RouteDecision(
            use_mcp=False,  # 降级关闭MCP外部工具调用，仅使用本地向量库RAG
            tool_name="none",  # 指定无外部工具
            query=question,  # 复用当前检索问题
            reason="工具路由失败，降级为纯RAG回答。",  # 记录降级事由
        )
        # 返回更新后的对话状态字典
        return {
            "tool_decision": decision,  # 写入降级生成的工具决策
            "selected_tool": "none",  # 标记本轮不使用任何MCP工具
            "tool_used": "rag_fallback",  # 标记本次走RAG降级流程，用于日志区分
            "degraded": True,  # 全局降级标记，代表本轮流程触发兜底逻辑
            "degradation_reasons": [
                # 读取原有降级记录，追加本次工具路由异常原因
                *state.get("degradation_reasons", []),
                "工具路由失败，降级为纯RAG",
            ],
        }

    # 正常分支同样必须返回状态更新；否则Knowledge Agent无法合并decision_update。
    return {
        "tool_decision": decision,
        "selected_tool": decision.tool_name,
        "tool_used": "mcp_auto" if decision.use_mcp else "rag_only",
    }

def mcp_search_node(state: AgentState) -> AgentState:
    decision = state.get("tool_decision")
    tool_name = decision.tool_name if decision else "search_local_knowledge"
    query = decision.query if decision else state["question"]

    try:
        results = call_tool_via_mcp_sync(
            tool_name=tool_name,
            query=query,
            top_k=5,
        )
        return {
            "mcp_results": results,
            "selected_tool": tool_name,
            "tool_used": "mcp",
            "mcp_error": "",
        }
    except Exception as exc:
        return {
            "mcp_results": [],
            "selected_tool": tool_name,
            "tool_used": "mcp_failed",
            "mcp_error": str(exc),
        }


def answer_node(state: AgentState) -> AgentState:
    document_evidence = "\n\n".join(
        f"来源={doc.metadata.get('source_name')}，"
        f"source_id={doc.metadata.get('source_id')}，"
        f"位置={doc.metadata.get('page', '')}\n{doc.page_content}"
        for doc in state.get("documents", [])
    )

    mcp_evidence = "\n\n".join(
        f"来源={item['source_name']}，source_id={item['source_id']}\n"
        f"{item['content']}"
        for item in state.get("mcp_results", [])
    )

    evidence = "\n\n".join(
        part for part in [document_evidence, mcp_evidence] if part
    )

    decision = state.get("tool_decision")
    tool_info = ""
    if decision:
        tool_info = (
            f"工具决策：use_mcp={decision.use_mcp}；"
            f"tool_name={decision.tool_name}；"
            f"query={decision.query}；"
            f"reason={decision.reason}；"
            f"selected_tool={state.get('selected_tool', '')}；"
            f"tool_used={state.get('tool_used', '')}；"
            f"mcp_error={state.get('mcp_error', '')}"
        )

    # 1. 读取状态中的对话历史，无历史则返回空列表；只截取最后12条（最多6轮对话），避免上下文过长
    # 2. 遍历每一条历史消息，拼接为「角色: 对话内容」格式字符串
    # 3. 使用换行符 \n 拼接所有对话条目，生成完整可读的对话上下文文本
    history_text = "\n".join(
        # 单条对话格式化：区分user用户 / assistant模型回复，拼接统一文本格式
        f"{item['role']}: {item['content']}"
        # 遍历裁剪后的历史列表，item为单条对话字典{"role":"xxx","content":"xxx"}
        for item in state.get("history", [])[-12:]
    )

    prompt = f"""你是证据优先的学习助理。只能根据证据回答，不足时明确说明。

回答完整性规则：
1. 先识别问题包含几个子问题，必须逐项回答，不能只回答第一项。
2. 询问“概念/是什么”并要求解释时，尽量覆盖名称、定义、工作方式和作用。
3. 询问“流程/步骤”时，若证据支持，要明确写出输入、编号步骤和输出。
4. 询问“为什么”时，要说明直接原因，以及它对上下文、召回、准确性等方面的影响。
5. 询问参数及“调大或调小”时，要同时说明参数定义、调大影响、调小影响和权衡。
6. 优先使用证据中的准确术语，但不要为了凑词而加入证据没有的信息。
7. 简单问题可以简洁，但不能因简洁而遗漏问题明确要求的部分。
8. 直接给出最终结论，不要复述这些规则，不要写“问题包含几个子问题”之类的分析过程。
9. 不要用“以下将回答”结束答案；写出引导语后必须继续给出完整实质内容。
10. 如果问题询问“Agent 接入外部工具时，MCP 的作用是什么”，答案里必须明确出现
    “Agent”“外部工具”“协议”三个核心词，并说明 MCP 是 Agent 接入外部工具的标准协议。

最近对话历史：
{history_text or "无"}

用户当前原始问题：
{state['question']}

用于检索的独立问题：
{state.get('retrieval_question', state['question'])}

工具状态：
{tool_info}

证据：
{evidence}

输出答案、引用、置信度和缺失信息。
引用的 source_id 必须来自证据。
如果 MCP 工具失败，但 Chroma 证据足够，可以继续根据 Chroma 回答。
"""

    structured_model = chat_model().with_structured_output(ResearchAnswer)

    # 第一次回答是核心调用，必须由统一重试器保护；重试耗尽后返回合法的结构化兜底答案。
    try:
        result = run_with_retry(
            lambda: structured_model.invoke(prompt),
            component="model.answer",
        )
    except Exception:
        runtime_metrics.record_fallback("model.answer")
        result = ResearchAnswer(
            answer="模型暂时无法生成回答，请稍后使用相同问题重试。",
            citations=[],
            confidence=0.0,
            missing_information=["Qwen回答模型本次调用失败"],
        )
        new_history = [
            {"role": "user", "content": state["question"]},
            {"role": "assistant", "content": result.answer},
        ]
        return {
            "answer": result,
            "history": new_history,
            "degraded": True,
            "degradation_reasons": [
                *state.get("degradation_reasons", []),
                "回答模型失败，返回结构化兜底答案",
            ],
        }

    if _answer_needs_revision(state["question"], result.answer):
        revision_prompt = f"""{prompt}

上一版答案：
{result.answer}

上一版答案过短或只描述了回答计划，没有完整解决问题。请重新输出完整的
ResearchAnswer。直接给出实质结论，逐项覆盖问题要求，并继续严格使用现有证据。
至少输出两句完整内容；如果问题询问 RAG 的作用，明确说明检索、证据、回答和幻觉；
如果问题询问 MCP 接入顺序，明确列出普通 Python 函数、MCP Server、MCP Client 和
LangGraph 节点的验证顺序。
"""
        # 二次修订只是质量优化；失败时保留第一次已经可用的回答。
        try:
            result = run_with_retry(
                lambda: structured_model.invoke(revision_prompt),
                component="model.answer_revision",
            )
        except Exception:
            runtime_metrics.record_fallback("model.answer_revision")


    new_history = [
        {"role": "user", "content": state["question"]},
        {"role": "assistant", "content": result.answer},
    ]
    return {"answer": result, "history": new_history}
