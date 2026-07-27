import asyncio

from app.mcp_tools.client import list_mcp_tools, search_via_mcp


async def main() -> None:
    tools = await list_mcp_tools()
    print("发现的工具：", tools)

    results = await search_via_mcp("MCP 的接入顺序是什么", top_k=2)
    print("工具返回：")
    for item in results:
        print(f"- {item['title']}：{item['content']}")


if __name__ == "__main__":
    asyncio.run(main())