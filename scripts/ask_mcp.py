from app.graph.builder import workflow


result = workflow.invoke({"question": "[MCP] MCP 的接入顺序是什么？"})

print("MCP 原始结果：")
for item in result.get("mcp_results", []):
    print(f"- {item['title']}：{item['content']}")

print("\nQwen 最终答案：")
print(result["answer"].model_dump_json(indent=2, ensure_ascii=False))