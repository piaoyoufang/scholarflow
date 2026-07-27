from pathlib import Path
import textwrap

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

course_md = """# ScholarFlow 课程资料：从 0 到 1 搭建 Qwen RAG Agent

## RAG
RAG 的全称是 Retrieval-Augmented Generation，也就是检索增强生成。它的核心概念是：先从资料库中检索相关证据，再让模型基于证据生成答案。RAG 的作用是让回答更加可追溯，并减少幻觉。

## LangGraph
LangGraph 用来把 Agent 拆成状态图。状态图里有状态、节点和边。状态保存 question、documents、answer 等数据；节点负责执行具体任务；边决定执行顺序。

## 向量数据库和 Embedding
Embedding 模型负责把文本转成向量。向量数据库负责保存文本片段的向量表示，并根据相似度找出最相关的内容。

## 文档切块和 Top-K
文档切块是为了让检索更准确。Top-K 表示检索时返回最相关的前 K 个文档片段。K 太小可能漏掉证据，K 太大可能引入噪声。

## 引用
引用 citation 能告诉用户答案来自哪份资料。它让回答可追溯、可检查，也能帮助发现模型是否在无证据回答。

## FastAPI 和 Streamlit
FastAPI 负责提供 Web API，例如 POST /ask。Streamlit 负责提供简单页面，让用户输入问题并展示答案和引用。

## 评估
先做评估是为了建立基线。没有基线时，你不知道修改 Prompt、Top-K、模型或加入 MCP 后效果是变好还是变差。

## MCP
本地 RAG 稳定后再加入 MCP。第一类工具建议做只读搜索工具，例如 search_web(query, top_k)。涉及写操作时，应该暂停并等待人工确认。
"""

rag_txt = """RAG 补充笔记

RAG 由检索和生成两部分组成。检索阶段根据用户问题从知识库中找证据，生成阶段根据证据组织答案。

文档切块会影响召回效果。chunk_size 太大，片段可能包含太多无关内容；chunk_size 太小，片段可能缺少上下文。

Top-K 是一个需要实验的参数。K 太小会漏掉证据，K 太大会引入噪声和更高 token 成本。
"""

# utf-8-sig 会在文件开头写入 UTF-8 BOM。Python 和 LangChain 都能正常读取，
# Windows 编辑器也更容易自动识别为 UTF-8，避免中文被错误编码。
(RAW_DIR / "course.md").write_text(course_md, encoding="utf-8-sig")
(RAW_DIR / "rag_notes.txt").write_text(rag_txt, encoding="utf-8-sig")

# 将本机中文字体嵌入 PDF，避免阅读器找不到 CID 字体时把中文显示为问号。
font_path = Path(r"C:\Windows\Fonts\simhei.ttf")
if not font_path.exists():
    raise FileNotFoundError(f"没有找到中文字体：{font_path}")
pdfmetrics.registerFont(TTFont("SimHei", str(font_path)))
pdf_path = RAW_DIR / "mcp_notes.pdf"
c = canvas.Canvas(str(pdf_path), pagesize=A4)
width, height = A4
c.setTitle("MCP 工具补充资料")
c.setFont("SimHei", 14)
c.drawString(50, height - 50, "MCP 工具补充资料")
text = c.beginText(50, height - 85)
text.setFont("SimHei", 11)
text.setLeading(18)
lines = [
    "MCP 可以理解为 Agent 调用外部工具的一种标准协议。",
    "在 ScholarFlow 中，不要一开始就加入复杂 MCP，而是先让本地 RAG 稳定。",
    "第一类 MCP 工具建议做只读搜索，例如 search_web(query, top_k)。",
    "只读搜索工具只返回外部资料，不直接修改文件、不发送邮件、不提交数据。",
    "如果以后加入写操作工具，LangGraph 中应该暂停并等待人工确认。",
]
for line in lines:
    for wrapped in textwrap.wrap(line, width=42):
        text.textLine(wrapped)
c.drawText(text)
c.save()

print("已生成练习资料：")
print(RAW_DIR / "course.md")
print(RAW_DIR / "rag_notes.txt")
print(RAW_DIR / "mcp_notes.pdf")
