# ScholarFlow 升级手册

> 面向「简历项目」定位的七步升级路线。每一步包含：**为什么做**（动机与原理）、**改动文件一览**（精确到插入位置）、**可插入代码**（逐行中文注解，风格对齐仓库现有注释密度）、**怎么验证**（可检查的成功标准）、**面试怎么讲**（转化为简历话术）。
>
> 项目定位：简历项目 ｜ 总工作量预估：约 8–10 个工作日 ｜ 编写时间：2026-08

## 升级总览（按建议执行顺序排列）

| 顺序 | 升级项 | 一句话目标 | 工作量 |
|---|---|---|---|
| 第 0 步 | [修复 Token 静默刷新](#第-0-步修复-token-静默刷新) | 消除「每 15 分钟被踢出登录」的真 bug | 半天 |
| 第 1 步 | [RAG 评估体系](#第-1-步rag-评估体系) | 检索调优从拍脑袋变成数据驱动 | 2–3 天 |
| 第 2 步 | [流式问答（SSE）](#第-2-步流式问答sse) | 首字秒出，演示效果质变 | 1–2 天 |
| 第 3 步 | [任务队列（arq + Redis）](#第-3-步任务队列arq--redis) | 重启不丢任务、失败可重试 | 1–2 天 |
| 第 4 步 | [前端工程化](#第-4-步前端工程化) | 补齐 lint / 测试 / CI 底线 | 1 天 |
| 第 5 步 | [拆分 api.py](#第-5-步拆分-apipy) | 1600 行单文件按业务域拆分 | 半天 |
| 第 6 步 | [依赖版本升级](#第-6-步依赖版本升级) | Vite 4→7、Python 3.11→3.12 | 半天 |
| 附录 | [深度项（选做）](#附录深度项有余力再做) | 限流 Redis 化 / Prometheus / Alembic | 各 1 天 |

---

## 第 0 步：修复 Token 静默刷新

> 约半天 · 只动前端两个文件

### 改动文件一览

| 操作 | 文件 | 插入 / 修改位置 |
|---|---|---|
| 修改 | `vue-frontend/src/stores/auth.js` | ① 文件顶部 `STORAGE_KEY` 后加模块级变量；② actions 里 `saveAuth` 之后新增 `refresh()` |
| 修改 | `vue-frontend/src/api/request.js` | 整体替换响应拦截器（`request.interceptors.response.use` 那段） |

### 为什么做

先理解双令牌机制的设计意图：`access_token_ttl_minutes = 15`（`app/config.py`），access token 短命，把泄露后的损失窗口压到 15 分钟；refresh token 长命（30 天）只用于换新 access token，且后端已做**轮换**——`app/security.py` 的 `rotate_refresh_token` 每次刷新后作废旧 refresh token，防止盗用重放。

问题在前端：`request.js` 的响应拦截器遇到 401 时**直接清空登录态跳登录页，从未调用 `/auth/refresh`**。后端续期能力建好了，前端没接上——用户每 15 分钟被强制登出一次，真实可复现。

> ⚠️ **关键难点（面试考点）**：页面同时发出 3 个请求、3 个都收到 401 时，不能刷新 3 次——第一次刷新后旧 refresh token 已被轮换作废，后两次必然失败。必须用**单例 Promise 去重**：第一个 401 发起刷新，其余 401 等待同一个 Promise。

### 怎么做 · 第一步：auth store 加刷新动作

**修改 `vue-frontend/src/stores/auth.js` —— 位置：文件顶部 `const STORAGE_KEY` 那一行之后**

```js
// 模块级单例 Promise：并发的多个 401 只触发一次刷新，其余请求复用同一个 Promise 等结果
// 注意：不能放进 state——Promise 不可序列化，persist() 写 localStorage 时会把它写坏
let refreshPromise = null
```

**修改 `vue-frontend/src/stores/auth.js` —— 位置：actions 中 `saveAuth(data)` 动作之后，新增一个 action**

```js
    // 用 refresh token 静默换新 access token（双令牌续期）
    // 后端 /auth/refresh 返回 AccountSessionResponse，结构与登录响应一致，可直接复用 saveAuth
    async refresh() {
      // 已有刷新在进行：直接复用，防止并发刷新——第一次刷新后旧 refresh token 已被后端轮换作废，
      // 第二次刷新必然 401，会把本不该登出的用户踢出去
      if (refreshPromise) return refreshPromise
      refreshPromise = (async () => {
        // 用原生 fetch 而不是 axios 实例：避免刷新请求自己也走进 response 拦截器造成递归
        const resp = await fetch(`${import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: this.refreshToken })
        })
        // refresh token 也过期/被吊销：抛错，由调用方（拦截器）决定登出
        if (!resp.ok) throw new Error('refresh token 已失效')
        const data = await resp.json()
        // 复用现有动作：写入新双 token（后端已轮换，旧 refresh 作废）并 persist 落盘
        this.saveAuth(data)
      })()
      try {
        await refreshPromise
      } finally {
        // 无论成败都复位，否则一次失败后所有后续请求都会拿到这个 rejected Promise
        refreshPromise = null
      }
    },
```

### 怎么做 · 第二步：拦截器改为刷新 + 重放

**修改 `vue-frontend/src/api/request.js` —— 位置：整体替换 `request.interceptors.response.use(...)` 这一段**

```js
request.interceptors.response.use(
  (response) => response,
  // 拦截器改 async：刷新是异步操作，await 之后才能决定重放还是登出
  async (error) => {
    const auth = useAuthStore()
    const { response, config } = error
    const status = response?.status
    // 三个条件同时满足才尝试「刷新 + 重放」：
    // 1) 是 401
    // 2) 本请求没重试过（_retried 防死循环：新 token 也 401 说明是权限问题，不是过期问题）
    // 3) 不是 /auth 下的接口（登录失败、刷新失败本身的 401 不该再触发刷新）
    if (status === 401 && !config._retried && !config.url.includes('/auth/')) {
      config._retried = true
      try {
        await auth.refresh()                                  // 静默续期；并发请求在此复用同一个刷新 Promise
        config.headers.Authorization = `Bearer ${auth.accessToken}`
        return request(config)                                // 用新 token 重放原请求，用户对过期无感知
      } catch {
        // refresh 也失效（30 天没活跃 / 被吊销）：彻底登出
        auth.clearAuth()
        ElMessage.error('登录已过期，请重新登录')
        router.push('/login')
      }
    }
    return Promise.reject(error)
  }
)
```

### 怎么验证

- 把 `app/config.py` 的 `access_token_ttl_minutes` 临时改成 `1`，登录后等 70 秒再操作页面：应无感继续（Network 里能看到一次 `/auth/refresh`），而不是跳登录页。
- 过期瞬间快速连点 3 个按钮：Network 里 `/auth/refresh` **只出现一次**，3 个原请求全部成功——去重生效。
- 手动把 localStorage 里的 refresh token 改错再发请求：应登出跳登录页——失败兜底正确。

### 💬 面试怎么讲

> 「排查登录体验时发现前端 401 拦截器只做了登出、没接后端的 refresh 轮换接口，用户每 15 分钟被强制登出。修复时用单例 Promise 解决了并发请求同时触发刷新、导致轮换后的 refresh token 互相作废的竞争问题。」——问题驱动 + 并发细节，比「实现了 Token 刷新」有分量得多。

---

## 第 1 步：RAG 评估体系

> 约 2–3 天 · 核心亮点

### 改动文件一览

| 操作 | 文件 | 说明 |
|---|---|---|
| 修改 | `data/eval/questions.jsonl` | 每行补充 `should_refuse` 字段，新增 5–10 条拒答题 |
| 新增 | `scripts/evaluate_run.py` | 评估主脚本：参数快照 + JSON/Markdown 报告 |
| 新增 | `scripts/evaluate_compare.py` | 两份报告回归对比 |
| 修改 | `RELEASE_CHECKLIST.md` | 「真实质量验收」改为引用 evaluate_run/compare 的产物 |

### 为什么做

RAG 系统的每一次调优——BM25 权重、rerank top-k、chunk 大小、问题改写策略——没有量化反馈就是玄学。现状是 `scripts/evaluate.py` 手动跑、产出覆盖式 CSV、人工看分数，`RELEASE_CHECKLIST.md` 里「20/20」手工勾选：不可重复、不可对比，回答不了「这次改动是变好还是变坏」。

仓库里其实已有两块好底子：`app/evaluation/metrics.py` 的 `score_case`（来源命中 + 关键词召回）和 `app/evaluation/judge.py` 的 `judge_answer`（LLM-as-judge 忠实度打分）。这一步是把它们组织成**可回归、可对比的体系**，而不是从零造轮子。

### 怎么做 · 第一步：扩充数据集

**修改 `data/eval/questions.jsonl` —— 位置：每行 JSON 增加 `should_refuse` 字段；文件末尾追加拒答题**

```json
{"question": "chunk_overlap 的作用是什么？", "expected_sources": ["course.md"], "required_keywords": ["重叠"], "should_refuse": false}
{"question": "这门课期末考试是哪天？", "expected_sources": [], "required_keywords": [], "should_refuse": true}
```

拒答题的设计原则：问题*看起来*像课程相关（考试安排、教室地点、老师联系方式），但资料里确实没有——考察的是系统「不知道就说不知道」的能力，这是教育场景的安全底线。

### 怎么做 · 第二步：评估主脚本

**新增 `scripts/evaluate_run.py` —— 运行方式 `python -m scripts.evaluate_run`**

```python
"""评估运行器：跑黄金数据集，输出带参数快照的 JSON 报告
与旧 evaluate.py 的区别：
1. 报告头部记录检索/模型参数快照——没有快照的两份报告不可比
2. 输出 JSON（机器可对比）而不只是 CSV（人看）
3. 增加拒答正确率指标
运行：python -m scripts.evaluate_run [数据集路径] [报告输出路径]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings                     # 读取当前模型与检索配置，写入报告快照
from app.evaluation.metrics import score_case        # 已有：来源命中 + 关键词召回
from app.evaluation.judge import judge_answer        # 已有：LLM-as-judge 忠实度/相关性打分
from app.graph.builder import workflow               # 无记忆版图实例：每题独立状态，互不污染

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVAL_FILE = PROJECT_ROOT / "data" / "eval" / "questions.jsonl"


def config_snapshot() -> dict:
    """记录本次评估运行时的关键参数——对比报告时先核对快照，快照不同则指标差异不可归因"""
    return {
        "chat_model": settings.chat_model,
        "fast_model": settings.fast_model,
        "embedding_model": settings.embedding_model,
        "rerank_model": settings.rerank_model,
        "vector_backend": settings.vector_backend,
        "ran_at": datetime.now(timezone.utc).isoformat(),
    }


def detect_refusal(answer_text: str) -> bool:
    """判断系统是否拒答：教育助手的拒答话术包含「资料中未提及/无法回答」类表述
    上线后应改为读取 ResearchAnswer.missing_information 字段，更可靠"""
    markers = ("未提及", "无法回答", "没有相关信息", "资料中没有", "无法从")
    return any(m in answer_text for m in markers)


def main() -> None:
    eval_file = Path(sys.argv[1]) if len(sys.argv) >= 2 else DEFAULT_EVAL_FILE
    report_file = (
        Path(sys.argv[2]) if len(sys.argv) >= 3
        else PROJECT_ROOT / "reports" / f"eval_run_{datetime.now():%Y%m%d_%H%M%S}.json"
    )

    cases = [json.loads(line) for line in eval_file.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    results = []

    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['question']}")
        graph_result = workflow.invoke({"question": case["question"]})
        answer_obj = graph_result["answer"]
        answer_text = answer_obj.answer if hasattr(answer_obj, "answer") else str(answer_obj)

        scored = score_case(case, answer_obj)         # 复用已有评分：source_hit / keyword_recall
        judged = judge_answer(case["question"], scored.contexts if hasattr(scored, "contexts") else [], answer_text)

        refused = detect_refusal(answer_text)
        results.append({
            "question": case["question"],
            "source_hit": scored.source_hit,                    # 期望来源是否被引用
            "keyword_recall": round(scored.keyword_recall, 3),  # 标准答案关键词覆盖度
            "faithfulness": judged.faithfulness,                # LLM 判断：答案是否忠于引用
            "should_refuse": case.get("should_refuse", False),
            "refused": refused,
            # 拒答正确 = 该拒的拒了，或不该拒的没拒
            "refusal_correct": refused == case.get("should_refuse", False),
        })

    # 汇总指标：三层各自一个总分
    n = len(results)
    report = {
        "snapshot": config_snapshot(),
        "metrics": {
            "source_hit_rate": sum(r["source_hit"] for r in results) / n,
            "avg_keyword_recall": sum(r["keyword_recall"] for r in results) / n,
            "avg_faithfulness": sum(r["faithfulness"] for r in results) / n,
            "refusal_accuracy": sum(r["refusal_correct"] for r in results) / n,
        },
        "cases": results,                              # 逐题明细留给 compare 做下钻
    }
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告：{report_file}")
    for k, v in report["metrics"].items():
        print(f"  {k}: {v:.2f}")


if __name__ == "__main__":
    main()
```

> ⚠️ **注意**：上面的 `judge_answer` 入参请按 `app/evaluation/judge.py` 的真实签名对齐（当前签名为 `judge_answer(question, contexts, answer)`，contexts 需要从 graph 结果的引用里取）。`detect_refusal` 的关键词匹配是过渡方案，稳定后应改读 `ResearchAnswer.missing_information` 字段。

### 怎么做 · 第三步：回归对比脚本

**新增 `scripts/evaluate_compare.py` —— 运行方式 `python -m scripts.evaluate_compare 旧报告.json 新报告.json`**

```python
"""回归对比：两份 evaluate_run 报告的指标 diff
固定工作流：改检索参数 → 跑 evaluate_run → compare 对比 → 决定保留或回滚
运行：python -m scripts.evaluate_compare reports/before.json reports/after.json
"""
import json
import sys
from pathlib import Path

def main() -> None:
    before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    after = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))

    # 先核对参数快照：把指标差异和「其实是换了模型」区分开
    for key in ("chat_model", "embedding_model", "rerank_model"):
        if before["snapshot"].get(key) != after["snapshot"].get(key):
            print(f"⚠ 快照不一致：{key}  {before['snapshot'].get(key)} → {after['snapshot'].get(key)}")

    print(f"{'指标':<22}{'改动前':>8}{'改动后':>8}{'差值':>8}")
    for key, new_val in after["metrics"].items():
        old_val = before["metrics"].get(key, 0)
        delta = new_val - old_val
        arrow = "↑" if delta > 0.005 else ("↓" if delta < -0.005 else "→")
        print(f"{key:<22}{old_val:>8.2f}{new_val:>8.2f}{arrow} {delta:>+6.2f}")

    # 逐题下钻：列出「变好/变差」的题，调优时最关注的是变差的题
    before_cases = {c["question"]: c for c in before["cases"]}
    for c in after["cases"]:
        b = before_cases.get(c["question"])
        if b and (b["source_hit"], b["refusal_correct"]) != (c["source_hit"], c["refusal_correct"]):
            print(f"  变化题：{c['question']}  命中 {b['source_hit']}→{c['source_hit']}  "
                  f"拒答正确 {b['refusal_correct']}→{c['refusal_correct']}")

if __name__ == "__main__":
    main()
```

### 怎么做 · 第四步：接入门禁

离线 CI 不能跑（需要 DashScope Key），把它写成发布前手动门禁：改 `RELEASE_CHECKLIST.md` 的「真实质量验收」一节，把手工勾的「20/20」替换为「`evaluate_compare` 对比上一稳定版报告，四项指标无下降」。

### 怎么验证

- **区分度测试**：故意把 `app/retrieval/hybrid.py` 的 BM25 权重调到极端值，跑一遍 compare——报告应显示 source_hit_rate 明显下跌。评估体系连这种变化都测不出，说明指标没区分度，先修评估再谈调优。
- 拒答题逐条人工核对一次 judge 打分，确认 LLM-as-judge 没有系统性偏松。

### 💬 面试怎么讲

> 「在已有评分模块基础上建立了可回归的 RAG 评估体系：参数快照保证报告可比，三层指标（来源命中、忠实度、拒答正确率），每次检索调参都用 compare 脚本与基线对比。比如调 rerank top-k 时，来源命中升了但忠实度降了，最后按 compare 结果选了折中值。」

---

## 第 2 步：流式问答（SSE）

> 约 1–2 天 · 演示效果提升最大

### 改动文件一览

| 操作 | 文件 | 插入 / 修改位置 |
|---|---|---|
| 修改 | `app/api.py` | `ask_course` 函数 `return answer_payload`（约 845 行）之后，新增流式路由 |
| 修改 | `vue-frontend/src/api/index.js` | 文件末尾新增 `askCourseStream` 函数 |
| 修改 | `vue-frontend/src/views/ChatView.vue` | 发送消息的方法改为消费流式接口（逐 token 追加到当前消息） |

### 为什么做

现在 `answer_agent` 生成完整答案后才一次性返回，长回答白屏十几秒。流式输出让首字 1–2 秒出现，是生成式产品的体验标配，也是演示时最直观的升级。

选型结论：**用 SSE 不用 WebSocket**。问答是「一次请求、服务端单向推送」场景，SSE 基于普通 HTTP、无需连接管理，WebSocket 在这里是过度设计——能讲清这个判断本身就是面试分。

> ⚠️ **诚实提示（真实风险点）**：逐 token 流式的前提是 answer_agent 里的 LLM 调用是普通 chat 调用。如果项目里答案生成用了 `with_structured_output`（结构化输出通常**不支持**逐 token 流式），就退化为「节点级流式」：推送 supervisor 完成 / 检索完成 / 正在生成 等进度事件，答案仍一次性下发。先打开 `app/agents/workers.py` 确认 answer_agent 的调用方式，再决定下面代码里用哪套事件。

### 怎么做 · 第一步：后端流式路由

**修改 `app/api.py` —— 位置①：文件头部导入区补充；位置②：`ask_course` 的 `return answer_payload` 之后插入整个新路由**

```python
# ===== 位置①：文件头部导入区补充两行 =====
from json import dumps as json_dumps
from fastapi.responses import StreamingResponse

# ===== 位置②：ask_course 函数结束之后插入 =====
@app.post("/courses/{course_id}/ask/stream", tags=["问答"], summary="课程内问答（流式）")
async def ask_course_stream(
    course_id: str,
    request: AskRequest,
    session: tuple[str, str] = Depends(current_session),
):
    """课程问答的 SSE 流式版本：与 ask_course 业务逻辑一致，只改返回形式"""
    # —— 权限与线程归属校验：与 ask_course 完全相同，照抄这三段 ——
    user_id, _ = session
    try:
        course_store.require_course_access(course_id, user_id)
        auth_store.claim_thread(user_id, request.thread_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    async def event_stream():
        """SSE 事件流生成器：每 yield 一个字符串就是一个 SSE 帧
        帧格式（SSE 协议）：event: <事件名>\ndata: <JSON>\n\n —— 两个换行结束一帧"""
        try:
            # astream_events 是 LangGraph 的事件流 API：图执行过程中每个节点/模型的
            # 开始、流式输出、结束都会产出事件，version="v2" 是当前稳定事件协议
            async for ev in memory_workflow.astream_events(
                {"question": request.question, "course_id": course_id},
                config={"configurable": {"thread_id": request.thread_id}},
                version="v2",
            ):
                # 模型逐 token 输出事件：只有节点内是普通 chat 调用时才会出现
                if ev["event"] == "on_chat_model_stream":
                    token = ev["data"]["chunk"].content
                    if token:
                        yield f"event: token\ndata: {json_dumps({'t': token}, ensure_ascii=False)}\n\n"
                # answer_agent 节点结束事件：节点名 = builder.py 里 add_node 的第一个参数
                # 引用/置信度等元信息在答案生成完毕后一次性下发，前端收到后再渲染来源列表
                elif ev["event"] == "on_chain_end" and ev.get("name") == "answer_agent":
                    output = ev["data"].get("output") or {}
                    answer_obj = output.get("answer")
                    payload = (
                        answer_obj.model_dump() if hasattr(answer_obj, "model_dump")
                        else (answer_obj if isinstance(answer_obj, dict) else {})
                    )
                    meta = {
                        "citations": payload.get("citations", []),
                        "confidence": payload.get("confidence", 0),
                        "missing_information": payload.get("missing_information", []),
                    }
                    yield f"event: meta\ndata: {json_dumps(meta, ensure_ascii=False)}\n\n"
        except Exception as exc:
            # 流式中途出错不能用 HTTP 状态码（响应头早已发出），只能用 error 事件通知前端
            yield f"event: error\ndata: {json_dumps({'msg': str(exc)}, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

### 怎么做 · 第二步：前端流式请求函数

**修改 `vue-frontend/src/api/index.js` —— 位置：文件末尾新增导出函数**

```js
import { API_BASE_URL } from './request'   // 文件顶部补充导入（若已导入则跳过）

// 流式问答：EventSource 只支持 GET，问答是 POST，所以用 fetch + ReadableStream 手动解 SSE 帧
// callbacks: onToken(增量文本) / onMeta(引用与置信度) / onError(错误信息)
export async function askCourseStream(courseId, payload, { onToken, onMeta, onError, signal }) {
  const auth = useAuthStore()
  const resp = await fetch(`${API_BASE_URL}/courses/${courseId}/ask/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${auth.accessToken}`   // fetch 不走 axios 拦截器，token 要手动带
    },
    body: JSON.stringify(payload),
    signal                                           // 关联 AbortController，「停止生成」靠它
  })
  if (!resp.ok) throw new Error(`请求失败：${resp.status}`)

  const reader = resp.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    // SSE 帧以 \n\n 分隔；最后一帧可能不完整，留在 buffer 里等下一块
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const eventLine = frame.split('\n').find((l) => l.startsWith('event:'))
      const dataLine = frame.split('\n').find((l) => l.startsWith('data:'))
      if (!eventLine || !dataLine) continue
      const event = eventLine.slice(6).trim()
      const data = JSON.parse(dataLine.slice(5).trim())
      if (event === 'token') onToken?.(data.t)         // 逐 token 追加到当前消息
      else if (event === 'meta') onMeta?.(data)        // 答案完成后渲染引用来源
      else if (event === 'error') onError?.(data.msg)
    }
  }
}
```

ChatView.vue 里：发送方法改为调 `askCourseStream`，`onToken` 里 `currentMessage.content += token`；「停止生成」按钮调用 `AbortController.abort()`。保留原 `/ask` 非流式接口不动——第 1 步的评估体系继续用它，行为可比。

### 怎么验证

- DevTools Network 确认响应类型是 `text/event-stream` 且分块到达。
- 掐表对比首 token 延迟：应从 10 秒级降到 1–2 秒级——数字记下来，简历量化素材。
- 生成中途点「停止」：后端日志应看到任务取消，而不是继续烧 token 跑完。

### 💬 面试怎么讲

> 「把问答从整段返回改造成 SSE 流式：LangGraph 侧用 astream_events 抽取模型 token 与节点完成事件，前端因 EventSource 不支持 POST 改用 fetch + ReadableStream 手动解帧，并实现 AbortController 取消传播。首 token 延迟从约 10 秒降到 2 秒内。过程中还识别出结构化输出不支持逐 token 流式的限制，用节点完成事件下发元信息做了折中。」

---

## 第 3 步：任务队列（arq + Redis）

> 约 1–2 天 · 可靠性故事

### 改动文件一览

| 操作 | 文件 | 插入 / 修改位置 |
|---|---|---|
| 修改 | `requirements.txt` | 依赖列表加 `arq` |
| 新增 | `app/tasks/queue.py` | 新建：arq 连接池单例 |
| 新增 | `app/tasks/worker.py` | 新建：worker 进程入口 |
| 修改 | `app/api.py` | `upload_course_document_async` 内 `background_tasks.add_task(...)`（约 696–702 行）替换为入队调用 |
| 修改 | `docker-compose.yml` | `api` 服务之后新增 `worker` 服务 |

### 为什么做

文档入库目前跑在 FastAPI 进程内 `BackgroundTasks`，四个硬伤：
1. **重启即丢任务**（解析到一半的 PDF 永久中断，`task_store` 永远停在 running）；
2. **没有重试**；
3. 入库是 CPU/IO 重活，**与请求争抢进程资源**；
4. **锁死 `--workers 1`**（compose 里写死很大程度上就是因为任务在进程内）。

选型 **arq 而非 Celery**：arq 是 asyncio 原生、Redis 单一依赖（项目已有）、配置极简；Celery 功能全但重，对单人项目是负担。面试被问「为什么不用 Celery」，这个权衡就是答案。

### 怎么做 · 第一步：连接池与 worker

**新增 `app/tasks/queue.py`**

```python
"""arq 连接池单例：API 进程只负责把任务投进 Redis，不亲自执行
遵循仓库惯例：模块级单例（同 course_store / task_store 的模式），不引入 DI 容器"""
from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings

_pool = None  # 模块级连接池，首次使用时惰性创建


async def get_queue():
    """获取 arq 连接池（懒加载单例）：enqueue_job 的入口"""
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    return _pool
```

**新增 `app/tasks/worker.py` —— 启动命令 `python -m arq app.tasks.worker.WorkerSettings`**

```python
"""arq worker 定义：独立进程运行，从 Redis 队列取 ingestion 任务执行
本地启动：python -m arq app.tasks.worker.WorkerSettings
容器启动：见 docker-compose.yml 的 worker 服务"""
import asyncio

from arq.connections import RedisSettings

from app.config import settings
from app.tasks.ingestion import run_ingestion_task


async def ingestion_job(ctx, task_id: str, source_id: str, file_path: str, course_id: str | None):
    """队列任务包装：签名与 run_ingestion_task 对齐，参数随 enqueue_job 传入
    ctx 是 arq 注入的上下文（含 redis 连接、job_id、重试次数），本任务暂不需要"""
    # 幂等短路：重试/重复入队时，若任务已成功则直接返回，不重复入库
    # （向量写入按 (source_id, chunk_index) upsert，天然幂等，这里再加一道状态闸）
    from app.tasks.store import task_store
    task = task_store.get_task(task_id)
    if task and task.get("status") == "success":
        return

    # run_ingestion_task 是同步阻塞函数（解析 PDF、embedding），
    # 用 asyncio.to_thread 丢到线程池执行，避免卡住 worker 的事件循环
    await asyncio.to_thread(run_ingestion_task, task_id, source_id, file_path, course_id)


class WorkerSettings:
    """arq 的 worker 配置类：命令行 python -m arq 按模块路径加载它"""
    functions = [ingestion_job]
    max_tries = 3                                    # 失败自动重试最多 3 次——BackgroundTasks 给不了的能力
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
```

### 怎么做 · 第二步：API 侧改投递

**修改 `app/api.py` —— 位置：`upload_course_document_async` 内，替换 `background_tasks.add_task(...)` 整段（约 696–702 行）**

```python
    # 改造点：不再用进程内 BackgroundTasks，改为投递到 Redis 队列，由独立 worker 进程执行
    # 接口契约不变：前端照常轮询 /tasks/{task_id}，前端代码零改动
    queue = await get_queue()
    await queue.enqueue_job(
        "ingestion_job",          # 对应 app/tasks/worker.py 里的函数名
        task_id,
        document.source_id,
        str(target),
        course_id,
    )
```

同时做两处清理（你的改动产生的孤儿代码，按规范应删）：函数签名里的 `background_tasks: BackgroundTasks` 参数删掉；文件头部 `from fastapi import BackgroundTasks` 若无其他用处一并删除。文件头部补充 `from app.tasks.queue import get_queue`。

### 怎么做 · 第三步：compose 加 worker 服务

**修改 `docker-compose.yml` —— 位置：`api` 服务定义之后、`web` 服务之前插入**

```yaml
  worker:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        PYTHON_BASE_IMAGE: ${PYTHON_BASE_IMAGE:-docker.1ms.run/library/python:3.11-slim}
    env_file:
      - .env.production
    # 与 api 同镜像，只换启动命令：arq 按模块路径加载 WorkerSettings
    command: ["python", "-m", "arq", "app.tasks.worker.WorkerSettings"]
    volumes:
      - ./data:/app/data          # 必须挂载：worker 要读上传文件、写向量库
    depends_on:
      mysql:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
```

### 怎么验证

- **重启测试**：上传大 PDF，任务 running 时 `docker restart` API 容器——任务应继续推进到 success。这是本次升级的存在意义，必须亲眼看到。
- **重试测试**：临时在 job 里抛异常，确认按 `max_tries=3` 重试且 task_store 状态流转正确。
- **幂等测试**：同一任务手动入队两次，确认向量库里没有重复 chunk、任务记录不被重置。

### 💬 面试怎么讲

> 「发现进程内 BackgroundTasks 在容器重启时丢任务、无重试，且锁死单 worker。迁移到 arq + Redis 队列后：任务持久化可恢复、max_tries 自动重试、按状态闸 + upsert 保证幂等，API 进程得以放开多 worker。接口契约保持不变，前端零改动。」

---

## 第 4 步：前端工程化

> 约 1 天 · 工程底线

### 改动文件一览

| 操作 | 文件 | 说明 |
|---|---|---|
| 新增 | `vue-frontend/eslint.config.js` | ESLint 9 flat config |
| 修改 | `vue-frontend/package.json` | 加 scripts 与 devDependencies |
| 新增 | `vue-frontend/src/stores/auth.test.js` | auth store 刷新去重的单测 |
| 修改 | `.github/workflows/ci.yml` | 新增 frontend job |

### 为什么做

`package.json` 里没有任何 lint/test 配置，CI 只验后端——面试官翻代码时这是一眼可见的减分项。排在第 0 步之后做很划算：**auth store 的刷新去重逻辑正好是第一个测试对象**，互相成就。测试策略：不追覆盖率数字，只覆盖「关键路径」——Token 刷新去重、错误信息拼装这类纯逻辑。

### 怎么做 · 第一步：ESLint + Prettier

**新增 `vue-frontend/eslint.config.js`（ESLint 9 使用 flat config，不再用 .eslintrc）**

```js
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import prettier from 'eslint-config-prettier'   // 只负责关闭与 Prettier 冲突的格式规则，各司其职

export default [
  js.configs.recommended,                        // JS 基础规则（未定义变量、不可达代码等）
  ...pluginVue.configs['flat/recommended'],      // Vue3 官方推荐规则（template 语法、props 校验等）
  prettier,                                      // 格式交给 Prettier，ESLint 只管代码质量
  {
    languageOptions: {
      globals: {                                 // 浏览器环境全局变量，不声明会报 no-undef
        window: 'readonly', document: 'readonly', localStorage: 'readonly',
        fetch: 'readonly', AbortController: 'readonly', console: 'readonly'
      }
    }
  }
]
```

**修改 `vue-frontend/package.json` —— scripts 块加三条；新增 devDependencies 后 `npm install`**

```json
"scripts": {
  "dev": "vite --host 0.0.0.0 --port 5173",
  "build": "vite build",
  "preview": "vite preview --host 0.0.0.0 --port 4173",
  "lint": "eslint src",
  "format": "prettier --write src",
  "test": "vitest run"
},
"devDependencies": {
  "@eslint/js": "^9", "eslint": "^9", "eslint-plugin-vue": "^9",
  "eslint-config-prettier": "^9", "prettier": "^3", "vitest": "^2"
}
```

### 怎么做 · 第二步：关键路径单测

**新增 `vue-frontend/src/stores/auth.test.js` —— 运行 `npm test`**

```js
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from './auth'

// fetch 是全局函数，直接用 vi.stubGlobal 替换为可控 mock
const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

beforeEach(() => {
  setActivePinia(createPinia())                  // 每个用例一个干净的 Pinia 实例
  localStorage.clear()
  fetchMock.mockReset()
})

describe('auth.refresh', () => {
  it('刷新成功后写入新双 token 并落盘', async () => {
    const store = useAuthStore()
    store.refreshToken = 'old-refresh'
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ user_id: 'u1', access_token: 'new-access',
                           refresh_token: 'new-refresh', role: 'student' })
    })

    await store.refresh()

    expect(store.accessToken).toBe('new-access')
    expect(store.refreshToken).toBe('new-refresh')          // 后端轮换：必须换新 refresh
    expect(JSON.parse(localStorage.getItem('course_ai_auth_state')).accessToken).toBe('new-access')
  })

  it('并发调用只发一次刷新请求（单例 Promise 去重）', async () => {
    const store = useAuthStore()
    store.refreshToken = 'old-refresh'
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ user_id: 'u1', access_token: 'a', refresh_token: 'r' })
    })

    // 模拟 3 个请求同时 401：三个 refresh 并发触发
    await Promise.all([store.refresh(), store.refresh(), store.refresh()])

    expect(fetchMock).toHaveBeenCalledTimes(1)              // 这是第 0 步 bug 修复的回归保障
  })

  it('refresh token 失效时抛错（由拦截器决定登出）', async () => {
    const store = useAuthStore()
    fetchMock.mockResolvedValueOnce({ ok: false })
    await expect(store.refresh()).rejects.toThrow()
  })
})
```

### 怎么做 · 第三步：CI 前端 job

**修改 `.github/workflows/ci.yml` —— 位置：jobs 下与 `offline-gate` 并列新增**

```yaml
  frontend:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: npm
          cache-dependency-path: vue-frontend/package-lock.json
      - run: npm ci
        working-directory: vue-frontend
      - run: npm run lint && npm test && npm run build
        working-directory: vue-frontend
```

### 怎么验证

- 故意留一个未使用变量，`npm run lint` 必须报错。
- 把 refresh 里的去重逻辑故意删掉（每次新建 Promise），「并发去重」用例必须红——测不出回归的测试等于没写。
- 推送后 GitHub Actions 前端 job 变绿。

### 💬 面试怎么讲

> 「为前端从零建立工程化：ESLint flat config + Prettier + Vitest，测试聚焦关键路径——Token 刷新的 Promise 去重有专门的并发用例守护。CI 前端 job 覆盖 lint、单测和构建。」

---

## 第 5 步：拆分 api.py

> 约半天 · 纯结构调整

### 改动文件一览

| 操作 | 文件 | 说明 |
|---|---|---|
| 新增 | `app/deps.py` | 共享依赖注入（current_session 等） |
| 新增 | `app/routers/*.py` | 按 openapi_tags 分 9 个 router 文件 |
| 修改 | `app/api.py` | 瘦身为 app 实例 + middleware + include_router |

### 为什么做

`app/api.py` 约 1600 行、40+ 路由挤在一个文件：阅读成本高、合并冲突率高。拆分是零行为变化的纯结构调整。它也演示一个重要原则：**重构与功能改动分开提交**——拆分的 commit 里一行逻辑都不改，出问题可安全回退。

### 怎么做

**新增 `app/deps.py` —— 从 api.py 原样搬入 `current_session` 与 `bearer`，避免 router 间循环 import**

```python
"""共享依赖注入：供 app/routers/ 下所有 router 使用
从 api.py 搬出，一行逻辑未改"""
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security import auth_store

bearer = HTTPBearer(auto_error=False)


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> tuple[str, str]:
    # ……函数体与 api.py 中完全一致，原样搬运……
```

**新增 `app/routers/auth.py`（示例：认证域；其余 8 个域同法炮制）**

```python
"""认证域路由：注册、登录、刷新、退出——从 api.py 原样搬入"""
from fastapi import APIRouter

from app.schemas import AccountSessionResponse, LoginRequest, RefreshTokenRequest, RegisterRequest
from app.security import auth_store

router = APIRouter(tags=["认证"])   # 原装饰器里的 tags 移到 router 上，路由函数装饰器照抄

# @app.post("/auth/register", ...) 改为：
@router.post("/auth/register", response_model=AccountSessionResponse, status_code=201, summary="注册账号")
def register(request: RegisterRequest):
    # ……函数体与 api.py 中完全一致……
```

**修改 `app/api.py` —— 替换全部路由定义为 include_router 列表**

```python
from app.routers import analytics, ask, auth, courses, documents, system, tasks, threads, agents_tools

# 挂载顺序即 /docs 里的展示顺序，保持与原 openapi_tags 顺序一致
app.include_router(system.router)
app.include_router(auth.router)
app.include_router(threads.router)
app.include_router(courses.router)
app.include_router(documents.router)
app.include_router(tasks.router)
app.include_router(ask.router)
app.include_router(analytics.router)
app.include_router(agents_tools.router)
```

节奏：按域逐个搬，每搬完一个域就跑一次 `python -m scripts.release_gate`（或至少相关域的 scripts 测试）。

### 怎么验证

- 拆分前后各抓一次 `/openapi.json` 保存，对 paths 做 diff——**必须为空**，这是「零行为变化」的硬证据：`Invoke-WebRequest http://127.0.0.1:8000/openapi.json -OutFile before.json`
- `release_gate` 全绿。

### 💬 面试怎么讲

> 「把 1600 行的 api.py 按业务域拆成 9 个 router，依赖注入抽到 deps.py，用 openapi.json diff 为空验证零行为变化，重构与功能改动严格分开提交。」

---

## 第 6 步：依赖版本升级

> 约半天

### 为什么做

Vite 4 已停止维护（无安全更新），Python 3.12 有实打实的性能改进。放在最后做，是因为前面几步完成后升级有 lint + 测试 + CI + release_gate 兜底——**升级顺序本身就是依赖管理的教学点**。

### 怎么做

**修改 `vue-frontend/package.json` · `requirements.lock.txt` · `Dockerfile` · `ci.yml`**

```powershell
# ① 前端：Node 升到 ≥ 20 后执行
cd vue-frontend
npm install -D vite@^7 @vitejs/plugin-vue@^6
npm ls unplugin-vue-markdown      # 检查插件 peer 依赖是否支持 Vite 7，不支持则同步升级该插件

# ② 后端：Python 3.12 重建虚拟环境后重新锁定依赖
pip install -r requirements.txt
pip freeze > requirements.lock.txt

# ③ 同步三处版本引用（漏一处就是环境不一致的隐患）：
#    .github/workflows/ci.yml   → python-version: "3.12"
#    Dockerfile                 → PYTHON_BASE_IMAGE 默认值 python:3.12-slim
#    docker-compose.yml         → 构建参数 PYTHON_BASE_IMAGE 默认值

# ④ 验证链（顺序不要乱）：
python -m scripts.release_gate    # 后端全量离线测试
cd vue-frontend; npm run lint; npm test; npm run build
# 手动冒烟：登录 → 上传文档 → 问答 → 看板
```

### 💬 面试怎么讲

> 「在测试与 CI 补齐之后才做依赖大版本升级：Vite 4→7、Python 3.11→3.12，四处版本引用同步修改，全程由 release_gate 和 CI 兜底。」——讲顺序与验证链，而不是讲版本号。

---

## 附录：深度项（有余力再做）

> 各约 1 天 · 优先级靠后

### 限流 Redis 化（滑动窗口）

**为什么**：`app/rate_limit.py` 自己的注释写着「多进程需要 Redis 分布式限流」——把这个 TODO 做掉。教学点：固定窗口在窗口边界有 2 倍突刺（窗口末尾 + 下一窗口开头各打满限额），滑动窗口日志算法可解。

**修改 `app/rate_limit.py` —— 新增 `RedisSlidingWindowLimiter` 类；api.py 中限流器实例按配置切换**

```python
# Lua 脚本保证「清理过期 + 计数 + 写入」三步原子执行——拆成多次 Redis 调用会有并发计数竞争
SLIDING_WINDOW_LUA = """
-- KEYS[1]=限流键；ARGV[1]=当前毫秒；ARGV[2]=窗口毫秒；ARGV[3]=限额
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, ARGV[1] - ARGV[2])  -- 清掉窗口外的旧请求记录
local count = redis.call('ZCARD', KEYS[1])                     -- 窗口内已有请求数
if count < tonumber(ARGV[3]) then
  -- 时间戳+随机后缀做 member，避免同一毫秒两个请求互相覆盖
  redis.call('ZADD', KEYS[1], ARGV[1], ARGV[1] .. ':' .. math.random())
  redis.call('PEXPIRE', KEYS[1], ARGV[2])                      -- 键随窗口过期，不积累垃圾
  return {1, tonumber(ARGV[3]) - count - 1}                    -- {放行, 剩余额度}
end
return {0, 0}                                                  -- {拒绝, 0}
"""
```

### Prometheus 指标

**为什么**：`runtime_metrics` 是进程内存单例，多 worker 后数据分散不可聚合，也无法被标准监控栈消费。

**怎么做**：引入 `prometheus-client`，把模型耗时映射为 Histogram、重试/成败映射为 Counter，在 `app/api.py`（或第 5 步后的 `routers/system.py`）加 `/metrics` 端点；与已有结构化日志、request_id 串成完整可观测性叙事。

### Alembic 数据库迁移

**为什么**：MySQL schema 靠 `scripts/init_mysql_schema.py` 手工初始化，无版本管理。

**怎么做**：`alembic init migrations` → 以现有 schema 为 base 版本（`alembic stamp head`）→ 后续变更走迁移脚本。注意本项目是裸 SQL 无 ORM，autogenerate 需要补一层仅用于迁移的 metadata 定义，或接受手写迁移。

### 明确不做

- **TypeScript 改造**——投入大，简历几乎不加分。
- **K8s / 多实例 / 微服务**——对该项目规模是过度设计，能说清「为什么单体够用」比硬拆更分。
- **PDF 图片/表格深度解析**（MinerU 等）——依赖重、收益不确定；真要做，先用第 1 步的评估体系验证收益再投入。

---

## 收尾：执行节奏建议

1. **每项一个独立分支 + PR**（哪怕单人项目），commit message 写清动机——git 历史本身就是简历材料。
2. **每完成一步，把「面试怎么讲」沉淀进 README 或笔记**，并补上量化数字（首 token 延迟、指标差值、重试次数）——简历话术里的数字只能在做的时候采集，事后补不出来。
3. 顺序可微调，但两条先后逻辑不要动：**第 0 步先修（真 bug）、第 1 步先于一切检索调优（评估是依据）**。

---

*本手册基于 ScholarFlow 仓库 2026-08 的代码现状编写：插入位置、函数签名、行号均对照真实文件核实。代码骨架可直接插入使用，但与仓库演进产生出入时以仓库实际状态为准；标注「骨架 / 照抄」的段落请按上下文补全。*
