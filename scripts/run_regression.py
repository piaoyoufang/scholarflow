"""这是一套流水线启动脚本，按顺序自动串行执行你项目里全部测试、问答、评估、报表分析脚本。
不用你手动一条一条复制命令敲终端；执行顺序：MCP 工具单元测试 → 手动 MCP 问答 → 自动路由问答 → MCP 专项评估 → 全量评估 → 分析评估报表。
任意一步脚本异常崩溃，整个流水线立刻终止。"""
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


COMMANDS = [
    ["-m", "scripts.test_mcp_tool"], # MCP 工具连通性单元测试，验证 MCP 服务能否正常拉起调用
    ["-m", "scripts.test_report_tool"], # 评估报表 MCP 工具单元测试脚本，专门用来测试你新增的 search_evaluation_report 工具能否正常工作。
    ["-m", "scripts.ask_mcp"], # 手动带[MCP]前缀模式问答测试
    ["-m", "scripts.ask_auto_mcp"], # AI 自动路由模式问答测试
    ["-m", "scripts.evaluate_mcp"], # MCP 路由专项评估，输出 mcp_eval_report.csv
    ["-m", "scripts.evaluate"], # Agent 全流程评估，输出 eval_report.csv
    ["-m", "scripts.analyze_reports"], # 读取两份 CSV 评估报表，输出通过率与失败用例
]


def run(command: list[str]) -> None:
    full_command = [sys.executable, *command]
    print("=" * 80)
    print("运行：", " ".join(full_command))

    result = subprocess.run(
        full_command, # 要执行的命令数组（subprocess 标准规范，不推荐拼接字符串防路径空格 bug）
        cwd=ROOT, # 子进程的工作目录 = 项目根目录，解决模块导入失败问题，和你手动 cd 到项目目录执行命令效果一致
        text=True, # 输出内容以字符串形式返回，而不是二进制字节
        encoding="utf-8", # 终端输出采用 utf8 编码，中文正常显示不乱码
        errors="replace", # 极端编码异常时，无法识别的字符替换成占位符，避免程序直接崩溃
    )


    if result.returncode != 0:  # result.returncode：进程退出码,0 = 脚本正常执行完毕，无异常,非 0 = 代码报错、抛出异常、执行失败
        raise SystemExit(f"命令失败：{' '.join(full_command)}")


def main() -> None:
    for command in COMMANDS:
        run(command)

    print("=" * 80)
    print("回归测试完成。请重点查看 reports 目录下的 CSV 报告。")


if __name__ == "__main__":
    main()