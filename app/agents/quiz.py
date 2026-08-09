# 导入获取聊天大模型实例的工厂函数
from app.models import chat_model
# 导入RAG检索函数search：混合检索，支持course_id过滤课程知识库
from app.retrieval.search import search
# 导入Pydantic结构化输出模型，约束大模型输出测验题的JSON格式
from app.schemas import QuizResponse


# 系统提示词，给大模型设定角色、出题业务规则
SYSTEM_PROMPT = """
你是一个课程出题助手。
你必须基于课程资料出题，不能编造资料外的知识。
每道题必须包含题目、答案、解析和引用来源。
如果是选择题，需要给出选项。
"""


def generate_quiz(
    course_id: str,         # 课程ID，检索时用来隔离知识库，只读取该课程的文档
    topic: str,             # 出题主题，以此作为检索query
    question_count: int,    # 需要生成的题目总数量
    question_type: str,     # 题型：single_choice / true_false / short_answer / interview
    difficulty: str,        # 题目难度：easy / medium / hard
) -> QuizResponse:
    """
    RAG出题业务函数：基于课程知识库资料，调用大模型生成结构化测验题目
    :return: QuizResponse Pydantic对象，包含整套题目
    """
    # RAG检索：以主题作为查询，只检索当前course_id课程知识库，召回8条相关文档块
    docs = search(query=topic, course_id=course_id, k=8)

    # 列表推导遍历检索结果，取出每一个Document的文本；_score代表忽略相关性分数
    # 使用双换行把多条文档片段拼接成一大段参考上下文，传给大模型
    context = "\n\n".join([doc.page_content for doc, _score in docs])

    # 获取大模型实例，开启结构化输出，强制把LLM输出解析校验为QuizResponse模型
    model = chat_model().with_structured_output(QuizResponse)

    # 调用大模型，组装system+human消息列表执行推理
    return model.invoke(
        [
            # system角色：传入出题规则prompt
            ("system", SYSTEM_PROMPT),
            # human角色：把检索到的课程资料、出题全部参数一起传给大模型
            (
                "human",
                f"课程资料：\n{context}\n\n主题：{topic}\n题目数量：{question_count}\n题型：{question_type}\n难度：{difficulty}",
            ),
        ]
    )