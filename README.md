# ScholarFlow｜AI 课程知识库与学习助手

ScholarFlow 是一个面向高校课程、职业培训和企业内训场景的 AI 课程知识库与学习助手系统。
老师可以创建课程并上传 PDF / Markdown / TXT 课程资料，系统自动构建课程知识库；学生可以基于课程资料进行带引用问答、生成学习计划和练习题；管理员和老师可以通过评估与诊断能力检查 AI 回答质量。
系统重点解决：
- 课程资料分散，人工查找效率低；
- 老师和助教重复答疑成本高；
- 普通大模型不知道课程私有资料；
- AI 回答缺少引用依据，学习场景不容易信任；
- 学生缺少系统学习路径和练习题；
- AI 助教回答质量缺少评估和诊断。

## 业务背景

真实学习场景里，课程资料往往分散在多个文件中，人工查找效率低，老师和助教也会反复回答相似问题。
普通大模型不知道课程私有资料，容易出现没有引用依据的回答。
ScholarFlow 通过 RAG、Agent 和评估闭环，把“资料管理、问答学习、质量验证”串成一个完整系统。

## 核心角色

- **admin**：管理用户、课程、评估、诊断和系统状态。
- **teacher**：创建课程、上传资料、管理知识库、查看评估报告。
- **student**：加入课程、基于资料问答、生成学习计划、自动出题。

## 核心能力

- 课程级资料上传与知识库管理
- Chroma 向量检索 + BM25 混合召回 + Rerank 精排
- 课程级问答与引用来源追踪
- 多轮对话记忆与线程隔离
- 学习计划 Agent
- 自动出题 Agent
- LLM-as-Judge 评估
- 诊断 Agent 与运行监控
- Docker Compose 部署

## 目录说明

```text
scholarflow/
├─ app/          # 后端核心代码
├─ data/         # SQLite、向量库、上传文件、记忆数据
├─ docs/         # 验收记录和开发文档
├─ scripts/      # 命令行测试与验收脚本
├─ tests/        # 自动化测试
├─ ui.py         # Streamlit 前端
├─ Dockerfile
└─ docker-compose.yml
```

## 开发顺序

1. 先完成课程和角色基础
2. 再做课程级知识库管理
3. 再做异步上传和任务状态
4. 再做课程级 RAG 问答
5. 再做检索可视化
6. 再做评估、学习计划和自动出题
7. 最后做监控、诊断和前端重构

## 运行方式

```powershell
cd D:\python\ai-project\scholarflow
python -m pip install -r requirements.txt
uvicorn app.api:app --reload
```

前端：

```powershell
streamlit run ui.py
```

## 当前状态

- v1.1.0 基础能力已完成并通过验收。
- 正在进行真实业务化改造，目标是把项目从 RAG Demo 升级为可用于课程学习场景的 AI 应用系统。

## 说明

本项目当前只保留子目录 README，根目录 README 不作为 ScholarFlow 主说明使用。
