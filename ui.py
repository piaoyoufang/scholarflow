# 导入UUID工具，生成全局唯一对话线程ID
from uuid import uuid4

# 导入httpx HTTP客户端，用于前端向后端FastAPI接口发送网络请求
import httpx
# 导入Streamlit网页框架，渲染前端页面、管理页面会话缓存
import streamlit as st

# 导入项目全局配置，读取后端API基础地址
from app.config import settings

# 读取配置中的后端接口根地址，rstrip("/") 去除末尾多余斜杠，避免拼接接口时出现//错误
API_BASE_URL = settings.api_base_url.rstrip("/")

# 常量定义：登录/注册/刷新Token后端返回的5项认证字段，统一管理方便存取、清空
AUTH_KEYS = [
    "user_id",          # 用户全局唯一ID
    "access_token",     # 短期业务鉴权令牌
    "expires_at",       # access_token过期UTC时间
    "refresh_token",    # 长效刷新续期令牌
    "refresh_expires_at"# refresh_token过期UTC时间
]

def auth_headers() -> dict[str, str]:
    """
    封装鉴权请求头函数
    返回标准Bearer鉴权头，所有需要登录校验的接口调用时携带
    """
    return {
        # 拼接标准Authorization请求头，填入页面缓存里的access_token
        "Authorization": f"Bearer {st.session_state.access_token}",
    }

def save_auth_data(data: dict) -> None:
    """
    保存后端返回的账号双Token会话数据到Streamlit页面缓存
    :param data: 后端AccountSessionResponse返回的完整json字典
    """
    # 遍历认证字段常量，批量写入页面会话缓存
    for key in AUTH_KEYS:
        st.session_state[key] = data[key]

def clear_auth_data() -> None:
    """
    清空页面缓存中所有登录认证相关字段，用户退出登录时调用
    pop(key, None)：字段不存在也不会抛出报错，容错处理
    """
    for key in AUTH_KEYS:
        st.session_state.pop(key, None)

def response_error(response: httpx.Response) -> str:
    """
    统一处理后端接口错误响应，格式化友好错误提示给用户
    优先读取FastAPI标准返回的detail错误文本，读取失败则返回HTTP状态码
    :param response: httpx请求返回的响应对象
    :return: 可读错误字符串
    """
    try:
        # 解析接口返回json，取出detail错误详情
        detail = response.json().get("detail")
        if detail:
            return str(detail)
    except ValueError:
        # 响应不是标准json格式，捕获解析异常，跳过
        pass
    # 兜底错误文案，展示HTTP错误状态码
    return f"请求失败，HTTP 状态码：{response.status_code}"

def ensure_chat_state() -> None:
    """
    登录成功后初始化对话状态缓存，不存在则自动创建
    保证页面始终存在thread_id对话线程、messages聊天记录缓存
    """
    # 不存在对话线程ID则生成全新UUID
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid4())
    # 不存在聊天记录列表则初始化空数组
    if "messages" not in st.session_state:
        st.session_state.messages = []

def render_login_page() -> None:
    """
    未登录状态页面渲染函数：展示登录、注册双标签表单
    无合法access_token时执行，阻断聊天页面渲染
    """
    # 页面主标题
    st.title("ScholarFlow")
    # 二级副标题
    st.subheader("账号登录")

    # 创建两个标签页：登录、注册
    login_tab, register_tab = st.tabs(["登录", "注册"])

    # ========== 登录标签页逻辑 ==========
    with login_tab:
        # 创建表单容器，统一提交按钮触发校验
        with st.form("login_form"):
            # 用户名输入框，key区分缓存避免控件冲突
            login_username = st.text_input("用户名", key="login_username")
            # 密码输入框，type="password"隐藏明文
            login_password = st.text_input(
                "密码",
                type="password",
                key="login_password",
            )
            # 表单提交按钮，铺满整行宽度
            login_submitted = st.form_submit_button("登录", use_container_width=True)

        # 用户点击登录按钮后执行逻辑
        if login_submitted:
            try:
                # 向后端登录接口发送POST请求
                response = httpx.post(
                    f"{API_BASE_URL}/auth/login",
                    json={
                        # 去除用户名首尾空格，标准化格式
                        "username": login_username.strip(),
                        "password": login_password,
                    },
                    timeout=30, # 请求超时30秒
                )
                # 判断接口2xx成功响应
                if response.is_success:
                    # 把后端返回的双Token账号信息存入页面缓存
                    save_auth_data(response.json())
                    # 登录重置对话线程、清空历史消息，隔离不同账号聊天数据
                    st.session_state.thread_id = str(uuid4())
                    st.session_state.messages = []
                    # 强制页面刷新，跳转聊天主页
                    st.rerun()
                else:
                    # 接口返回4xx/5xx错误，展示格式化错误提示
                    st.error(response_error(response))
            except httpx.RequestError as exc:
                # 捕获网络异常（连不上后端、超时、断网）
                st.error(f"无法连接后端：{exc}")

    # ========== 注册标签页逻辑 ==========
    with register_tab:
        # 注册表单容器
        with st.form("register_form"):
            register_username = st.text_input("用户名", key="register_username")
            # 密码输入框
            register_password = st.text_input(
                "密码",
                type="password",
                key="register_password",
            )
            # 二次确认密码输入框，校验两次密码一致
            confirm_password = st.text_input(
                "确认密码",
                type="password",
                key="confirm_password",
            )
            # 注册提交按钮
            register_submitted = st.form_submit_button(
                "注册并登录",
                use_container_width=True,
            )

        # 用户点击注册执行校验与请求
        if register_submitted:
            # 标准化用户名，去除首尾空格
            username = register_username.strip()
            # 校验1：两次输入密码不一致
            if register_password != confirm_password:
                st.error("两次输入的密码不一致")
            # 校验2：密码长度不足8位，不符合后端规则
            elif len(register_password) < 8:
                st.error("密码至少需要 8 个字符")
            else:
                try:
                    # 调用后端注册接口
                    response = httpx.post(
                        f"{API_BASE_URL}/auth/register",
                        json={
                            "username": username,
                            "password": register_password,
                        },
                        timeout=30,
                    )
                    if response.is_success:
                        # 注册成功保存会话缓存，重置对话
                        save_auth_data(response.json())
                        st.session_state.thread_id = str(uuid4())
                        st.session_state.messages = []
                        st.rerun()
                    else:
                        # 展示后端返回错误（如用户名已存在）
                        st.error(response_error(response))
                except httpx.RequestError as exc:
                    # 网络连接异常捕获
                    st.error(f"无法连接后端：{exc}")

# 全局页面基础配置：标题、图标、居中布局
st.set_page_config(page_title="ScholarFlow", page_icon="S", layout="centered")

# 核心登录状态判断：页面缓存无access_token代表未登录
if "access_token" not in st.session_state:
    # 渲染登录注册页面
    render_login_page()
    # 终止后续所有聊天页面代码，不再执行下方对话逻辑
    st.stop()

# 已登录状态，初始化对话缓存
ensure_chat_state()

# 聊天页面主标题
st.title("ScholarFlow")

# ========== 侧边栏区域：账号信息、刷新Token、退出登录 ==========
with st.sidebar:
    st.subheader("当前账号")
    # 展示用户唯一ID，代码块样式
    st.code(st.session_state.user_id, language=None)
    # 展示短期access令牌过期时间
    st.caption(f"Access Token 到期：{st.session_state.expires_at}")
    # 展示长效刷新令牌过期时间
    st.caption(f"Refresh Token 到期：{st.session_state.refresh_expires_at}")

    # 侧边栏创建两列并排按钮：刷新Token、退出登录
    refresh_column, logout_column = st.columns(2)

    # 刷新Token按钮逻辑
    with refresh_column:
        if st.button("刷新 Token", use_container_width=True):
            try:
                # 调用后端刷新双Token接口，传入本地refresh_token
                response = httpx.post(
                    f"{API_BASE_URL}/auth/refresh",
                    json={
                        "refresh_token": st.session_state.refresh_token,
                    },
                    timeout=30,
                )
                if response.is_success:
                    # 后端返回全新双Token，覆盖页面全部认证缓存
                    save_auth_data(response.json())
                    # 页面刷新，新令牌立即生效
                    st.rerun()
                else:
                    # 刷新失败展示错误（refresh_token过期/注销）
                    st.error(response_error(response))
            except httpx.RequestError as exc:
                st.error(f"刷新失败，无法连接后端：{exc}")

    # 退出登录按钮逻辑
    with logout_column:
        if st.button("退出登录", use_container_width=True):
            try:
                # 调用后端登出接口，同时作废access与refresh令牌
                response = httpx.post(
                    f"{API_BASE_URL}/auth/logout",
                    headers=auth_headers(), # 携带当前有效access鉴权
                    json={
                        "refresh_token": st.session_state.refresh_token,
                    },
                    timeout=30,
                )
                if response.is_success:
                    # 清空页面所有登录认证缓存
                    clear_auth_data()
                    # 清空对话相关缓存
                    st.session_state.pop("thread_id", None)
                    st.session_state.pop("messages", None)
                    # 页面刷新，自动跳转登录页
                    st.rerun()
                else:
                    st.error(response_error(response))
            except httpx.RequestError as exc:
                st.error(f"退出失败，无法连接后端：{exc}")

# 页面顶部两栏按钮：清空当前会话 / 新建会话
clear_column, new_column = st.columns(2)

# 清空当前会话按钮逻辑
with clear_column:
    if st.button("清空当前会话", use_container_width=True):
        try:
            # 仅当存在聊天记录时，调用后端删除当前thread对话历史
            if st.session_state.messages:
                response = httpx.delete(
                    f"{API_BASE_URL}/threads/{st.session_state.thread_id}",
                    headers=auth_headers(),
                    timeout=30,
                )
                # 删除接口返回错误，提示用户并终止逻辑
                if not response.is_success:
                    st.error(response_error(response))
                    st.stop()

            # 本地生成全新对话ID，清空聊天记录，页面刷新重置对话
            st.session_state.thread_id = str(uuid4())
            st.session_state.messages = []
            st.rerun()
        except httpx.RequestError as exc:
            st.error(f"清空失败，无法连接后端：{exc}")

# 新建会话按钮逻辑
with new_column:
    if st.button("新建会话", use_container_width=True):
        # 仅本地切换全新thread_id，不删除后端历史对话记录
        st.session_state.thread_id = str(uuid4())
        st.session_state.messages = []
        st.rerun()

# 循环渲染历史聊天消息，用户/助手对话气泡
for message in st.session_state.messages:
    # 根据消息角色渲染对应聊天框
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 底部聊天输入框，接收用户提问
question = st.chat_input("输入问题")

# 用户输入提问后执行RAG问答逻辑
if question:
    # 将用户问题存入本地聊天记录缓存
    st.session_state.messages.append(
        {"role": "user", "content": question}
    )

    # 渲染用户提问气泡
    with st.chat_message("user"):
        st.markdown(question)

    # 助手回答气泡容器
    with st.chat_message("assistant"):
        try:
            # 加载中转圈提示
            with st.spinner("正在检索资料..."):
                # 向后端RAG问答接口发送请求，携带鉴权头、对话ID、用户问题
                response = httpx.post(
                    f"{API_BASE_URL}/ask",
                    headers=auth_headers(),
                    json={
                        "question": question,
                        "thread_id": st.session_state.thread_id,
                    },
                    timeout=180, # 问答接口超时延长至3分钟，适配长文档检索
                )

            # 接口非2xx成功状态，展示错误并终止渲染回答
            if not response.is_success:
                st.error(response_error(response))
                st.stop()

            # 解析后端返回问答结果JSON
            result = response.json()
            # 取出大模型生成的回答文本
            answer_text = result["answer"]
            # 页面渲染回答内容
            st.markdown(answer_text)

            # 循环渲染引用资料片段
            for citation in result.get("citations", []):
                st.caption(
                    f"{citation['source_name']} {citation.get('locator', '')}: "
                    f"{citation['quote']}"
                )

            # 将助手回答存入本地聊天缓存，刷新页面保留对话历史
            st.session_state.messages.append(
                {"role": "assistant", "content": answer_text}
            )
        except httpx.RequestError as exc:
            # 问答网络异常捕获提示
            st.error(f"提问失败，无法连接后端：{exc}")