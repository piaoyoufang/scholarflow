# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

高校课程 AI 学习助手平台：FastAPI 后端 + Vue3 前端，核心是基于课程资料的 RAG 问答（引用溯源）、学习 Agent（学习计划/自动出题）和教师分析看板。

## 常用命令

### 启动开发环境

```powershell
docker compose up -d mysql redis                        # 依赖中间件（MySQL 宿主机端口 3307，Redis 6379）
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000   # 后端，文档见 /docs
cd vue-frontend; npm run dev                             # 前端，5173 端口
```

前端开发服务器将 `/api` 代理到 `http://127.0.0.1:8000` 并剥掉 `/api` 前缀（见 `vue-frontend/vite.config.js`），前端代码里所有请求都走 `/api` 前缀。

注意：docker-compose 里 MySQL 映射到宿主机 **3307**，而 `app/config.py` 默认 `database_url` 指向 3306——本地跑 compose 时以 `.env` 中的 `DATABASE_URL` 为准。

### 测试

```powershell
pytest tests/                                            # pytest 单元测试（检索、重排、graph、schemas）
pytest tests/test_hybrid_retrieval.py::test_bm25_prefers_exact_identifier   # 单个测试
python -m scripts.test_account_auth                      # 脚本式集成测试（scripts/test_*.py 都是这种用法，非 pytest）
python -m scripts.release_gate                           # 离线发布门禁：文件/版本校验 + compileall + 全部 scripts 测试
```

存在两套测试：`tests/` 是 pytest；`scripts/test_*.py` 是独立脚本，必须用 `python -m` 逐个跑。CI（`.github/workflows/ci.yml`）的 offline-gate 只跑 `release_gate`，不依赖外部大模型和网络。真实模型评估走 `scripts/evaluate.py`、`scripts/evaluate_mcp.py`（需要 DashScope API Key）。

### 构建与部署

```powershell
cd vue-frontend; npm run build                           # 产物在 vue-frontend/dist/（不入库）
docker compose up -d --build                             # 需先 copy .env.production.example .env.production
```

发布流程受 `scripts/release_gate.py` 约束：`VERSION` 必须是语义化版本，`CHANGELOG.md` 必须包含 `## [x.y.z]` 章节，git tag 必须与 VERSION 一致（CI 校验）。

## 架构要点

### 问答主链路（LangGraph）

`POST /courses/{id}/ask` 和 `/ask` 都汇入 `app/graph/builder.py` 编译的 LangGraph 工作流：

```
START → rewrite_question → supervisor →(条件路由)→ knowledge_agent / report_agent / diagnosis_agent → answer_agent → END
```

- `app/agents/supervisor.py` 用 LLM 判断问题走哪个分支；`app/agents/workers.py` 是各 agent 节点实现。
- `builder.py` 导出两个图实例：`workflow`（无持久化，每次独立状态）和 `memory_workflow`（挂 SQLite `SqliteSaver` checkpointer，按 `thread_id` 续接多轮会话）。改动 builder 时注意 LangGraph 严格反序列化只允许显式声明的 Pydantic 类型。
- 对话记忆（摘要 + checkpoint）存 `./data/memory/checkpoints.sqlite`。

### 检索管线

`app/retrieval/`：`hybrid.py` 是纯 Python 实现的 BM25（自写分词，英文按词、中文按字）+ 向量召回融合，`rerank.py` 调 DashScope `gte-rerank-v2` 重排，`debug.py` 输出完整中间结果供 `/retrieval/debug` 接口排障。向量库默认本地 Qdrant（`./data/qdrant_local`，`app/vectorstores/qdrant_store.py`），Chroma 为遗留路径（`vector_backend` 配置切换）。

### 存储分层（注意四种存储并存）

| 数据 | 位置 |
|---|---|
| 关系数据（课程、成员、反馈、问答事件、任务、学习历史） | MySQL，`app/storage/sql_db.py` 用 SQLAlchemy 裸 SQL，无 ORM/迁移工具 |
| 账号/Token | SQLite `./data/auth/auth.sqlite`（`app/security.py`） |
| 对话 checkpoint | SQLite `./data/memory/checkpoints.sqlite` |
| 缓存 | Redis（`app/cache.py`，`cache_ttl_seconds`） |

MySQL schema 初始化用 `python -m scripts.init_mysql_schema`；从 SQLite 迁移用 `scripts/migrate_sqlite_to_mysql.py`。

### 全局单例模式

各业务模块导出模块级单例（`course_store`、`knowledge_library`、`task_store`、`feedback_store`、`qa_event_store`、`auth_store`、`runtime_metrics`），`app/api.py` 直接 import 使用。新增存储能力时遵循同一模式，不要引入 DI 容器。

### 异步文档入库

`/courses/{id}/documents/upload-async` → 写入 `task_store` → FastAPI `BackgroundTasks` 跑 `app/tasks/ingestion.py`（解析 PDF/MD/TXT、切块、向量化入库）→ 前端轮询 `/tasks/{task_id}`。这是 FastAPI 进程内后台任务，不是独立 worker，重启会中断任务。

### MCP 工具

`app/mcp_tools/`（server/client/local_search/report_reader）为 agent 提供课程资料检索和评估报表读取能力；`report_agent` 跳过向量检索只走 MCP 报表查询。

### LLM 接入

统一走阿里云 DashScope（Qwen 系列，`chat_model`/`fast_model`/`embedding_model`/`rerank_model` 在 `app/config.py` 配置，OpenAI 兼容接口）。`app/resilience.py` 封装重试/降级，`app/rate_limit.py` 有全局限流、`/ask` 独立限流和模型并发信号量 `model_semaphore`——调用 LLM 的代码要过这层并发控制。

### 前端

`vue-frontend/src/api/request.js` 是 axios 封装，自动从 Pinia `stores/auth.js` 取 Bearer Token 并处理 401 刷新；`api/index.js` 集中定义所有接口调用。`ui.py` 是遗留 Streamlit 原型，仅作对照演示，新功能不要做在里面。

### 横切设施

`app/observability.py` 提供 `configure_logging()`（控制台 + JSONL 文件双输出）和 `request_id_context`（全链路 request_id）；`app/api.py` 的两个 middleware 分别负责 request_id 注入和慢请求/指标采集（`slow_request_ms`）。`/health/live` 和 `/health/ready` 供容器 healthcheck 使用。
