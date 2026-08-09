# 从评估模块导入RAG自动打分函数judge_answer，基于大模型做RAG答案多维度评估
from app.evaluation.judge import judge_answer

# 调用评估函数，执行LLM‑as‑Judge打分
score = judge_answer(
    # 用户原始提问
    question="ScholarFlow 的记忆策略是什么？",
    # RAG检索得到的参考上下文证据片段列表，评估大模型会以此作为事实依据
    contexts=["ScholarFlow 使用 memory_summary + 最近12条history + turn_count 做长期记忆。"],
    # RAG系统实际生成出来的回答，用来和上下文做对比打分
    answer="它使用 memory_summary 加最近12条历史记录，并记录 turn_count。",
)

# 打印JudgeScore结构化评估对象，输出各个维度分数、pass_result、reason打分理由
print(score)