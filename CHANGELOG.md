# Changelog

本文件记录 ScholarFlow 每个正式版本对用户和部署者可见的变化。

## [Unreleased]

### Added

- 暂无。

## [1.1.0] - 2026-08-03

### Added

- Chroma 向量检索与本地 BM25 混合召回，并使用阿里 `gte-rerank-v2` 精排。
- 长期滚动摘要、最近 12 条消息窗口和会话轮次持久化。
- 只读 `diagnosis_agent`，汇总数据文件、评估报告和运行指标。
- 历史会话标题与最近更新时间排序。
- 鉴权 PDF、TXT、Markdown 上传、大小限制、文件名清理和增量入库。
- 混合检索、摘要记忆、诊断 Agent、上传 API 和在线链路验收脚本。

### Changed

- Supervisor 支持知识、报告和诊断三个 Agent 分支。
- Streamlit 侧边栏使用首个问题显示会话标题，并提供知识资料上传入口。
- 离线发布门禁覆盖旧数据库迁移、摘要 checkpoint、诊断和上传安全校验。

### Fixed

- 旧版 SQLite `threads` 表升级时不能添加非恒定默认值的问题。
- 百炼 rerank 地址缺少最后一级 `text-rerank` 导致全部请求降级的问题。

### Verification

- 离线发布门禁全部通过。
- 真实阿里模型通用评估 `20/20`。
- MCP 与诊断专项评估 `8/8`。
- Docker API healthy，Web、上传、引用、标题和数据持久化验收通过。

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
