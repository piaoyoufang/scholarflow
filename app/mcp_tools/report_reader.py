"""这是适配你 MCP 工具标准的检索函数！
和最开始写的 search_local_knowledge 结构完全对齐：输入查询词，
返回统一格式字典列表（title/content/source_id/source_name/score），
可以直接封装成 MCP 工具，让 Agent检索两份评估 CSV 报告。"""
import csv
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_FILES = {
    "通用评估": ROOT / "reports" / "eval_report.csv",
    "MCP 专项评估": ROOT / "reports" / "mcp_eval_report.csv",
}


def _read_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "是"}


def search_evaluation_report(
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """只读查询 CSV 评估报告，不修改报告文件。"""
    query = query.strip()
    if not query:
        raise ValueError("query 不能为空")
    if not 1 <= top_k <= 20:
        raise ValueError("top_k 必须在 1 到 20 之间")

    normalized = query.lower()
    # 把查询转小写，检测用户是否想要只查看失败的测试用例
    wants_failed = any(word in normalized for word in ["失败", "未通过", "问题", "错误"])

    if "mcp" in normalized:
        selected_reports = {"MCP 专项评估": REPORT_FILES["MCP 专项评估"]} # 查询包含mcp → 只读取 MCP 专项评估
    elif any(word in normalized for word in ["通用", "rag", "20题", "20 题"]):
        selected_reports = {"通用评估": REPORT_FILES["通用评估"]} # 查询包含通用/rag/20题 → 只读取通用评估
    else:
        selected_reports = REPORT_FILES # 其他情况：两份报表全部读取

    results: list[dict[str, Any]] = []

    for report_name, path in selected_reports.items():
        if not path.exists():
            results.append(
                {
                    "title": f"{report_name}尚未生成",
                    "content": f"报告文件不存在：{path}。请先运行对应评估脚本。",
                    "source_id": path.stem,
                    "source_name": path.name,
                    "score": 1,
                }
            )
            continue

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))

        # 筛选失败用例，统计通过数量。
        failed_rows = [row for row in rows if not _read_bool(row.get("passed", ""))]
        passed_count = len(rows) - len(failed_rows)

        results.append(
            {
                "title": f"{report_name}汇总",
                "content": (
                    f"{report_name}共有 {len(rows)} 道题，通过 {passed_count} 道，"
                    f"失败 {len(failed_rows)} 道，通过率为 {passed_count}/{len(rows)}。"
                ),
                "source_id": path.stem,
                "source_name": path.name,
                "score": 10,
            }
        )

        detail_rows = failed_rows if wants_failed else rows # wants_failed为true只看失败用例，false为全部用例
        for row in detail_rows:
            question = row.get("question", "")
            answer = row.get("answer", "")
            results.append(
                {
                    "title": f"评估题 {row.get('id', '') or question[:30]}",
                    "content": (
                        f"问题：{question}\n"
                        f"是否通过：{row.get('passed', '')}\n"
                        f"预期工具：{row.get('expected_tool', '')}\n"
                        f"实际工具：{row.get('actual_tool', '')}\n"
                        f"关键词召回率：{row.get('keyword_recall', '')}\n"
                        f"答案：{answer[:500]}"
                    ),
                    "source_id": path.stem,
                    "source_name": path.name,
                    "score": 5 if not _read_bool(row.get("passed", "")) else 1,
                }
            )

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:top_k]