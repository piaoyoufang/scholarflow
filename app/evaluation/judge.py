# 导入 Pydantic 基类与 Field 字段校验工具，用于定义结构化输出的数据模型
from pydantic import BaseModel, Field

# 导入项目真实存在的主对话模型工厂函数
from app.models import chat_model


class JudgeScore(BaseModel):
    """RAG 答案评估百分制结构化输出模型。

    注意：这里字段类型用 int，范围是 0~100。
    例如 correctness=85 表示正确性为 85%。
    不建议让模型输出 "85%" 字符串，因为字符串不方便后续统计、排序和画图。
    """

    # correctness：答案正确性，百分制 0~100；例如 85 表示 85%
    correctness: int = Field(ge=0, le=100)
    # relevance：答案与问题相关性，百分制 0~100；例如 90 表示 90%
    relevance: int = Field(ge=0, le=100)
    # faithfulness：忠实度，检测是否幻觉编造，百分制 0~100；例如 70 表示 70%
    faithfulness: int = Field(ge=0, le=100)
    # citation_quality：引用质量，看引用片段能不能支撑回答，百分制 0~100；例如 95 表示 95%
    citation_quality: int = Field(ge=0, le=100)
    # completeness：回答完整度，是否覆盖问题关键点，百分制 0~100；例如 88 表示 88%
    completeness: int = Field(ge=0, le=100)
    # pass_result：评估结果是否通过，True=合格，False=不合格
    pass_result: bool
    # reason：大模型输出的打分理由，说明各个维度为什么给这个百分比
    reason: str


# 评估任务的系统提示词，给大模型设定评估员角色、评分规则、输出要求
JUDGE_PROMPT = """
你是一个严格的 RAG 系统评估员。
请根据用户问题、检索上下文、系统答案进行评分。

评分维度全部使用百分制 0-100 分：
1. correctness：答案是否正确回答问题，0-100分，例如 85 表示 85%。
2. relevance：答案是否紧扣问题，0-100分，例如 90 表示 90%。
3. faithfulness：答案是否忠实于上下文，是否有编造，0-100分，例如 70 表示 70%。
4. citation_quality：引用是否能支撑答案，0-100分，例如 95 表示 95%。
5. completeness：答案是否完整，0-100分，例如 80 表示 80%。

评分规则：
- 请输出整数，不要输出字符串，不要带百分号。例如输出 85，而不是 "85%"。
- 80 分及以上表示质量较好。
- 60-79 分表示基本可用但仍需优化。
- 60 分以下表示质量较差。
- 如果答案没有上下文依据却编造内容，faithfulness 必须低于 60。
- 如果引用不能支撑答案，citation_quality 必须低于 60。
- 如果 correctness、faithfulness 或 citation_quality 任一关键维度低于 60，pass_result 应为 false。

请只输出符合结构化模型的 JSON。
"""


def judge_answer(question: str, contexts: list[str], answer: str) -> JudgeScore:
    """
    RAG 自动评估函数：调用大模型，对 RAG 输出答案做百分制多维度打分。
    :param question: 用户原始提问
    :param contexts: RAG 检索拿到的上下文片段列表
    :param answer: RAG 系统生成的回答文本
    :return: JudgeScore，包含5项百分制分数、是否通过、打分理由
    """
    # 获取 chat 模型实例，并开启结构化输出，强制把 LLM 输出解析为 JudgeScore
    model = chat_model().with_structured_output(JudgeScore)

    # 将上下文片段列表用两行换行拼接，变成完整字符串给大模型阅读
    context_text = "\n\n".join(contexts)

    # 调用大模型执行评估，传入 system + human 对话消息
    return model.invoke(
        [
            ("system", JUDGE_PROMPT),
            (
                "human",
                f"用户问题：\n{question}\n\n检索上下文：\n{context_text}\n\n系统答案：\n{answer}",
            ),
        ]
    )
