
import csv
import json
from pathlib import Path

from app.graph.builder import workflow


ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = ROOT / "data" / "eval" / "mcp_questions.jsonl"
REPORT_PATH = ROOT / "reports" / "mcp_eval_report.csv"


def load_questions() -> list[dict]:
    questions = []
    with QUESTIONS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    return questions


def tool_pass(expected_tool: str, actual_tool: str) -> bool:
    if expected_tool == "any":
        return True
    if expected_tool == "mcp":
        return actual_tool in {"mcp", "mcp_forced", "mcp_auto"}
    if expected_tool == "rag_only":
        return actual_tool == "rag_only"
    if expected_tool == "diagnosis":
        return actual_tool == "diagnosis"
    return False


def keyword_pass(answer: str, keywords: list[str]) -> bool:
    return all(keyword in answer for keyword in keywords)


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for item in load_questions():
        result = workflow.invoke({"question": item["question"]})
        answer_obj = result["answer"]
        answer_text = answer_obj.answer
        actual_tool = result.get("tool_used", "")

        ok_tool = tool_pass(item["expected_tool"], actual_tool)
        ok_keyword = keyword_pass(answer_text, item["expected_keywords"])
        passed = ok_tool and ok_keyword

        rows.append(
            {
                "id": item["id"],
                "question": item["question"],
                "expected_tool": item["expected_tool"],
                "actual_tool": actual_tool,
                "mcp_result_count": len(result.get("mcp_results", [])),
                "tool_pass": ok_tool,
                "keyword_pass": ok_keyword,
                "passed": passed,
                "answer": answer_text,
            }
        )

        print(
            f"{item['id']} | expected={item['expected_tool']} | "
            f"actual={actual_tool} | passed={passed}"
        )

    with REPORT_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    passed_count = sum(1 for row in rows if row["passed"])
    print(f"\nMCP 专项通过率：{passed_count}/{total}")
    print(f"报告路径：{REPORT_PATH}")


if __name__ == "__main__":
    main()
