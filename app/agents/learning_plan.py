# 学习计划 Agent 的关键不是直接让模型编计划，而是先检索课程资料；
# 导入获取快速大模型实例的工厂函数，学习计划对实时性要求高，优先使用轻量模型
from app.models import fast_model
# 导入RAG检索入口函数search，支持按course_id过滤课程知识库
from app.retrieval.search import search
# 导入Pydantic响应模型，约束大模型输出学习计划的JSON结构
from app.schemas import LearningPlanResponse


# 系统提示词：设定角色、业务规则、输出约束
SYSTEM_PROMPT = """
你是一个课程学习规划助手。
你必须根据课程资料生成学习计划，不能脱离资料泛泛而谈。
每天计划要包含：学习主题、学习任务、预期产出、引用来源。
如果资料不足，要明确说明缺少哪些资料。
"""


def generate_learning_plan(
    course_id: str,        # 课程ID，检索时用来隔离知识库，只取本课程文档
    goal: str,             # 用户的学习目标
    days: int,             # 计划总天数
    difficulty: str,       # 难度等级：beginner / intermediate / advanced
    daily_minutes: int,    # 每日建议学习分钟数
) -> LearningPlanResponse:
    """
    基于课程知识库RAG检索，调用大模型生成结构化学习计划
    :return: LearningPlanResponse Pydantic结构化学习计划对象
    """
    # RAG检索：以学习目标作为query，只检索当前course_id课程知识库，召回5条相关文档块，减少大模型超时概率
    docs = search(query=goal, course_id=course_id, k=5)

    # 遍历检索结果，取出每一个Document的page_content文本，使用双换行拼接成完整参考上下文
    # _score：下划线代表丢弃相关性分数，此处不需要使用分数
    context = "\n\n".join([doc.page_content for doc, _score in docs])[:6000]

    # 获取快速模型实例，开启结构化输出，强制LLM输出解析为LearningPlanResponse模型
    model = fast_model().with_structured_output(LearningPlanResponse)

    # 调用大模型，组装system+human消息列表执行推理
    return model.invoke(
        [
            # system消息：传入角色与业务约束prompt
            ("system", SYSTEM_PROMPT),
            # human消息：把检索到的课程资料、用户全部参数组装，交给大模型生成计划
            (
                "human",
                f"课程资料：\n{context}\n\n学习目标：{goal}\n学习天数：{days}\n学习基础：{difficulty}\n每天学习时长：{daily_minutes}分钟",
            ),
        ]
    )
