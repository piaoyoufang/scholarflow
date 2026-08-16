# 导入uuid4，用于生成全局唯一会话thread_id
from uuid import uuid4
# httpx：http客户端库，streamlit前端调用FastAPI后端接口
import httpx
# streamlit网页UI库，快速构建AI应用前端页面
import streamlit as st

# 从项目配置模块读取配置对象settings
from app.config import settings

# 读取后端API基础地址，rstrip("/")去除末尾斜杠，防止拼接路径出现 "//"
API_BASE_URL = settings.api_base_url.rstrip("/")
# 认证相关session_state字段列表，登录保存、退出登录清空复用该列表
AUTH_KEYS = [
    "user_id",               # 用户唯一id
    "access_token",          # 短期访问令牌，调用接口鉴权
    "expires_at",            # access_token过期时间
    "refresh_token",         # 刷新令牌，用来获取新access_token
    "refresh_expires_at",    # refresh_token过期时间
]



APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700;800;900&display=swap');
:root {
    --sf-bg: #0b1020;
    --sf-bg-2: #111a32;
    --sf-surface: rgba(255,255,255,.94);
    --sf-surface-strong: #ffffff;
    --sf-text: #0f172a;
    --sf-muted: #64748b;
    --sf-border: rgba(148,163,184,.24);
    --sf-primary: #3b82f6;
    --sf-primary-dark: #1d4ed8;
    --sf-cyan: #06b6d4;
    --sf-violet: #7c3aed;
    --sf-green: #10b981;
    --sf-orange: #f59e0b;
    --sf-shadow: 0 24px 70px rgba(2, 6, 23, 0.18);
    --sf-shadow-soft: 0 14px 34px rgba(15, 23, 42, 0.10);
    --sf-radius-xl: 30px;
    --sf-radius-lg: 22px;
    --sf-radius-md: 16px;
}
html, body, [class*="css"] { font-family: 'Noto Sans SC', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.stApp {
    background:
        radial-gradient(circle at 8% 8%, rgba(59,130,246,.38), transparent 24rem),
        radial-gradient(circle at 88% 12%, rgba(124,58,237,.28), transparent 28rem),
        radial-gradient(circle at 72% 82%, rgba(6,182,212,.16), transparent 28rem),
        linear-gradient(135deg, #080d1a 0%, #111827 42%, #0f172a 100%);
    color: var(--sf-text);
}
.block-container { max-width: 1240px; padding-top: 2rem; padding-bottom: 4rem; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { right: 1rem; }
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, rgba(15,23,42,.98), rgba(30,41,59,.96));
    border-right: 1px solid rgba(255,255,255,.10);
}
[data-testid="stSidebar"] * { color: rgba(255,255,255,.92) !important; }
[data-testid="stSidebar"] .stCaptionContainer,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: rgba(226,232,240,.70) !important; }
[data-testid="stSidebar"] code {
    display: block;
    padding: 10px 12px !important;
    border-radius: 14px !important;
    background: rgba(255,255,255,.08) !important;
    border: 1px solid rgba(255,255,255,.12) !important;
    color: #bfdbfe !important;
}
.sf-shell {
    padding: 1px;
    border-radius: 34px;
    background: linear-gradient(135deg, rgba(255,255,255,.30), rgba(255,255,255,.06));
    box-shadow: var(--sf-shadow);
}
.sf-hero {
    position: relative;
    overflow: hidden;
    min-height: 310px;
    padding: 36px 38px;
    border-radius: 32px;
    background:
        linear-gradient(135deg, rgba(255,255,255,.96), rgba(239,246,255,.92) 54%, rgba(224,242,254,.90)),
        radial-gradient(circle at 86% 18%, rgba(59,130,246,.22), transparent 20rem);
    border: 1px solid rgba(255,255,255,.62);
}
.sf-hero:before {
    content: "";
    position: absolute;
    width: 430px;
    height: 430px;
    right: -150px;
    top: -130px;
    border-radius: 999px;
    background: radial-gradient(circle, rgba(59,130,246,.28), rgba(124,58,237,.16), transparent 68%);
}
.sf-hero:after {
    content: "RAG";
    position: absolute;
    right: 34px;
    bottom: 22px;
    font-size: 110px;
    line-height: 1;
    font-weight: 900;
    letter-spacing: -.08em;
    color: rgba(15,23,42,.045);
}
.sf-eyebrow {
    position: relative;
    z-index: 1;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 13px;
    border-radius: 999px;
    background: rgba(37,99,235,.10);
    color: #1d4ed8;
    border: 1px solid rgba(37,99,235,.16);
    font-size: 13px;
    font-weight: 800;
}
.sf-title {
    position: relative;
    z-index: 1;
    max-width: 820px;
    margin: 18px 0 12px;
    color: #08111f;
    font-size: clamp(38px, 5vw, 68px);
    line-height: 1.05;
    font-weight: 900;
    letter-spacing: -0.06em;
}
.sf-subtitle {
    position: relative;
    z-index: 1;
    max-width: 760px;
    margin: 0;
    color: #475569;
    font-size: 17px;
    line-height: 1.9;
}
.sf-chip-row { position: relative; z-index: 1; display: flex; flex-wrap: wrap; gap: 10px; margin-top: 24px; }
.sf-chip {
    padding: 9px 13px;
    border-radius: 999px;
    color: #0f172a;
    background: rgba(255,255,255,.82);
    border: 1px solid rgba(148,163,184,.28);
    box-shadow: 0 8px 20px rgba(15,23,42,.06);
    font-size: 13px;
    font-weight: 700;
}
.sf-login-layout {
    display: grid;
    grid-template-columns: 1.05fr .95fr;
    gap: 18px;
    margin-top: 18px;
}
.sf-product-preview,
.sf-login-card,
.sf-panel,
.sf-card {
    border-radius: var(--sf-radius-lg);
    background: rgba(255,255,255,.94);
    border: 1px solid rgba(226,232,240,.78);
    box-shadow: var(--sf-shadow-soft);
}
.sf-product-preview { padding: 24px; }
.sf-login-card { padding: 24px; }
.sf-preview-window {
    border-radius: 20px;
    border: 1px solid #e2e8f0;
    overflow: hidden;
    background: #f8fafc;
}
.sf-preview-topbar {
    height: 42px;
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 0 14px;
    border-bottom: 1px solid #e2e8f0;
    background: #ffffff;
}
.sf-dot { width: 9px; height: 9px; border-radius: 999px; background: #cbd5e1; }
.sf-preview-body { display: grid; grid-template-columns: 180px 1fr; min-height: 270px; }
.sf-preview-nav { padding: 16px; background: #0f172a; }
.sf-preview-nav div { height: 30px; border-radius: 10px; background: rgba(255,255,255,.10); margin-bottom: 10px; }
.sf-preview-main { padding: 16px; }
.sf-preview-card { height: 76px; border-radius: 16px; background: #ffffff; border: 1px solid #e2e8f0; margin-bottom: 12px; box-shadow: 0 8px 18px rgba(15,23,42,.05); }
.sf-feature-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 18px 0; }
.sf-feature-card {
    padding: 18px;
    border-radius: 20px;
    background: rgba(255,255,255,.94);
    border: 1px solid rgba(226,232,240,.80);
    box-shadow: 0 12px 30px rgba(15,23,42,.10);
}
.sf-feature-title { color: #0f172a; font-size: 16px; font-weight: 850; margin-bottom: 8px; }
.sf-feature-desc { color: #64748b; font-size: 13.5px; line-height: 1.75; }
.sf-panel { padding: 24px; margin-bottom: 18px; }
.sf-section-title { margin: 12px 0 8px; color: #0f172a; font-size: 26px; font-weight: 900; letter-spacing: -0.04em; }
.sf-section-desc { margin: 0; color: #64748b; font-size: 15px; line-height: 1.8; }
.sf-course-card { padding: 16px 18px; margin: 0 0 18px; border-radius: 20px; background: rgba(255,255,255,.94); border: 1px solid rgba(226,232,240,.82); box-shadow: var(--sf-shadow-soft); }
.sf-status-pill { display: inline-flex; align-items: center; padding: 9px 13px; border-radius: 999px; background: #eff6ff; color: #1d4ed8; border: 1px solid #dbeafe; font-weight: 800; font-size: 13px; }
.sf-empty-hint { padding: 20px 22px; border-radius: 20px; background: rgba(255,255,255,.94); border: 1px dashed #bfdbfe; color: #475569; box-shadow: 0 10px 28px rgba(15,23,42,.06); line-height: 1.75; }
.sf-callout { padding: 15px 18px; border-radius: 18px; background: #eff6ff; border: 1px solid #bfdbfe; color: #1e3a8a; line-height: 1.7; margin: 10px 0 16px; }
.sf-status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 999px; background: #2563eb; margin-right: 8px; }
.sf-doc-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.sf-doc-card { padding: 18px; border-radius: 20px; background: #ffffff; border: 1px solid #e2e8f0; box-shadow: 0 10px 26px rgba(15,23,42,.07); }
.sf-doc-title { font-size: 16px; font-weight: 850; color: #0f172a; margin-bottom: 8px; }
.sf-doc-meta { color: #64748b; font-size: 13px; line-height: 1.8; word-break: break-all; }
h1,h2,h3 { letter-spacing: -0.035em; }
hr { margin: 1.4rem 0; border-color: rgba(203,213,225,.65); }
small,.stCaptionContainer { color: #64748b !important; }
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 8px; padding: 8px; border-radius: 20px; background: rgba(255,255,255,.92); border: 1px solid rgba(226,232,240,.82); box-shadow: var(--sf-shadow-soft); }
[data-testid="stTabs"] [data-baseweb="tab"] { min-height: 46px; padding: 0 16px; border-radius: 14px; color: #475569; font-weight: 800; }
[data-testid="stTabs"] [aria-selected="true"] { background: linear-gradient(135deg, #0f172a, #1e40af); color: #ffffff !important; }
.stButton > button,.stDownloadButton > button,button[kind="primary"] { min-height: 44px; border-radius: 14px !important; border: 1px solid #1d4ed8 !important; background: linear-gradient(135deg, #2563eb, #1d4ed8) !important; color: #ffffff !important; font-weight: 800 !important; box-shadow: 0 12px 28px rgba(37,99,235,.26) !important; transition: transform .18s ease, box-shadow .18s ease, background .18s ease; }
.stButton > button:hover,.stDownloadButton > button:hover { transform: translateY(-1px); box-shadow: 0 16px 34px rgba(37,99,235,.32) !important; }
.stButton > button[kind="secondary"] { background: #ffffff !important; color: #334155 !important; border: 1px solid #dbe3ef !important; box-shadow: 0 8px 20px rgba(15,23,42,.06) !important; }
.stButton > button:disabled { background: #e5e7eb !important; color: #94a3b8 !important; border-color: #e5e7eb !important; box-shadow: none !important; }
[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea,[data-testid="stSelectbox"] div[data-baseweb="select"] > div,[data-testid="stNumberInput"] input { min-height: 44px; border-radius: 14px !important; border-color: #dbe3ef !important; background: #ffffff !important; box-shadow: 0 8px 20px rgba(15,23,42,.045) !important; }
[data-testid="stTextInput"] input:focus,[data-testid="stTextArea"] textarea:focus { border-color: #60a5fa !important; box-shadow: 0 0 0 4px rgba(37,99,235,.12) !important; }
[data-testid="stFileUploader"] section { border-radius: 20px !important; border: 1px dashed #93c5fd !important; background: #f8fbff !important; }
[data-testid="stForm"],[data-testid="stExpander"],[data-testid="stDataFrame"],.stAlert { border-radius: 18px !important; }
[data-testid="stDataFrame"] { overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 10px 26px rgba(15,23,42,.06); }
[data-testid="stMetric"] { padding: 20px; border-radius: 20px; background: #ffffff; border: 1px solid #e2e8f0; box-shadow: var(--sf-shadow-soft); }
[data-testid="stMetricValue"] { color: #0f172a; font-weight: 900; }
[data-testid="stMetricLabel"] { color: #64748b; }
[data-testid="stChatMessage"] { border-radius: 20px; padding: 14px 16px; background: #ffffff; border: 1px solid #e2e8f0; box-shadow: 0 10px 24px rgba(15,23,42,.06); }
[data-testid="stChatInput"] textarea { border-radius: 18px !important; border: 1px solid #dbe3ef !important; box-shadow: 0 16px 36px rgba(15,23,42,.16) !important; }
[data-testid="stSidebar"] .stButton > button { border-color: rgba(255,255,255,.16) !important; background: rgba(255,255,255,.08) !important; color: #f8fafc !important; box-shadow: none !important; }
*:focus-visible { outline: 3px solid rgba(96,165,250,.34) !important; outline-offset: 2px !important; }
@media (max-width: 960px) { .sf-login-layout { grid-template-columns: 1fr; } .sf-feature-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .sf-doc-grid { grid-template-columns: 1fr; } .sf-hero { min-height: auto; padding: 28px; } }
@media (max-width: 560px) { .block-container { padding-left: 1rem; padding-right: 1rem; } .sf-feature-grid { grid-template-columns: 1fr; } [data-testid="stTabs"] [data-baseweb="tab-list"] { overflow-x: auto; flex-wrap: nowrap; } .sf-title { font-size: 36px; } }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; scroll-behavior: auto !important; } }
</style>
"""


def apply_theme() -> None:
    """Inject global CSS for a polished Streamlit product UI."""
    st.markdown(APP_CSS, unsafe_allow_html=True)


def render_hero(title: str, subtitle: str, eyebrow: str = "RAG Course Assistant", chips: list[str] | None = None) -> None:
    """Render the unified product hero area."""
    chips = chips or ["课程知识库", "RAG 溯源问答", "学习计划 Agent", "自动出题", "教师分析看板"]
    chip_html = "".join(f'<span class="sf-chip">{chip}</span>' for chip in chips)
    st.markdown(f"""
        <div class="sf-shell">
            <section class="sf-hero">
                <div class="sf-eyebrow">{eyebrow}</div>
                <h1 class="sf-title">{title}</h1>
                <p class="sf-subtitle">{subtitle}</p>
                <div class="sf-chip-row">{chip_html}</div>
            </section>
        </div>
        """, unsafe_allow_html=True)


def render_login_showcase() -> None:
    """Render a product preview beside login form."""
    st.markdown(
        """
        <div class="sf-product-preview">
            <div class="sf-eyebrow">项目演示预览</div>
            <h2 class="sf-section-title">从课程资料到智能学习闭环</h2>
            <p class="sf-section-desc">教师上传资料构建课程知识库，学生基于资料问答、生成计划与练习，教师通过分析看板持续优化课程内容。</p>
            <div class="sf-preview-window" style="margin-top:18px;">
                <div class="sf-preview-topbar"><span class="sf-dot"></span><span class="sf-dot"></span><span class="sf-dot"></span></div>
                <div class="sf-preview-body">
                    <div class="sf-preview-nav"><div></div><div></div><div></div><div></div></div>
                    <div class="sf-preview-main"><div class="sf-preview-card"></div><div class="sf-preview-card"></div><div class="sf-preview-card"></div></div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title: str, desc: str, icon: str = "") -> None:
    """Render a consistent feature section header."""
    label = f"{icon} {title}" if icon else title
    st.markdown(f"""
        <div class="sf-panel">
            <div class="sf-eyebrow">{label}</div>
            <h2 class="sf-section-title">{title}</h2>
            <p class="sf-section-desc">{desc}</p>
        </div>
        """, unsafe_allow_html=True)


def render_empty_state(message: str) -> None:
    """Render a polished empty state without changing business logic."""
    st.markdown(f'<div class="sf-empty-hint">{message}</div>', unsafe_allow_html=True)


def render_doc_card(document: dict) -> None:
    """Render one document as a compact card for resume demo quality."""
    filename = document.get("original_name", "未命名资料")
    status = document.get("status", "unknown")
    source_id = document.get("source_id", "")
    file_type = document.get("file_type", "")
    chunk_count = document.get("chunk_count", 0)
    created_at = document.get("created_at", "")
    st.markdown(f"""
        <div class="sf-doc-card">
            <div class="sf-doc-title">{filename}</div>
            <div class="sf-doc-meta">状态：{status} ｜ 类型：{file_type or "未知"} ｜ 切片：{chunk_count} ｜ ID：{source_id}</div>
            <div class="sf-doc-meta">创建时间：{created_at or "-"}</div>
        </div>
        """, unsafe_allow_html=True)


def render_feature_grid() -> None:
    """Render concise product capability cards for resume/demo presentation."""
    st.markdown(
        """
        <div class="sf-feature-grid">
            <div class="sf-feature-card"><div class="sf-feature-title">RAG 课程问答</div><div class="sf-feature-desc">混合检索、Rerank 与引用溯源，让回答基于课程资料。</div></div>
            <div class="sf-feature-card"><div class="sf-feature-title">课程资料入库</div><div class="sf-feature-desc">支持 PDF、Markdown、TXT 上传，异步解析、切块和向量化。</div></div>
            <div class="sf-feature-card"><div class="sf-feature-title">学习 Agent</div><div class="sf-feature-desc">自动生成学习计划、练习题和阶段性学习产出。</div></div>
            <div class="sf-feature-card"><div class="sf-feature-title">教学反馈分析</div><div class="sf-feature-desc">沉淀高频问题、无引用问题和低质量问答，反哺课程建设。</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_callout(message: str) -> None:
    """Render a neutral status callout for guidance and next steps."""
    st.markdown(f'<div class="sf-callout"><span class="sf-status-dot"></span>{message}</div>', unsafe_allow_html=True)

def auth_headers() -> dict[str, str]:
    """所有需要登录的接口都统一从这里拿 Bearer Token 请求头。"""
    # 组装Authorization请求头，带上Bearer令牌
    return {"Authorization": f"Bearer {st.session_state.access_token}"}


def save_auth_data(data: dict) -> None:
    """登录、注册、刷新 Token 成功后，把后端返回的账号会话保存到页面状态。"""
    # 遍历认证字段列表，把后端返回数据存入streamlit会话状态
    for key in AUTH_KEYS:
        st.session_state[key] = data[key]


def clear_auth_data() -> None:
    """退出登录时清空账号相关缓存。"""
    # 循环删除认证相关session状态，pop第二个参数None，key不存在不会抛异常
    for key in AUTH_KEYS:
        st.session_state.pop(key, None)


def response_error(response: httpx.Response) -> str:
    """把 FastAPI 的错误响应转换成页面上能看懂的中文提示。"""
    try:
        # 尝试解析返回json
        detail = response.json().get("detail")
        # 如果拿到detail错误信息，直接返回字符串
        if detail:
            return str(detail)
    except ValueError:
        # 返回不是合法json，捕获解析异常，跳过
        pass
    # 解析失败，返回HTTP状态码作为错误提示
    return f"请求失败，HTTP 状态码：{response.status_code}"


def api_get(path: str, timeout: int = 30) -> httpx.Response:
    """统一发送 GET 请求，path 只写 /courses 这种相对路径。"""
    # 发起get请求，拼接基础地址，带上鉴权头，设置超时时间
    return httpx.get(
        f"{API_BASE_URL}{path}",
        headers=auth_headers(),
        timeout=timeout,
    )


def api_post(path: str, json: dict | None = None, timeout: int = 30) -> httpx.Response:
    """统一发送 POST 请求，避免每个 tab 重复拼接 API_BASE_URL 和 headers。"""
    # json为None时传空字典{}，避免httpx报错
    return httpx.post(
        f"{API_BASE_URL}{path}",
        headers=auth_headers(),
        json=json or {},
        timeout=timeout,
    )


def ensure_chat_state() -> None:
    """初始化 Streamlit 页面状态：会话线程、聊天记录、当前课程。"""
    # 如果session没有thread_id，生成全新uuid会话id
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid4())
    # 如果没有messages聊天消息列表，初始化为空列表
    if "messages" not in st.session_state:
        st.session_state.messages = []
    # 当前选中课程id，初始为空字符串
    if "current_course_id" not in st.session_state:
        st.session_state.current_course_id = ""
    # 当前选中课程名称
    if "current_course_name" not in st.session_state:
        st.session_state.current_course_name = ""
    # 用户在课程中的角色 teacher / student
    if "current_course_role" not in st.session_state:
        st.session_state.current_course_role = ""
    # 最近一次异步任务task_id，方便查询任务状态
    if "last_task_id" not in st.session_state:
        st.session_state.last_task_id = ""
    # 判断会话状态中是否没有保存上一轮用户提问的key
    if "last_question" not in st.session_state:
        # 初始化，把last_question设置为空字符串，st.session_state是streamlit页面全局会话存储，页面刷新不会丢失
        st.session_state.last_question = ""
    # 判断会话状态中是否没有保存上一轮AI回答的key
    if "last_answer" not in st.session_state:
        # 初始化上一轮AI回答，赋值空字符串
        st.session_state.last_answer = ""
    # 保存最近一次问答分析返回的低质量问题列表，供处理表单选择 event_id
    if "low_quality_items" not in st.session_state:
        st.session_state.low_quality_items = []


def load_thread_messages(thread_id: str) -> bool:
    """从后端恢复某个历史会话。"""
    try:
        # 根据thread_id调用接口获取会话详情
        response = api_get(f"/threads/{thread_id}", timeout=30)
    except httpx.RequestError:
        # 网络异常，直接返回False代表加载失败
        return False

    # http状态码非2xx，返回失败
    if not response.is_success:
        return False

    # 解析接口返回json
    data = response.json()
    # 更新session里面thread_id
    st.session_state.thread_id = data["thread_id"]
    # 取出历史对话记录，没有history返回空列表
    st.session_state.messages = data.get("history", [])
    # 返回True代表加载会话成功
    return True


def restore_latest_thread_or_new() -> None:
    """登录后优先恢复最近一次会话；没有历史则创建新会话。"""
    try:
        # 获取该用户全部会话列表
        response = api_get("/threads", timeout=30)
    except httpx.RequestError:
        # 网络异常，直接新建空会话
        st.session_state.thread_id = str(uuid4())
        st.session_state.messages = []
        return

    # 请求成功
    if response.is_success:
        # 获取threads数组，没有返回空列表
        threads = response.json().get("threads", [])
        if threads:
            # 取列表第一条，代表最新会话
            latest_thread_id = threads[0]["thread_id"]
            # 尝试加载该会话，加载成功直接return
            if load_thread_messages(latest_thread_id):
                return

    # 没有会话 / 加载会话失败，新建会话
    st.session_state.thread_id = str(uuid4())
    st.session_state.messages = []


def render_login_page() -> None:
    """未登录时展示登录/注册页面。"""
    left_col, right_col = st.columns([1.18, 0.82], gap="large")

    with left_col:
        render_hero(
            "高校课程AI学习助手平台项目",
            "面向高校课程资料与教学知识库的 RAG 智能问答平台。支持资料入库、引用溯源、多轮问答、学习计划、自动出题和教师分析看板，形成从课程资料到学习反馈的完整闭环。",
            eyebrow="Course RAG Assistant",
            chips=["课程知识库", "混合检索", "引用溯源", "学习 Agent", "教学分析"],
        )
        render_login_showcase()

    with right_col:
        st.markdown('<div class="sf-login-card">', unsafe_allow_html=True)
        st.markdown(
            '<h2 class="sf-section-title">账号登录</h2><p class="sf-section-desc">登录后进入课程空间，管理资料、体验 AI 问答与教学分析。</p>',
            unsafe_allow_html=True,
        )

        # 创建两个标签页：登录、注册
        login_tab, register_tab = st.tabs(["登录", "注册"])

        # 登录tab内部代码块
        with login_tab:
            # st.form表单组件，点击submit才会一次性提交表单数据
            with st.form("login_form"):
                # 用户名输入框，key区分组件状态
                login_username = st.text_input("用户名", key="login_username")
                # 密码输入框，type="password"隐藏输入内容
                login_password = st.text_input("密码", type="password", key="login_password")
                # 表单提交按钮，use_container_width占满整行宽度
                login_submitted = st.form_submit_button("登录", use_container_width=True)

            # 判断表单是否点击提交
            if login_submitted:
                try:
                    # 直接调用登录接口，登录接口不需要auth header
                    response = httpx.post(
                        f"{API_BASE_URL}/auth/login",
                        json={
                            "username": login_username.strip(), # 去除用户名前后空格
                            "password": login_password,
                        },
                        timeout=30,
                    )
                    # 请求成功
                    if response.is_success:
                        # 保存登录返回token信息
                        save_auth_data(response.json())
                        # 初始化聊天相关session状态
                        ensure_chat_state()
                        # 加载最新历史会话
                        restore_latest_thread_or_new()
                        # st.rerun()刷新整个streamlit页面
                        st.rerun()
                    else:
                        # 登录失败，展示错误信息
                        st.error(response_error(response))
                except httpx.RequestError as exc:
                    # 捕获网络异常，打印错误
                    st.error(f"无法连接后端：{exc}")

        # 注册tab代码块
        with register_tab:
            # 注册表单
            with st.form("register_form"):
                register_username = st.text_input("用户名", key="register_username")
                register_password = st.text_input("密码", type="password", key="register_password")
                confirm_password = st.text_input("确认密码", type="password", key="confirm_password")
                register_submitted = st.form_submit_button("注册并登录", use_container_width=True)

            # 点击注册提交按钮
            if register_submitted:
                # 去除用户名前后空格
                username = register_username.strip()
                # 前端校验：两次密码不一致
                if register_password != confirm_password:
                    st.error("两次输入的密码不一致")
                # 前端校验密码长度最少8位
                elif len(register_password) < 8:
                    st.error("密码至少需要 8 个字符")
                else:
                    try:
                        # 请求注册接口
                        response = httpx.post(
                            f"{API_BASE_URL}/auth/register",
                            json={"username": username, "password": register_password},
                            timeout=30,
                        )
                        if response.is_success:
                            # 注册成功直接保存token，自动登录
                            save_auth_data(response.json())
                            ensure_chat_state()
                            restore_latest_thread_or_new()
                            st.rerun()
                        else:
                            st.error(response_error(response))
                    except httpx.RequestError as exc:
                        st.error(f"无法连接后端：{exc}")

        st.markdown("</div>", unsafe_allow_html=True)

def selected_course_id() -> str:
    """读取当前选中的课程 ID。"""
    # 从session取出current_course_id，取不到返回空字符串
    return st.session_state.get("current_course_id", "")


def require_selected_course() -> str | None:
    """业务 tab 的入口校验：没有选课程就提示用户先去“我的课程”。"""
    # 获取当前课程id
    course_id = selected_course_id()
    # 如果课程id为空，弹出警告，返回None
    if not course_id:
        render_empty_state("请先在“我的课程”里创建或选择一门课程，再使用当前功能。")
        return None
    # 显示当前课程信息给用户
    st.caption(
        f"当前课程：{st.session_state.current_course_name} "
        f"｜角色：{st.session_state.current_course_role or '未知'} "
        f"｜课程ID：{course_id}"
    )
    # 返回有效的course_id，供后续接口调用
    return course_id


def render_sidebar() -> None:
    """左侧栏：账号、历史会话、刷新 Token、退出登录。"""
    # 进入侧边栏上下文
    with st.sidebar:
        st.subheader("当前账号")
        # 以代码块样式展示user_id
        st.code(st.session_state.user_id, language=None)
        # 展示两个token到期时间
        st.caption(f"Access Token 到期：{st.session_state.expires_at}")
        st.caption(f"Refresh Token 到期：{st.session_state.refresh_expires_at}")

        # 分割线
        st.divider()
        st.subheader("历史会话")
        try:
            # 获取用户全部会话列表
            threads_response = api_get("/threads", timeout=30)
            if threads_response.is_success:
                threads = threads_response.json().get("threads", [])
            else:
                threads = []
                st.caption(f"读取历史会话失败：{response_error(threads_response)}")
        except httpx.RequestError as exc:
            threads = []
            st.caption(f"读取历史会话失败：{exc}")

        # 如果存在会话
        if threads:
            # 提取全部thread_id组成选项列表
            thread_options = [item["thread_id"] for item in threads]
            # 字典映射 thread_id → 会话完整对象
            thread_map = {item["thread_id"]: item for item in threads}
            # 如果当前内存中的thread_id不在后端返回列表，插入选项最前面
            if st.session_state.thread_id not in thread_options:
                thread_options.insert(0, st.session_state.thread_id)
            # 获取当前选中会话的下标
            current_index = thread_options.index(st.session_state.thread_id)
            # 下拉选择会话组件
            selected_thread_id = st.selectbox(
                "选择会话",
                options=thread_options,
                index=current_index,
                # format_func自定义下拉框显示文本
                format_func=lambda tid: (
                    "当前新会话（尚未保存）"
                    if tid not in thread_map
                    else f"{thread_map[tid].get('title', '新会话')}"
                         f"（{thread_map[tid].get('history_count', 0)}条）"
                ),
            )
            # 用户切换下拉框选中的会话
            if selected_thread_id != st.session_state.thread_id:
                # 加载目标会话消息，成功就刷新页面
                if load_thread_messages(selected_thread_id):
                    st.rerun()
                else:
                    st.error("读取该会话失败，请确认后端服务正常。")
        else:
            # 用户没有任何历史会话
            st.caption("当前账号还没有保存过历史会话。")

        st.divider()
        # 新建会话按钮
        if st.button("新建会话", use_container_width=True):
            # 生成全新thread_id，清空本地消息，页面刷新
            st.session_state.thread_id = str(uuid4())
            st.session_state.messages = []
            st.rerun()

        # 清空当前会话按钮
        if st.button("清空当前会话", use_container_width=True):
            try:
                # 如果本地有消息，调用后端删除该thread会话
                if st.session_state.messages:
                    response = httpx.delete(
                        f"{API_BASE_URL}/threads/{st.session_state.thread_id}",
                        headers=auth_headers(),
                        timeout=30,
                    )
                    # 删除接口失败，报错并且停止执行后续代码
                    if not response.is_success:
                        st.error(response_error(response))
                        st.stop()
                # 删除完成，生成新会话，清空消息，刷新页面
                st.session_state.thread_id = str(uuid4())
                st.session_state.messages = []
                st.rerun()
            except httpx.RequestError as exc:
                st.error(f"清空失败，无法连接后端：{exc}")

        # 划分两列布局
        refresh_column, logout_column = st.columns(2)
        with refresh_column:
            # 手动刷新token按钮
            if st.button("刷新 Token", use_container_width=True):
                try:
                    # 请求token刷新接口
                    response = httpx.post(
                        f"{API_BASE_URL}/auth/refresh",
                        json={"refresh_token": st.session_state.refresh_token},
                        timeout=30,
                    )
                    if response.is_success:
                        # 保存新拿到的token，页面刷新
                        save_auth_data(response.json())
                        st.rerun()
                    else:
                        st.error(response_error(response))
                except httpx.RequestError as exc:
                    st.error(f"刷新失败：{exc}")

        with logout_column:
            # 退出登录按钮
            if st.button("退出登录", use_container_width=True):
                try:
                    # 请求后端logout接口
                    response = api_post(
                        "/auth/logout",
                        json={"refresh_token": st.session_state.refresh_token},
                        timeout=30,
                    )
                    if response.is_success:
                        # 清空认证信息
                        clear_auth_data()
                        # 清空聊天、课程相关全部session状态
                        for key in [
                            "thread_id",
                            "messages",
                            "current_course_id",
                            "current_course_name",
                            "current_course_role",
                            "last_task_id",
                        ]:
                            st.session_state.pop(key, None)
                        st.rerun()
                    else:
                        st.error(response_error(response))
                except httpx.RequestError as exc:
                    st.error(f"退出失败：{exc}")


def render_courses_tab() -> None:
    """Tab 1：创建课程、选择课程。"""
    render_section_header("我的课程", "创建或选择当前课程，后续知识库、问答、出题和分析都会围绕这门课工作。")

    # 创建课程表单
    with st.form("create_course_form"):
        course_name = st.text_input("课程名称", placeholder="例如：AI应用开发实战课")
        description = st.text_area("课程说明", placeholder="这门课包含 RAG、Agent、评估、部署等资料。")
        submitted = st.form_submit_button("创建课程", use_container_width=True)

    # 点击创建课程按钮
    if submitted:
        # 判断课程名称去除空格后是否为空
        if not course_name.strip():
            st.error("课程名称不能为空")
        else:
            try:
                # 调用创建课程接口
                response = api_post(
                    "/courses",
                    json={"course_name": course_name.strip(), "description": description.strip()},
                    timeout=30,
                )
                if response.is_success:
                    course = response.json().get("course", {})
                    # 创建成功，自动设置为当前课程，角色为teacher
                    st.session_state.current_course_id = course.get("course_id", "")
                    st.session_state.current_course_name = course.get("course_name", course_name.strip())
                    st.session_state.current_course_role = "teacher"
                    st.success("课程创建成功，并已自动选为当前课程。")
                    st.rerun()
                else:
                    st.error(response_error(response))
            except httpx.RequestError as exc:
                st.error(f"创建课程失败：{exc}")

    st.divider()
    st.markdown("### 选择当前课程")
    try:
        # 获取用户所有课程列表
        response = api_get("/courses", timeout=30)
        if not response.is_success:
            st.error(f"读取课程失败：{response_error(response)}")
            return
        courses = response.json().get("courses", [])
    except httpx.RequestError as exc:
        st.error(f"读取课程失败：{exc}")
        return

    # 用户没有任何课程
    if not courses:
        render_empty_state("你还没有课程。可以先在上方创建课程，或让老师把你的 user_id 添加为课程成员。")
        return

    # 构造下拉框显示文本数组
    labels = [
        f"{course.get('course_name', '未命名课程')}｜{course.get('role_in_course', 'unknown')}｜{course.get('course_id', '')}"
        for course in courses
    ]
    default_index = 0
    current_id = selected_course_id()
    # 循环找到当前选中课程对应的数组下标
    for index, course in enumerate(courses):
        if course.get("course_id") == current_id:
            default_index = index
            break

    # 下拉选择课程组件，options传下标数字
    selected_index = st.selectbox(
        "选择当前课程",
        options=list(range(len(courses))),
        index=default_index,
        format_func=lambda index: labels[index],
    )
    # 根据选中下标取出课程对象
    selected = courses[selected_index]
    # 更新session，切换当前课程
    st.session_state.current_course_id = selected.get("course_id", "")
    st.session_state.current_course_name = selected.get("course_name", "")
    st.session_state.current_course_role = selected.get("role_in_course", "")

    st.success(f"当前课程：{st.session_state.current_course_name}")
    # dataframe表格展示全部课程
    st.dataframe(courses, use_container_width=True)



def render_documents_tab() -> None:
    """Tab 2：上传课程资料、查看当前课程知识库文档列表。"""
    render_section_header("课程知识库", "上传 PDF、Markdown 或 TXT 资料，后台自动解析、切块并写入向量库。")
    course_id = require_selected_course()
    if not course_id:
        return

    st.markdown("### 上传课程资料")
    st.caption("老师上传 Markdown、TXT 或 PDF 后，后端会返回 task_id，并在后台异步完成解析、切块、向量入库。")
    uploaded_file = st.file_uploader(
        "选择课程资料文件",
        type=["pdf", "txt", "md"],
        accept_multiple_files=False,
        key=f"course_upload_{course_id}",
    )
    if st.button(
        "上传并创建入库任务",
        disabled=uploaded_file is None,
        use_container_width=True,
    ):
        try:
            with st.spinner("正在上传文件并创建后台任务..."):
                response = httpx.post(
                    f"{API_BASE_URL}/courses/{course_id}/documents/upload-async",
                    headers=auth_headers(),
                    files={
                        "file": (
                            uploaded_file.name,
                            uploaded_file.getvalue(),
                            uploaded_file.type or "application/octet-stream",
                        )
                    },
                    timeout=120,
                )
            if response.is_success:
                data = response.json()
                st.session_state.last_task_id = data.get("task_id", "")
                st.success(f"上传成功，任务ID：{st.session_state.last_task_id}")
                render_empty_state("接下来去“上传任务”tab 查询任务进度；任务 success 后再回来刷新课程知识库列表。")
            else:
                st.error(response_error(response))
        except httpx.RequestError as exc:
            st.error(f"上传失败，无法连接后端：{exc}")

    st.divider()
    st.markdown("### 当前课程文档列表")
    try:
        response = api_get(f"/courses/{course_id}/documents", timeout=30)
        if response.is_success:
            documents = response.json().get("documents", [])
            if documents:
                # 如果文档列表不为空，渲染表格展示文档元数据
                if documents:
                    st.markdown("### 资料卡片")
                    st.markdown('<div class="sf-doc-grid">', unsafe_allow_html=True)
                    for document in documents:
                        render_doc_card(document)
                    st.markdown('</div>', unsafe_allow_html=True)
                    # Streamlit表格展示文档列表，宽度占满容器
                    st.markdown("### 资料明细")
                    st.dataframe(documents, use_container_width=True)
                    # 增加二级标题：资料操作区域
                    st.markdown("### 资料操作")
                    # 遍历每一条文档记录
                    for document in documents:
                        # 取出文档唯一标识
                        source_id = document["source_id"]
                        # 原始上传文件名
                        filename = document["original_name"]
                        # 文档处理状态：processing / success / failed
                        status = document["status"]

                        # 折叠面板：标题展示 文件名｜状态｜source_id，点击展开操作按钮
                        with st.expander(f"{filename}｜{status}｜{source_id}"):
                            # 切分为左右两列布局，col1重新入库，col2删除
                            col1, col2 = st.columns(2)

                            # 第一列：重新入库按钮
                            with col1:
                                # key必须带source_id，streamlit依靠key区分循环里多个按钮，防止组件冲突
                                if st.button("重新入库", key=f"reingest_{source_id}"):
                                    # POST请求后端reingest接口，触发文档重新向量化任务
                                    response = api_post(
                                        f"/courses/{course_id}/documents/{source_id}/reingest",
                                        timeout=30,
                                    )
                                    # 判断http请求成功
                                    if response.is_success:
                                        data = response.json()
                                        # 将返回的task_id存入session_state，方便页面其他地方读取任务id轮询进度
                                        st.session_state.last_task_id = data.get("task_id", "")
                                        st.success(f"已创建重新入库任务：{st.session_state.last_task_id}")
                                    else:
                                        # 请求失败，展示后端返回的错误信息
                                        st.error(response_error(response))

                            # 第二列：删除资料按钮
                            with col2:
                                if st.button("删除资料", key=f"delete_{source_id}"):
                                    # 发送DELETE请求，调用后端删除文档接口，带上鉴权请求头
                                    response = httpx.delete(
                                        f"{API_BASE_URL}/courses/{course_id}/documents/{source_id}",
                                        headers=auth_headers(),
                                        timeout=30,
                                    )
                                    if response.is_success:
                                        st.success("资料已删除")
                                        # 页面强制刷新，重新拉取课程文档列表，删掉的条目立刻消失
                                        st.rerun()
                                    else:
                                        st.error(response_error(response))
            else:
                render_empty_state("这门课程暂时没有入库文档。请先上传课程资料，系统会自动完成解析、切块和向量入库。")
        else:
            st.error(response_error(response))
    except httpx.RequestError as exc:
        st.error(f"读取课程知识库失败：{exc}")


def render_qa_tab() -> None:
    """Tab 3：课程级 AI 问答。"""
    render_section_header("AI 问答", "基于当前课程资料进行带引用问答，支持多轮追问与回答反馈。")
    course_id = require_selected_course()
    if not course_id:
        return

    # 先渲染历史消息，再渲染输入框。
    # 用户提交后只写入 session_state 并 st.rerun，避免新消息跑到输入框下面。
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if st.session_state.get("last_question") and st.session_state.get("last_answer"):
        st.markdown("### 对上一条回答反馈")
        col1, col2 = st.columns(2)

        with col1:
            if st.button("有帮助", use_container_width=True):
                response = api_post(
                    f"/courses/{course_id}/feedback",
                    json={
                        "thread_id": st.session_state.thread_id,
                        "question": st.session_state.last_question,
                        "answer": st.session_state.last_answer,
                        "rating": "up",
                        "reason": "",
                        "comment": "",
                    },
                    timeout=30,
                )
                if response.is_success:
                    st.success("感谢反馈")
                else:
                    st.error(response_error(response))

        with col2:
            with st.form("down_feedback_form"):
                reason = st.selectbox(
                    "没帮助的原因",
                    ["答案不准确", "没有引用", "引用不相关", "回答太少", "没看懂", "其他"],
                )
                comment = st.text_area("补充说明")
                submitted = st.form_submit_button("没帮助", use_container_width=True)
            if submitted:
                response = api_post(
                    f"/courses/{course_id}/feedback",
                    json={
                        "thread_id": st.session_state.thread_id,
                        "question": st.session_state.last_question,
                        "answer": st.session_state.last_answer,
                        "rating": "down",
                        "reason": reason,
                        "comment": comment,
                    },
                    timeout=30,
                )
                if response.is_success:
                    st.success("反馈已记录")
                else:
                    st.error(response_error(response))


    question = st.chat_input("输入课程相关问题")
    if not question:
        return
    # 用户问题可以立刻保存
    st.session_state.last_question = question
    st.session_state.messages.append({"role": "user", "content": question})

    try:
        with st.spinner("正在检索当前课程知识库并生成回答..."):
            response = api_post(
                f"/courses/{course_id}/ask",
                json={"question": question, "thread_id": st.session_state.thread_id},
                timeout=180,
            )
        if not response.is_success:
            st.session_state.messages.append(
                {"role": "assistant", "content": f"请求失败：{response_error(response)}"}
            )
            st.rerun()

        result = response.json()
        answer_text = str(result.get("answer", result)) if isinstance(result, dict) else str(result)
        citations = result.get("citations", []) if isinstance(result, dict) else []
        if citations:
            citation_lines = ["\n\n#### 引用来源"]
            for citation in citations:
                source = citation.get("source_name", citation.get("source", "未知来源"))
                locator = citation.get("locator", "")
                quote = citation.get("quote", citation.get("content", ""))
                citation_lines.append(f"- {source} {locator}: {quote}")
            answer_text += "\n".join(citation_lines)

        # 到这里 answer_text 才真正生成完成。
        # 所以 last_answer 必须放在这里赋值，不能放在调用接口之前。
        st.session_state.last_answer = answer_text
        st.session_state.messages.append({"role": "assistant", "content": answer_text})
        st.rerun()
    except httpx.RequestError as exc:
        st.session_state.messages.append(
            {"role": "assistant", "content": f"提问失败，无法连接后端：{exc}"}
        )
        st.rerun()

def render_learning_plan_tab() -> None:
    """Tab 4：学习计划 Agent。"""
    render_section_header("学习计划", "输入学习目标，由 Agent 按天拆解任务、产出和难度节奏。")
    course_id = require_selected_course()
    if not course_id:
        return

    # 生成学习计划表单
    with st.form("learning_plan_form"):
        goal = st.text_area("学习目标", placeholder="例如：7天内掌握本课程的 RAG 项目开发流程")
        col1, col2, col3 = st.columns(3)
        with col1:
            days = st.number_input("计划天数", min_value=1, max_value=30, value=7)
        with col2:
            daily_minutes = st.number_input("每天学习分钟数", min_value=10, max_value=600, value=60)
        with col3:
            difficulty = st.selectbox("难度", ["beginner", "intermediate", "advanced"])
        submitted = st.form_submit_button("生成学习计划", use_container_width=True)

    # 用户点击生成计划
    if submitted:
        if not goal.strip():
            st.error("学习目标不能为空")
            return
        try:
            # 请求学习计划agent接口
            response = api_post(
                f"/courses/{course_id}/agents/learning-plan",
                json={
                    "goal": goal.strip(),
                    "days": int(days),
                    "difficulty": difficulty,
                    "daily_minutes": int(daily_minutes),
                },
                timeout=180,
            )
            if response.is_success:
                data = response.json()
                st.success("学习计划生成成功")
                # 循环渲染每一天学习计划，expander折叠面板
                for day in data.get("days", []):
                    with st.expander(f"第 {day.get('day')} 天：{day.get('topic', '')}", expanded=True):
                        for task in day.get("tasks", []):
                            st.write(f"- {task}")
                        if day.get("expected_output"):
                            st.markdown(f"**预期产出：** {day.get('expected_output')}")
            else:
                st.error(response_error(response))
        except httpx.RequestError as exc:
            st.error(f"生成学习计划失败：{exc}")


def render_quiz_tab() -> None:
    """Tab 5：自动出题 Agent。"""
    render_section_header("自动出题", "围绕指定主题自动生成选择题、判断题、简答题或面试题。")
    course_id = require_selected_course()
    if not course_id:
        return

    # 出题表单
    with st.form("quiz_form"):
        topic = st.text_input("出题主题", placeholder="例如：RAG 检索增强生成")
        col1, col2, col3 = st.columns(3)
        with col1:
            question_count = st.number_input("题目数量", min_value=1, max_value=20, value=5)
        with col2:
            question_type = st.selectbox("题型", ["single_choice", "true_false", "short_answer", "interview"])
        with col3:
            difficulty = st.selectbox("难度", ["easy", "medium", "hard"])
        submitted = st.form_submit_button("生成题目", use_container_width=True)

    # 点击生成题目
    if submitted:
        if not topic.strip():
            st.error("出题主题不能为空")
            return
        try:
            # 调用出题agent接口
            response = api_post(
                f"/courses/{course_id}/agents/quiz",
                json={
                    "topic": topic.strip(),
                    "question_count": int(question_count),
                    "question_type": question_type,
                    "difficulty": difficulty,
                },
                timeout=180,
            )
            if response.is_success:
                data = response.json()
                st.success("题目生成成功")
                # 遍历每一道题目，折叠面板展示
                for index, item in enumerate(data.get("items", []), start=1):
                    with st.expander(f"第 {index} 题：{item.get('question', '')}", expanded=True):
                        options = item.get("options", [])
                        for option in options:
                            st.write(f"- {option}")
                        st.markdown(f"**参考答案：** {item.get('answer', '')}")
                        st.markdown(f"**解析：** {item.get('explanation', '')}")
            else:
                st.error(response_error(response))
        except httpx.RequestError as exc:
            st.error(f"生成题目失败：{exc}")


def render_retrieval_debug_tab() -> None:
    """Tab 6：教师查看检索召回过程。"""
    render_section_header("检索可视化", "教师可查看检索召回和排序过程，定位知识库命中效果。")
    course_id = require_selected_course()
    if not course_id:
        return

    st.caption("这个页面调用 POST /courses/{course_id}/retrieval/debug。后端要求课程教师访问，学生账号返回 403 是正常权限控制。")
    query = st.text_input("输入要调试的检索问题", placeholder="例如：RAG 的核心流程是什么？")
    # 点击查看召回结果按钮
    if st.button("查看召回结果", use_container_width=True):
        if not query.strip():
            st.error("检索问题不能为空")
            return
        try:
            # 请求检索调试接口
            response = api_post(
                f"/courses/{course_id}/retrieval/debug",
                json={"question": query.strip(), "thread_id": st.session_state.thread_id},
                timeout=60,
            )
            if response.is_success:
                data = response.json()
                if isinstance(data, dict):
                    # 多key兼容取召回文档数组
                    rows = data.get("items") or data.get("results") or data.get("documents") or []
                    if rows:
                        st.dataframe(rows, use_container_width=True)
                    st.json(data)
                else:
                    st.write(data)
            else:
                st.error(response_error(response))
        except httpx.RequestError as exc:
            st.error(f"检索调试失败：{exc}")



def render_tasks_tab() -> None:
    """Tab 7：查看课程异步上传任务，并支持按 task_id 查询。"""
    render_section_header("上传任务", "查看课程资料入库任务状态，快速定位解析或向量化进度。")
    course_id = require_selected_course()
    if not course_id:
        return

    st.markdown("### 当前课程最近任务")
    try:
        response = api_get(f"/courses/{course_id}/tasks", timeout=30)
        if response.is_success:
            tasks = response.json().get("tasks", [])
            if tasks:
                st.dataframe(tasks, use_container_width=True)
            else:
                render_empty_state("当前课程还没有上传任务。上传课程资料后，这里会展示解析和入库进度。")
        else:
            st.error(response_error(response))
    except httpx.RequestError as exc:
        st.error(f"读取课程任务失败：{exc}")

    st.divider()
    st.markdown("### 按任务ID查询")
    task_id = st.text_input(
        "任务 ID",
        value=st.session_state.get("last_task_id", ""),
        placeholder="粘贴上传接口返回的 task_id",
    )
    if st.button("查询任务状态", use_container_width=True):
        if not task_id.strip():
            st.error("请先输入 task_id")
            return
        st.session_state.last_task_id = task_id.strip()
        try:
            response = api_get(f"/tasks/{task_id.strip()}", timeout=30)
            if response.is_success:
                st.json(response.json().get("task", response.json()))
            else:
                st.error(response_error(response))
        except httpx.RequestError as exc:
            st.error(f"查询任务失败：{exc}")

def render_analytics_tab() -> None:
    """Tab 8：教师查看课程问答分析。"""
    render_section_header("问答分析", "统计高频问题、无引用问题和低质量问题，辅助教师优化课程资料。")
    course_id = require_selected_course()
    if not course_id:
        return

    st.caption("这个页面调用教师专用 analytics 接口；学生账号看到 403 代表权限控制生效。")
    # 刷新分析数据按钮
    if st.button("刷新分析数据", use_container_width=True):
        # 定义多个分析接口（标题，接口路径）元组列表
        endpoints = [
            ("高频问题", f"/courses/{course_id}/analytics/top-questions"),
            ("无引用问题", f"/courses/{course_id}/analytics/no-citation"),
            ("低质量问题", f"/courses/{course_id}/analytics/low-quality"),
        ]
        # 循环依次请求每个分析接口
        for title, path in endpoints:
            st.markdown(f"### {title}")
            try:
                response = api_get(path, timeout=30)
                if response.is_success:
                    items = response.json().get("items", [])
                    if title == "低质量问题":
                        # 低质量接口返回的每一条记录都包含 event_id。
                        # 保存到 session_state，后面的处理表单可以直接选择，不需要用户手抄 UUID。
                        st.session_state.low_quality_items = items
                    if items:
                        st.dataframe(items, use_container_width=True)
                    else:
                        render_empty_state("暂无数据。课程产生问答记录后，这里会自动展示分析结果。")
                else:
                    st.error(response_error(response))
            except httpx.RequestError as exc:
                st.error(f"读取{title}失败：{exc}")
        # 处理区域加在这里
    st.divider()
    st.markdown("### 处理低质量问题")
    low_quality_items = st.session_state.get("low_quality_items", [])
    if not low_quality_items:
        render_empty_state("请先点击“刷新分析数据”，并确保课程中存在低质量问题记录。")
        return

    event_options = {
        f"{item.get('event_id', '')}｜{item.get('question', '')[:60]}": item.get("event_id", "")
        for item in low_quality_items
        if item.get("event_id")
    }
    if not event_options:
        st.warning("低质量问题列表中没有 event_id，无法更新处理状态。")
        return

    with st.form("process_qa_event_form"):
        selected_event = st.selectbox("选择要处理的问答事件", list(event_options))
        event_id = event_options[selected_event]
        status = st.selectbox("处理状态", ["pending", "processing", "resolved", "ignored"])
        note = st.text_area("处理备注", placeholder="例如：已补充资料并重新入库")
        submitted = st.form_submit_button("更新处理状态")

    if submitted:
        response = httpx.patch(
            f"{API_BASE_URL}/courses/{course_id}/qa-events/{event_id}/status",
            headers=auth_headers(),
            json={"status": status, "note": note},
            timeout=30,
        )
        if response.is_success:
            st.success("处理状态已更新")
        else:
            st.error(response_error(response))

def render_dashboard_tab() -> None:
    render_section_header("课程看板", "汇总文档入库、问答质量、引用率和反馈数据。")
    course_id = require_selected_course()
    if not course_id:
        return

    if st.button("刷新课程看板", use_container_width=True):
        try:
            response = api_get(f"/courses/{course_id}/dashboard", timeout=30)
            if response.is_success:
                data = response.json()

                col1, col2, col3 = st.columns(3)
                col1.metric("文档总数", data.get("document_count", 0))
                col2.metric("成功入库", data.get("success_document_count", 0))
                col3.metric("入库失败", data.get("failed_document_count", 0))

                col4, col5, col6 = st.columns(3)
                col4.metric("问答总数", data.get("qa_count", 0))
                col5.metric("无引用问题", data.get("no_citation_count", 0))
                col6.metric("低质量问题", data.get("low_quality_count", 0))

                col7, col8, col9 = st.columns(3)
                citation_rate = data.get("citation_rate", 0)
                col7.metric("引用率", f"{citation_rate * 100:.1f}%")
                col8.metric("点赞数", data.get("feedback_up_count", 0))
                col9.metric("点踩数", data.get("feedback_down_count", 0))
            else:
                st.error(response_error(response))
        except httpx.RequestError as exc:
            st.error(f"读取课程看板失败：{exc}")


# streamlit全局页面配置：页面标题、图标、宽布局
st.set_page_config(page_title="高校课程AI学习助手平台项目", page_icon="S", layout="wide")
apply_theme()

# 判断未登录：session不存在access_token，渲染登录页面，st.stop终止后续全部代码
if "access_token" not in st.session_state:
    render_login_page()
    st.stop()

# 已经登录，初始化聊天相关session状态
ensure_chat_state()
# 渲染左侧侧边栏
render_sidebar()

# 主页面 Hero
render_hero(
    "高校课程AI学习助手平台项目",
    "面向课程资料、培训文档和项目知识库的带引用问答、学习计划、自动出题与评估诊断系统。",
)
render_feature_grid()

# 获取当前课程名称
current_course = st.session_state.get("current_course_name")
if current_course:
    st.markdown(
        f'<div class="sf-course-card"><span class="sf-status-pill">当前课程：{current_course}｜{st.session_state.current_course_role or "未知角色"}</span></div>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        '<div class="sf-empty-hint">当前还没有选择课程，请先进入“我的课程”创建或选择课程。</div>',
        unsafe_allow_html=True,
    )

# 创建8个tab标签页
tabs = st.tabs([
    "我的课程",
    "课程知识库",
    "AI 问答",
    "学习计划",
    "自动出题",
    "检索可视化",
    "上传任务",
    "问答分析",
    "课程看板",
])

# 每个tab绑定对应的渲染函数
with tabs[0]:
    render_courses_tab()
with tabs[1]:
    render_documents_tab()
with tabs[2]:
    render_qa_tab()
with tabs[3]:
    render_learning_plan_tab()
with tabs[4]:
    render_quiz_tab()
with tabs[5]:
    render_retrieval_debug_tab()
with tabs[6]:
    render_tasks_tab()
with tabs[7]:
    render_analytics_tab()
with tabs[8]:
    render_dashboard_tab()


