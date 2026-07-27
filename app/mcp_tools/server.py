import json

from mcp.server.fastmcp import FastMCP

from app.mcp_tools.local_search import search_local_knowledge as local_search

from app.mcp_tools.report_reader import search_evaluation_report as report_search


mcp = FastMCP("scholarflow-tools") #创建名为 `scholarflow-tools` 的 MCP Server。


@mcp.tool(name="search_local_knowledge") # 把下面的 Python 函数注册为 MCP 工具。
def search_local_knowledge_tool(query: str, top_k: int = 3) -> str:
    """搜索 ScholarFlow 的本地补充知识，只读取数据，不修改任何文件。"""
    results = local_search(query=query, top_k=top_k)
    return json.dumps(results, ensure_ascii=False) # 使用 JSON 返回结构化结果，并保留中文。

@mcp.tool(name="search_evaluation_report")
def search_evaluation_report_tool(query: str, top_k: int = 5) -> str:
    """查询 ScholarFlow 评估通过率和失败题，只读取 CSV 报告。"""
    results = report_search(query=query, top_k=top_k)
    return json.dumps(results, ensure_ascii=False)

if __name__ == "__main__":
    mcp.run(transport="stdio") # Client 和 Server 通过标准输入输出通信