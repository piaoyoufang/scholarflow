# ScholarFlow 课程资料：从 0 到 1 搭建 Qwen RAG Agent

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
