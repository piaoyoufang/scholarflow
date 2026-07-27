# 批量运行 20 个问题，并生成 CSV 报告
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from app.evaluation.metrics import score_case
from app.graph.builder import workflow


PROJECT_ROOT = Path(__file__).resolve().parents[1] # 自动找到项目根目录。不管你在哪个文件夹运行这个脚本，它都能精准定位到 app 文件夹的同级目录。
DEFAULT_EVAL_FILE = PROJECT_ROOT / "data" / "eval" / "questions.jsonl" # 这是你存放学术测试问题的地方。
DEFAULT_REPORT_FILE = PROJECT_ROOT / "reports" / "eval_report.csv" # 评估结果会自动生成在这里。

# 读取学术问题集
def load_cases(path: Path) -> list[dict]:
    cases: list[dict] = [] # 初始化问题列表。准备一个空容器，用来存放所有读取到的学术问题。
    with path.open("r", encoding="utf-8-sig") as f: # 安全打开试卷。以 UTF-8 编码读取文件，确保中文题目不会乱码；with 语句保证读完后自动关闭文件。
        for line_no, line in enumerate(f, start=1): # 逐行读取并计数。enumerate 同时获取行号和内容，start=1 让行号从 1 开始，方便报错时定位。
            line = line.strip() # 清洗行数据。去除每行首尾的空格和换行符，防止 JSON 解析失败。
            if not line: # 跳过空行。忽略文件中的空行或纯空白行，避免无效数据干扰。
                continue
            try:
                cases.append(json.loads(line)) # 解析 JSON 题目。将每一行 JSON 字符串转换为 Python 字典，并加入问题列表。
            except json.JSONDecodeError as exc:
                raise SystemExit(f"第 {line_no} 行不是合法 JSON：{exc}") from exc #
    return cases

""" sys.argv[0] 是脚本文件名本身。
    sys.argv[1] 是你输入的第一个参数（试卷路径）。
    sys.argv[2] 是你输入的第二个参数（报告路径）。"""

def main() -> None:
    eval_file = Path(sys.argv[1]) if len(sys.argv) >= 2 else DEFAULT_EVAL_FILE # 灵活指定试卷。如果你在命令行传了路径就用你的，否则用默认路径。方便你同时维护多套学术测试集。
    report_file = Path(sys.argv[2]) if len(sys.argv) >= 3 else DEFAULT_REPORT_FILE # 灵活指定报告路径。同理，支持自定义输出位置，便于对比不同实验的结果。

    if not eval_file.exists(): # 检查试卷是否存在。如果文件不存在，给出明确的修复指引（复制示例文件），而不是让脚本崩溃。
        raise SystemExit(
            f"找不到评估问题文件：{eval_file}\n"
            "请先复制 data/eval/questions.example.jsonl 为 data/eval/questions.jsonl，"
            "再把里面的问题改成你自己资料里的问题。"
        )

    cases = load_cases(eval_file) # 加载问题集。调用上面的函数，把所有学术问题读入内存。
    if not cases:
        raise SystemExit(f"评估文件为空：{eval_file}")

    report_file.parent.mkdir(parents=True, exist_ok=True) # 自动创建报告目录。如果 reports 文件夹不存在，自动创建；exist_ok=True 避免目录已存在时报错。
    results = []

    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] 正在评估：{case['question']}")
        graph_result = workflow.invoke({"question": case["question"]})  # 让 AI 作答。将题目输入你的 RAG/Agent 系统，获取 AI 生成的完整回答。
        eval_result = score_case(case, graph_result["answer"])  # 执行学术评分。调用评分量表，对比 AI 回答与标准答案，计算来源命中率和关键词召回率。
        results.append(eval_result)  # 保存审稿结果。将本次评分结果存入结果列表，供后续生成报告使用。
        status = "PASS" if eval_result.passed else "FAIL" # 判定通过状态。根据评分结果，标记该题是“通过”还是“失败”。
        print(
            f"    {status} | 来源命中={eval_result.source_hit} | "
            f"关键词召回={eval_result.keyword_recall:.2f}"
        )

    with report_file.open("w", encoding="utf-8-sig", newline="") as f: # 创建报告文件。utf-8-sig 确保 Excel 打开时中文不乱码；newline="" 防止 Windows 下出现多余空行。
        writer = csv.DictWriter(   # csv.DictWriter(f, fieldnames=[...])：定义报告表头。指定 CSV 的列名和顺序，确保报告结构统一。
            f,
            fieldnames=[   #
                "passed",
                "source_hit",
                "keyword_recall",
                "question",
                "expected_sources",
                "actual_sources",
                "required_keywords",
                "answer",
            ],
        )
        writer.writeheader()  # 写入表头行。在 CSV 第一行写入列名，方便后续用 Excel 分析
        for r in results:
            writer.writerow(
                {
                    "passed": r.passed,
                    "source_hit": r.source_hit,
                    "keyword_recall": f"{r.keyword_recall:.2f}",
                    "question": r.question,
                    "expected_sources": ";".join(r.expected_sources),
                    "actual_sources": ";".join(r.actual_sources),
                    "required_keywords": ";".join(r.required_keywords),
                    "answer": r.answer,
                }
            )

    pass_count = sum(1 for r in results if r.passed) # 统计通过率。计算有多少题目通过了学术审稿，这是衡量 AI 系统学术能力的核心指标。
    print("\n评估完成")
    print(f"通过：{pass_count}/{len(results)}") # 展示最终成绩。以“通过数/总数”的格式输出整体通过率，一目了然。
    print(f"报告：{report_file}")


if __name__ == "__main__":
    main()
