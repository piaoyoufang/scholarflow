# ScholarFlow 项目架构与完整流程

## 第一个核心概念：RAG

ScholarFlow 的第一个核心概念是 RAG，也就是检索增强生成。
RAG 的定义是：先从知识库检索相关证据，再让模型基于证据生成回答。
它的作用是让答案有来源、可追溯，并减少大模型幻觉。

## 系统的输入、流程步骤和输出

系统输入是用户问题和已经导入的 PDF、Markdown、TXT 资料。
完整流程包含以下步骤：

1. loader.py 加载原始文档并切块；
2. Embedding 模型把文本块转换成向量并写入 Chroma 向量库；
3. search.py 根据问题查询向量库，召回相关文档；
4. LangGraph 的 nodes.py 执行检索、工具路由、MCP 调用和回答节点；
5. builder.py 把节点和边组装为可执行工作流；
6. Qwen 根据召回证据生成结构化答案；
7. FastAPI 返回响应，Streamlit 展示答案和引用。

系统输出是包含 answer、citations、confidence 和 missing_information 的结构化回答。

## Agent 与普通大模型调用的区别

普通大模型调用通常只有一次输入和一次输出。Agent 除了调用模型，还能规划步骤、
调用工具并执行工作流。ScholarFlow 使用 LangGraph 控制执行顺序，使用 MCP 调用外部工具。

## FastAPI 与 Streamlit

FastAPI 负责后端接口。它接收 HTTP 请求，调用 LangGraph 工作流，再把结构化答案作为
HTTP 响应返回。Streamlit 负责用户界面，接收用户输入并展示答案、引用和错误信息。

## schemas.py 的职责

schemas.py 定义系统中的数据结构、字段和校验规则。例如 AskRequest 校验问题字段，
ResearchAnswer 约束答案、引用、置信度和缺失信息，RouteDecision 约束工具路由结果。

## config.py 的职责

config.py 集中读取和管理配置，例如模型名称、百炼地址、向量库目录和环境变量。
API Key 属于密钥，不能直接写进代码或提交到 Git，应通过 .env 环境变量读取。

## models.py 的职责

models.py 单独封装 Qwen 对话模型和 Embedding 模型。这样其他模块可以复用同一套模型
创建逻辑和配置，将来更换模型名称、超时或百炼地址时只需修改一处。

## loader.py 的职责

loader.py 负责加载 PDF、Markdown、TXT 文档，对文档切块，补充 source_id、
source_name、chunk_index 等元数据，然后向量化并入库到 Chroma。

## search.py 的职责

search.py 接收自然语言查询，访问 Chroma 向量库，根据向量相似度返回最相关文档，
供回答节点使用。它只负责查询和召回相关文档，不负责生成最终答案。

## nodes.py 与 builder.py 的职责

nodes.py 定义工作流中的节点，每个节点执行一项具体任务，例如检索、工具决策、
MCP 搜索和生成回答。builder.py 定义图的边和执行顺序，把节点组装成 LangGraph 工作流。

## 为什么先评估再加入 MCP

先评估是为了建立稳定基线。加入 MCP 后，可以把新结果和旧基线对比，判断效果是变好
还是变差。如果没有基线，资料、检索、Prompt 和工具同时变化时就无法定位原因。

## MCP 的第一类工具

第一类 MCP 工具建议使用只读搜索工具。只读工具只查询和返回数据，不修改文件、
不发送消息、不提交表单，风险更低，也更容易测试和回滚。