# 用于评估 AI 回答质量的自动化测试工具。它通过对比 AI 生成的答案与预设的“标准答案”，从引用来源准确性和关键词覆盖率两个维度进行打分，最后返回一个包含详细评估结果的对象。
from __future__ import annotations
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

"""
作用：定义了一个名为 EvalResult 的数据类，用来封装一次评估的所有结果。
字段含义：
question: 原始问题。
answer: AI 生成的实际回答文本。
expected_sources: 期望引用的文献 ID 列表（标准答案）。
actual_sources: AI 实际引用的文献 ID 列表。
required_keywords: 必须包含的关键词列表。
source_hit: 布尔值，表示是否引用了正确的文献。
keyword_recall: 浮点数，表示关键词的召回率（命中数/总数）。
passed: 布尔值，表示该次回答是否通过了整体测试。"""
@dataclass
class EvalResult:
    question: str
    answer: str
    expected_sources: list[str]
    actual_sources: list[str]
    required_keywords: list[str]
    source_hit: bool
    keyword_recall: float
    passed: bool

# 清洗文本以便进行模糊匹配。
def _normalize_text(text: str) -> str:
    return (text or "").lower().replace(" ", "")

# 兼容不同格式的输入对象，提取其中的文本内容。
def extract_answer_text(answer_obj: Any) -> str:
    """兼容 Pydantic 对象和 dict。"""
    if hasattr(answer_obj, "answer"): # 优先检查是否是对象且有 .answer 属性（如 Pydantic 模型或 Dataclass）。
        return answer_obj.answer
    if isinstance(answer_obj, dict): # 其次检查是否是字典，尝试获取 "answer" 键的值。
        return str(answer_obj.get("answer", ""))
    return str(answer_obj) # 最后兜底，直接将整个对象转为字符串。

# 从复杂的回答对象中提取出所有的文献 ID。
def extract_sources(answer_obj: Any) -> list[str]:
    """从 ResearchAnswer.citations 中提取 source_id/source_name。"""
    citations = []
    if hasattr(answer_obj, "citations"):
        citations = answer_obj.citations or []
    elif isinstance(answer_obj, dict):
        citations = answer_obj.get("citations", []) or []

    sources: list[str] = []
    for citation in citations:
        if hasattr(citation, "source_id"):
            sources.append(str(citation.source_id))
        elif isinstance(citation, dict):
            value = citation.get("source_id") or citation.get("source_name")
            if value:
                sources.append(str(value))
    return sources


def _source_aliases(source: str) -> set[str]:
    """兼容 source_id、文件名以及带章节后缀的引用格式。"""
    value = str(source).strip()
    base = value.split("#", 1)[0]
    aliases = {value, base}
    if PurePath(base).suffix:
        aliases.add(PurePath(base).stem)
    return {item.lower() for item in aliases if item}

# 这是主入口函数，接收“测试用例”和“AI 回答”，输出评估结果。
def score_case(case: dict[str, Any], answer_obj: Any) -> EvalResult:
    # --- A. 准备标准答案 ---
    question = str(case["question"])

    # 确保列表里的元素都是字符串，防止混入数字导致比对失败
    expected_sources = [str(x) for x in case.get("expected_sources", [])]
    required_keywords = [str(x) for x in case.get("required_keywords", [])]

    # --- B. 提取 AI 的实际表现 ---
    answer_text = extract_answer_text(answer_obj)
    actual_sources = extract_sources(answer_obj)

    # --- C. 维度1：来源准确性打分 (Source Hit) ---
    if expected_sources:
        expected_aliases = set().union(*(_source_aliases(src) for src in expected_sources))
        actual_aliases = set().union(*(_source_aliases(src) for src in actual_sources)) if actual_sources else set()
        source_hit = bool(expected_aliases & actual_aliases)
    else:
        source_hit = True # 如果题目没要求引用，那这一项默认满分

    # --- D. 维度2：内容完整性打分 (Keyword Recall) ---
    normalized_answer = _normalize_text(answer_text)  # 先把 AI 回答洗一遍
    if required_keywords:
        hit_count = sum(1 for kw in required_keywords if _normalize_text(kw) in normalized_answer) # 计算有多少个“关键词”出现在了“回答”中。
        keyword_recall = hit_count / len(required_keywords) # 召回率 = 命中的词数 / 总词数
    else:
        keyword_recall = 1.0 # 没要求关键词，默认满分

    # --- E. 综合判定 (Passed?) ---
    # 只有“来源对了” 且 “关键词覆盖率达标” 才算通过
    # float(...) 是为了防止配置文件里写的是字符串 "0.6"
    passed = source_hit and keyword_recall >= float(case.get("min_keyword_recall", 0.6))

    return EvalResult(
        question=question,
        answer=answer_text,
        expected_sources=expected_sources,
        actual_sources=actual_sources,
        required_keywords=required_keywords,
        source_hit=source_hit,
        keyword_recall=keyword_recall,
        passed=passed,
    )
