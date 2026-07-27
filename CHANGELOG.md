# Changelog

本文件记录 ScholarFlow 每个正式版本对用户和部署者可见的变化。

## [Unreleased]

### Added

- 暂无。

## [1.0.0] - 2026-07-27

### Added

- 基于 Qwen、LangGraph、Chroma 和 MCP 的可追溯研究问答流程。
- PDF、Markdown 和 TXT 文档导入与向量检索。
- 知识、报告和回答 Agent 协作，以及执行轨迹记录。
- 用户注册、登录、Token 轮换、注销和线程所有权隔离。
- SQLite 持久记忆、请求日志、限流、并发保护和运行指标。
- 模型与 MCP 超时、有限重试和结构化降级。
- FastAPI 与 Streamlit 双服务 Docker Compose 部署。
- 存活检查、就绪检查、一致性备份和恢复流程。
- 离线发布门禁、GitHub Actions 和上线验收清单。
- 前端支持登录后恢复最近历史会话，并可在侧边栏切换旧线程。

### Security

- 密码使用 Argon2 哈希保存。
- 日志和指标不记录密码、Token、API Key 或问题正文。
- 真实环境文件、数据库、日志和备份不会进入镜像或版本库。

### Known limitations

- API 固定使用一个 worker；限流和运行指标仍保存在单进程内存中。
- SQLite 与本地 Chroma 适合单机部署，不支持多副本并发写入。
- TLS 终止和公网域名由部署环境的可信反向代理负责。
