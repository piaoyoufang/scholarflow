from typing import Literal
# 定义了数据的格式（比如用户提问必须包含哪些字段），确保各模块间传递的数据是规范的。
from pydantic import BaseModel, Field, SecretStr

# 引用信息模板 (Citation)
class Citation(BaseModel):
    source_id: str  # 文档的唯一编号（比如数据库里的 ID）。
    source_name: str  # 论文或书籍的标题。
    locator: str = ""  # 定位符（默认为空字符串 ""），通常用来记录页码或章节号。
    quote: str # 原文摘录，证明 AI 确实参考了这段话。

# 研究回答模板 (ResearchAnswer)
class ResearchAnswer(BaseModel):
    answer: str # AI 生成的最终回答文本。
    citations: list[Citation] = Field(default_factory=list)  # 引用列表。注意这里用了 list[Citation]，意味着一个回答可以包含多个上面的 Citation 对象。default_factory=list 保证如果没找到引用，它就是一个空列表 [] 而不是报错。
    confidence: float = Field(ge=0, le=1) # 置信度。这是一个评分机制，范围被严格限制在 0 到 1 之间（ge=0, le=1 表示大于等于0，小于等于1）。这让前端可以根据分数决定要不要显示“我不确定”的提示。
    missing_information: list[str] = Field(default_factory=list) # 缺失信息列表。如果知识库不够，AI 可以在这里列出“我还缺什么资料才能回答得更好”，这对于学术研究非常有用。

# 提问请求模板 (AskRequest)
class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000) # 用户的问题。加了限制：最少 1 个字，最多 4000 字。这能防止用户发空消息浪费
    # 定义接口入参字段 thread_id：客户端会话唯一标识字符串
    thread_id: str = Field(
        # 字符串最小长度限制：最少8个字符，过滤过短非法会话ID
        min_length=8,
        # 字符串最大长度限制：最多128个字符，防止传入超长字符串占用存储、引发异常
        max_length=128,
        # 给大模型/接口文档的字段说明，约束业务规则：thread_id必须由客户端自行生成独立UUID，禁止全局共用默认会话ID
        description="客户端生成的会话 UUID，不能使用公共默认值。",
    )

# 工具路由决策模型：让 Qwen 先判断要不要调用 MCP
class RouteDecision(BaseModel):
    use_mcp: bool = Field(
        description="是否需要调用 MCP 工具。需要就填 true，不需要就填 false。"
    )
    # 使用 `Literal` 后，Qwen 只能从三个合法值中选择，可以避免它随意编造不存在的工具名。
    tool_name: Literal[
        "none",
        "search_local_knowledge",
        "search_evaluation_report",
    ] = Field(
        description="不调用工具时选 none；否则选择最适合的一个 MCP 工具。"
    )
    query: str = Field(
        min_length=1,
        max_length=1000,
        description="传给工具的查询；不调用 MCP 时原样填写用户问题。",
    )
    reason: str = Field(
        default="",
        description="简短说明为什么这样选择。",
    )

# 对话历史问题重写结构化模型 QuestionRewrite
class QuestionRewrite(BaseModel):
    standalone_question: str = Field(
        min_length=1,
        max_length=4000,
        description="结合历史后得到的独立问题。",
    )
    used_history: bool = Field(
        description="本次改写是否实际使用了历史信息。"
    )

# 用户登录会话返回结构体，FastAPI登录接口专用返回格式
class SessionResponse(BaseModel):
    # 用户全局唯一标识ID
    user_id: str
    # 前端鉴权用的明文访问令牌
    access_token: str
    #  token过期时间
    expires_at: str
    # Token认证类型，固定bearer格式，前端请求头按标准格式携带令牌
    token_type: str = "bearer"

# 用户注册接口请求体模型，校验前端提交的注册账号密码格式
class RegisterRequest(BaseModel):
    # 用户名字段：最小3字符、最大32字符，仅允许大小写英文字母、数字、下划线
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_]+$")
    # 密码字段，SecretStr自动脱敏，日志不会打印明文；长度限制8~128位
    password: SecretStr = Field(min_length=8, max_length=128)

# 用户账号密码登录接口请求体模型
class LoginRequest(BaseModel):
    # 登录用户名，长度3~32位
    username: str = Field(min_length=3, max_length=32)
    # 登录密码，SecretStr脱敏存储，长度限制8~128位
    password: SecretStr = Field(min_length=8, max_length=128)

# 刷新长会话凭证专用请求模型，接收前端传入的刷新令牌
class RefreshTokenRequest(BaseModel):
    # 刷新令牌字段，长度限制32~512字符，保障令牌完整性
    refresh_token: str = Field(min_length=32, max_length=512)

# 账号登录完整会话返回模型，继承原有SessionResponse基础字段，扩展刷新令牌相关字段
class AccountSessionResponse(SessionResponse):
    # 长效刷新令牌，用于access_token过期后免账号密码续期会话
    refresh_token: str
    # 刷新令牌的过期时间（ISO标准时间字符串），前端用于判断何时重新登录
    refresh_expires_at: str

# 继承Pydantic基础模型，用于封装分流器（Supervisor）的输出结构化结果
class SupervisorDecision(BaseModel):
    # 固定字面量类型，仅允许二选一：知识检索Agent / 报告生成Agent
    next_agent: Literal[
        "knowledge_agent",  # 分支1：进入资料检索、引用匹配流程
        "report_agent",     # 分支2：直接生成总结报告，无需额外检索
        "diagnosis_agent",  # 分支3：只读检查文件、评估与运行指标
    ] = Field(
        # 字段说明：告知大模型当前仅两个可选分流目标
        description="下一步交给知识Agent、评估报告Agent或只读诊断Agent。"
    )
    # 分流原因文本字段
    reason: str = Field(
        # 默认空字符串，无特殊分流理由时留空
        default="",
        # 字符串最大长度500，限制模型输出超长文本
        max_length=500,
        # 字段描述，指导模型输出简短判断理由
        description="简短说明分流原因。",
    )
