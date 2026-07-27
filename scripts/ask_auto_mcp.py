from app.graph.builder import workflow


questions = [
    "MCP 的接入顺序是什么？",
    "RAG 的作用是什么？",
    "MCP Server 和 Client 分别负责什么？",
]


for question in questions:
    print("=" * 80)
    print("问题：", question)

    result = workflow.invoke({"question": question})

    decision = result.get("tool_decision")
    if decision:
        print("工具决策：", decision.model_dump())

    print("实际工具：", result.get("tool_used"))
    print("MCP 结果数量：", len(result.get("mcp_results", [])))
    print("MCP 错误：", result.get("mcp_error", ""))

    print("最终答案：")
    print(result["answer"].model_dump_json(indent=2, ensure_ascii=False))