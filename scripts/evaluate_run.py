"""评估运行器：跑黄金数据集，输出带参数快照的 JSON 报告
与旧 evaluate.py 的区别：
1. 报告头部记录检索/模型参数快照——没有快照的两份报告不可比
2. 输出 JSON（机器可对比），供 evaluate_compare.py 做回归对比
3. 增加拒答正确率指标（教育场景安全底线）
运行：python -m scripts.evaluate_run [数据集路径] [报告输出路径]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings                     # 读取当前模型与检索配置，写入报告快照
from app.evaluation.judge import judge_answer        # 已有：LLM-as-judge 百分制五维打分
from app.evaluation.metrics import extract_answer_text, extract_sources, score_case  # 已有：来源命中 + 关键词召回
from app.graph.builder import workflow               # 无记忆版图实例：每题独立状态，互不污染

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_FILE = PROJECT_ROOT / "data" / "eval" / "questions.jsonl"


def config_snapshot() -> dict:
    """记录本次评估运行时的关键参数——对比报告时先核对快照，快照不同则指标差异不可归因"""
    return {
        "chat_model": settings.chat_model,
        "fast_model": settings.fast_model,
        "embedding_model": settings.embedding_model,
        "rerank_model": settings.rerank_model,
        "vector_backend": settings.vector_backend,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }


def detect_refusal(answer_obj) -> bool:
    """判断系统是否拒答。
    优先信号：ResearchAnswer.missing_information 非空（模型主动声明缺资料）；
    兜底信号：答案文本包含拒答话术关键词（防止模型没填 missing_information 但话术上拒答了）"""
    missing = getattr(answer_obj, "missing_information", None) or []
    if missing:
        return True
    answer_text = extract_answer_text(answer_obj)
    markers = ("未提及", "无法回答", "没有相关信息", "资料中没有", "无法从")
    return any(m in answer_text for m in markers)


def main() -> None:
    eval_file = Path(sys.argv[1]) if len(sys.argv) >= 2 else DEFAULT_EVAL_FILE
    report_file = (
        Path(sys.argv[2]) if len(sys.argv) >= 3
        else PROJECT_ROOT / "reports" / f"eval_run_{datetime.now():%Y%m%d_%H%M%S}.json"
    )

    cases = [json.loads(line) for line in eval_file.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not cases:
        raise SystemExit(f"评估文件为空：{eval_file}")
    results = []

    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['question']}", flush=True)
        graph_result = workflow.invoke({"question": case["question"]})
        answer_obj = graph_result.get("answer")
        answer_text = extract_answer_text(answer_obj)

        # 复用已有评分：source_hit（期望来源是否被引用）/ keyword_recall（关键词覆盖度）
        scored = score_case(case, answer_obj)

        # LLM-as-judge 的上下文取检索召回的原始片段，而不是答案自带引用：
        # 评判的是「答案是否忠于检索到的资料」，这是 RAG 忠实度的正确定义
        contexts = [doc.page_content for doc in graph_result.get("documents") or []]
        judged = None
        try:
            judged = judge_answer(case["question"], contexts, answer_text)
        except Exception as exc:  # judge 失败不拖垮整轮评估，该题生成层指标记空
            print(f"    judge 失败：{exc}")

        refused = detect_refusal(answer_obj)
        should_refuse = bool(case.get("should_refuse", False))
        results.append({
            "question": case["question"],
            "source_hit": scored.source_hit,
            "keyword_recall": round(scored.keyword_recall, 3),
            "actual_sources": extract_sources(answer_obj),
            # judge 五维百分制；judge 失败时记 None，汇总时跳过
            "faithfulness": judged.faithfulness if judged else None,
            "citation_quality": judged.citation_quality if judged else None,
            "pass_result": judged.pass_result if judged else None,
            "should_refuse": should_refuse,
            "refused": refused,
            # 拒答正确 = 该拒的拒了，或不该拒的没拒
            "refusal_correct": refused == should_refuse,
        })
        print(
            f"    来源命中={scored.source_hit} 关键词召回={scored.keyword_recall:.2f} "
            f"忠实度={judged.faithfulness if judged else '-'} 拒答={refused}(应为{should_refuse})",
            flush=True,
        )

    n = len(results)
    judged_results = [r for r in results if r["faithfulness"] is not None]

    def avg(key: str, pool: list[dict]) -> float:
        return round(sum(r[key] for r in pool) / len(pool), 3) if pool else 0.0

    report = {
        "snapshot": config_snapshot(),
        "metrics": {
            "source_hit_rate": round(sum(r["source_hit"] for r in results) / n, 3),
            "avg_keyword_recall": avg("keyword_recall", results),
            "avg_faithfulness": avg("faithfulness", judged_results),
            "avg_citation_quality": avg("citation_quality", judged_results),
            "refusal_accuracy": round(sum(r["refusal_correct"] for r in results) / n, 3),
            "judge_coverage": round(len(judged_results) / n, 3),  # judge 成功率，太低说明 judge 本身不稳定
        },
        "cases": results,  # 逐题明细留给 compare 做下钻
    }
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告：{report_file}")
    for k, v in report["metrics"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
