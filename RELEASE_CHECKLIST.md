# ScholarFlow 发布验收清单

## 发布信息

- 版本：v1.0.0
- 提交：最终以 `git rev-parse v1.0.0^{}` 输出为准
- 验收人：朴有范
- 验收时间：2026-07-27 18:54
- 部署环境：Windows 本机 Docker Compose，FastAPI 8000，Streamlit 8501
- 备份目录：D:\python\ai-project\scholarflow\backups\20260727_185409

## 自动门禁

- [x] `python -m scripts.release_gate` 全部通过（已补充 `scripts.test_thread_history_api`）
- [x] `docker compose config --quiet` 通过
- [x] `docker compose build` 通过
- [ ] GitHub Actions全部通过（需要最终提交并推送后，在 GitHub Actions 页面确认最新提交的 `offline-gate` 与 `docker-build` 均为绿色）
- [ ] `git status --short` 为空（当前仍有本次修复改动，提交后再勾选）

## 真实质量验收

- [x] MCP专项真实评估达到5/5（`reports/mcp_eval_report.csv`，2026-07-27 17:59）
- [x] 通用20题真实评估至少达到18/20（实际20/20，`reports/eval_report.csv`，2026-07-27 18:06）
- [x] 失败题已经人工检查且没有安全或数据隔离问题（本次 `scripts.analyze_reports` 显示失败题：无）
- [x] 报告中没有API Key、Token、密码或用户问题正文泄漏

## 容器功能验收

- [x] `/health/live` 返回200
- [x] `/health/ready` 返回200且`ready=true`
- [x] 新用户可以注册、登录和刷新Token
- [x] 知识问答返回可定位引用
- [x] 报告问答能读取最新评估结果
- [x] 同线程追问保留上下文，不同用户不能互相读取线程
- [x] 限流返回429和`Retry-After`
- [x] API重启后账号、线程、历史消息和Chroma数据仍存在
- [x] JSONL日志持续写入且不含敏感数据

## 备份与回滚

- [x] 发布前已经生成新备份并检查`manifest.json`
- [x] 已记录当前稳定版本标签和镜像标识
- [ ] 已演练退回上一个镜像（最终标签重建后再执行）
- [x] 已演练停止服务后的数据库与Chroma恢复（第二十四步已完成）
- [x] 恢复后登录、线程读取和知识问答通过

## 发布结论

- [ ] 允许发布
- [x] 不允许发布

结论说明：第二十五步主体能力已补齐，但当前还不是“彻底完成”。原因是本次新增了历史会话恢复修复和离线测试，必须先提交、移动/重建 v1.0.0 标签、推送到 GitHub，并确认最新提交触发的 GitHub Actions 全部通过后，才能把结论改为“允许发布”。
