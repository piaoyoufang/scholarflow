import sys

from app.graph.builder import workflow


if len(sys.argv) != 2:
    raise SystemExit('用法: python -m scripts.ask "你的问题"')

result = workflow.invoke({"question": sys.argv[1]})
print(result["answer"].model_dump_json(indent=2, ensure_ascii=False))
