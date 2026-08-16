# 高校课程 AI 学习助手平台

高校课程 AI 学习助手平台是一个面向高校课程资料管理、课程知识库问答和教学质量分析的 AI 应用开发项目。项目采用 FastAPI 后端 + Vue3 前端的前后端分离架构，围绕“课程资料入库、RAG 智能问答、引用溯源、学习 Agent、自动出题、教师分析看板”构建完整的课程学习闭环。
这个项目主要解决三个问题：第一，课程资料分散，学生查找效率低；第二，老师重复答疑成本高；第三，普通大模型不了解课程私有资料，容易没有依据地回答。
系统支持教师创建课程、上传 PDF、Markdown、TXT 等课程资料，后端会自动解析、切分、向量化，并构建课程级知识库。学生可以基于课程资料进行智能问答，系统会返回答案、引用来源、置信度和缺失信息。同时还支持学习计划生成、自动出题、用户反馈、高频问题分析和 LLM 自动评测。

## 项目亮点

- **真实前后端分离**：Vue3 单页应用通过 axios 调用 FastAPI REST 接口，开发环境使用 Vite Proxy 转发到后端。
- **登录鉴权闭环**：后端提供注册、登录、刷新 Token、退出登录能力，前端使用 Pinia 保存登录态并自动携带 Bearer Token。
- **课程级知识库**：支持创建课程、选择当前课程、上传课程资料并构建课程知识库。
- **RAG 智能问答**：基于课程资料进行问答，支持多轮会话、引用来源拼接与 Markdown 渲染。
- **学习 Agent 能力**：支持生成学习计划、自动出题、检索可视化和回答反馈。
- **教师数据分析**：提供高频问题、无引用问题、低质量问题和课程看板，辅助教师优化课程资料。
- **工程化部署**：支持 MySQL、Redis、Docker Compose、GitHub Actions CI 和生产环境配置模板。

## 技术栈

### 后端

- Python 3.11
- FastAPI
- Pydantic / pydantic-settings
- MySQL
- Redis
- Qdrant / Chroma 向量检索能力
- BM25 + 向量检索 + Rerank 混合检索流程
- LangGraph / Agent 工作流
- Docker / Docker Compose

### 前端

- Vue3
- Vite
- Element Plus
- Pinia
- vue-router@4
- axios
- markdown-it
- unplugin-vue-markdown

## 核心功能

### 1. 账号与权限

- 用户注册、登录、退出登录
- Bearer Token 鉴权
- Token 过期后的统一处理
- 课程角色区分：教师、学生、助教、管理员

### 2. 课程管理

- 创建课程
- 查看课程列表
- 选择当前课程
- 课程角色标签展示
- 课程看板入口

### 3. 课程知识库

- 上传课程资料
- 查询资料列表
- 重新入库
- 删除资料
- 查看上传任务状态

### 4. AI 问答

- 基于当前课程资料进行 RAG 问答
- 支持多轮会话 thread_id
- AI 回答支持 Markdown 渲染
- 引用来源自动附加展示
- 支持点赞、点踩与低质量反馈

### 5. 学习辅助 Agent

- 根据学习目标生成学习计划
- 根据课程主题自动生成练习题
- 检索过程可视化调试

### 6. 教师分析看板

- 课程资料统计
- 问答总量统计
- 引用率统计
- 高频问题分析
- 无引用问题分析
- 低质量问题处理

## 项目目录

```text
scholarflow/
├─ app/                         # FastAPI 后端核心代码
│  ├─ agents/                   # 学习计划、自动出题、诊断等 Agent
│  ├─ analytics/                # 问答分析与统计
│  ├─ courses/                  # 课程存储与成员关系
│  ├─ evaluation/               # 回答质量评估
│  ├─ feedback/                 # 点赞、点踩和反馈记录
│  ├─ graph/                    # LangGraph 工作流
│  ├─ ingestion/                # 文档加载与入库
│  ├─ knowledge/                # 课程知识库管理
│  ├─ retrieval/                # 混合检索、重排和调试
│  ├─ storage/                  # 数据库存储适配
│  ├─ api.py                    # FastAPI REST 接口入口
│  ├─ config.py                 # 配置管理
│  └─ security.py               # 登录鉴权与 Token 管理
├─ vue-frontend/                # Vue3 前端项目
│  ├─ src/
│  │  ├─ api/                   # axios 请求封装与接口调用
│  │  ├─ components/            # Markdown 渲染等公共组件
│  │  ├─ layouts/               # 后台主布局
│  │  ├─ router/                # vue-router 路由
│  │  ├─ stores/                # Pinia 全局状态
│  │  ├─ styles/                # 全局主题样式
│  │  └─ views/                 # 登录、课程、知识库、问答、看板页面
│  ├─ package.json
│  └─ vite.config.js
├─ scripts/                     # 本地测试、发布检查和验收脚本
├─ tests/                       # 自动化测试
├─ docs/                        # 项目文档与验收记录
├─ data/                        # 本地运行数据目录，默认不提交
├─ ui.py                        # Streamlit 原型前端，保留用于对照演示
├─ Dockerfile
├─ docker-compose.yml
├─ requirements.txt
├─ requirements.lock.txt
└─ README.md
```

## 本地开发启动

### 1. 启动后端依赖

如果使用 MySQL 和 Redis，可以先启动容器服务：

```powershell
docker compose up -d mysql redis
```

### 2. 安装后端依赖

```powershell
cd D:\python\ai-project\scholarflow
python -m pip install -r requirements.txt
```

### 3. 启动 FastAPI 后端

```powershell
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
```

后端接口文档：

```text
http://127.0.0.1:8000/docs
```

### 4. 启动 Vue 前端

```powershell
cd D:\python\ai-project\scholarflow\vue-frontend
npm install
npm run dev
```

前端开发地址：

```text
http://localhost:5173
```

说明：

- `5173` 是 Vite 开发服务端口。
- `4173` 是执行 `npm run preview` 后用于预览生产构建的端口。
- 开发环境下前端通过 `/api` 代理到 `http://127.0.0.1:8000`，避免跨域问题。

## 前端构建

```powershell
cd D:\python\ai-project\scholarflow\vue-frontend
npm run build
```

生产构建产物会生成到 `vue-frontend/dist/`，该目录不提交到 Git。

如需本地预览生产构建：

```powershell
npm run preview
```

访问：

```text
http://localhost:4173
```

## Docker Compose 部署

项目保留 Docker Compose 部署配置，可根据服务器环境准备 `.env.production` 后启动：

```powershell
copy .env.production.example .env.production
docker compose up -d --build
```

默认服务：

- FastAPI API：`http://服务器IP:8000`
- Streamlit 原型页面：`http://服务器IP:8501`
- MySQL：宿主机端口 `3307`
- Redis：宿主机端口 `6379`

Vue 前端推荐单独执行 `npm run build` 后，将 `dist` 交给 Nginx 或宝塔站点部署。

## Git 提交说明

本项目不提交以下内容：

- `node_modules/`
- `.vite/`
- `dist/`
- `.env` / `.env.production`
- 本地数据库、上传文件、日志和缓存

如果需要重新安装前端依赖：

```powershell
cd vue-frontend
npm install
```

## 当前项目状态

- 后端 FastAPI 接口已包含登录鉴权、课程管理、资料上传、RAG 问答、反馈、检索调试和教师分析看板。
- 前端已由 Streamlit 原型迁移为 Vue3 + Element Plus 后台管理单页应用。
