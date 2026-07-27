# 自动化评估结果统计工具，专门读取两份评估 CSV 报表：通用评估报表、MCP 工具专项评估报表，自动计算通过率、打印所有失败用例的详细信息，快速定位路由 / 工具调用错误。
import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = [
    ROOT / "reports" / "eval_report.csv", #
    ROOT / "reports" / "mcp_eval_report.csv", #
]

# CSV 文件里passed列存储的是文本字符串（true/false、1/0、是/否），无法直接用bool()判断，封装统一转换逻辑，用来判断测试用例是否通过。
def read_bool(value: str) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "是"}


def analyze_report(path: Path) -> None:
    print("=" * 80)
    print(f"报告：{path}")

    if not path.exists():
        print("状态：报告不存在，先运行对应评估脚本。")
        return

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("状态：报告为空。")
        return

    failed = [row for row in rows if not read_bool(row.get("passed", ""))]
    total = len(rows) # 总测试用例条数
    passed = total - len(failed) # 通过条数 = 总条数 - 失败条数

    print(f"通过率：{passed}/{total}")

    if not failed:
        print("失败题：无")
        return

    # 循环打印每一条失败用例完整信息
    print("失败题：")
    for row in failed:
        print("-" * 80)
        print("id:", row.get("id", ""))
        print("question:", row.get("question", ""))
        print("expected_tool:", row.get("expected_tool", ""))
        print("actual_tool:", row.get("actual_tool", ""))
        print("tool_pass:", row.get("tool_pass", ""))
        print("keyword_pass:", row.get("keyword_pass", ""))
        print("answer:", row.get("answer", "")[:500])


def main() -> None:
    for report in REPORTS:
        analyze_report(report) # 遍历全局定义的两份 csv 报表路径，依次调用分析函数，一次性打印两份报告的统计结果，不用手动分别分析。


if __name__ == "__main__":
    main()