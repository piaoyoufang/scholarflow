# 新建第二个工具的独立测试脚本
import asyncio
from app.mcp_tools.client import call_tool_via_mcp, list_mcp_tools


async def main() -> None:
    tools = await list_mcp_tools()
    print("发现的工具：", tools)

    expected_tools = {
        "search_local_knowledge",
        "search_evaluation_report",
    }
    missing_tools = expected_tools - set(tools)
    if missing_tools:
        raise SystemExit(f"缺少 MCP 工具：{sorted(missing_tools)}")

    results = await call_tool_via_mcp(
        tool_name="search_evaluation_report",
        query="MCP 专项评估有哪些失败题？",
        top_k=5,
    )

    print("报告工具返回：")
    for item in results:
        print(f"- {item['title']}：{item['content'][:200]}")


if __name__ == "__main__":
    asyncio.run(main())