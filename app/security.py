# 导入sha256哈希工具，用于不可逆加密存储登录Token，数据库不保存明文令牌
import hashlib
# 安全随机数生成器，生成高安全强度的用户访问Token
import secrets
# SQLite文件型数据库驱动，持久化存储登录会话、对话线程归属权限
import sqlite3
# 迭代器类型注解，上下文管理器返回数据库连接迭代器
from collections.abc import Iterator
# 上下文管理器装饰器，封装数据库连接自动开启/关闭、事务提交回滚逻辑
from contextlib import contextmanager
# 日期时间工具：当前UTC时间、时间差、时区标准化，用于Token过期时间计算
from datetime import datetime, timedelta, timezone
# 路径工具类，统一处理数据库文件相对/绝对路径、自动创建目录
from pathlib import Path
# UUID工具，生成全局唯一user_id用户标识
from uuid import uuid4

# 导入全局项目配置：项目根目录、Token过期分钟配置、认证数据库路径配置
from app.config import PROJECT_ROOT, settings

# 导入pwdlib密码哈希工具库，提供安全的密码加盐哈希、校验功能，替代原生hashlib
from pwdlib import PasswordHash

# 获取官方推荐的高强度哈希算法实例（默认采用Argon2，自动随机加盐、抗暴力破解）
password_hash = PasswordHash.recommended()


# 用户认证与会话、对话线程权限持久化存储类
# 负责登录鉴权、Token过期管理、会话注销、多用户对话线程隔离权限校验
class AuthStore:
    # 类构造初始化方法
    #:param path: SQLite数据库文件路径对象
    #:param token_ttl_seconds: 短期access_token有效期，单位秒，默认900秒=15分钟
    #:param refresh_token_ttl_seconds: 长效刷新refresh_token有效期，单位秒，默认30天
    def __init__(
        self,
        path: Path,
        token_ttl_seconds: int = 900,
        refresh_token_ttl_seconds: int = 30 * 24 * 60 * 60,
    ):
        # 参数合法性校验：两种令牌有效期都不能小于1秒
        if token_ttl_seconds < 1 or refresh_token_ttl_seconds < 1:
            raise ValueError("Token 有效期必须大于 0")
        # 保存数据库文件路径到实例属性
        self.path = path
        # 保存短期访问令牌有效期配置，创建会话时计算过期时间
        self.token_ttl_seconds = token_ttl_seconds
        # 保存长效刷新令牌有效期配置，创建刷新会话时计算过期时间
        self.refresh_token_ttl_seconds = refresh_token_ttl_seconds
        # 自动递归创建数据库所在文件夹，多级目录不存在则生成，已存在无报错
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 执行数据表创建、字段迁移、历史数据兼容逻辑
        self._setup()

    # 上下文管理器封装数据库连接，自动管理事务、连接关闭，解决Windows文件锁占用问题
    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        # 建立SQLite连接，设置30秒超时避免文件锁阻塞
        connection = sqlite3.connect(str(self.path), timeout=30)
        # 设置查询返回行对象，支持通过列名直接读取字段值
        connection.row_factory = sqlite3.Row
        try:
            # 向外抛出数据库连接对象，给外层SQL操作使用
            yield connection
            # 所有SQL执行无异常，自动提交事务写入磁盘
            connection.commit()
        except Exception:
            # 任意SQL异常，事务回滚，放弃本次所有修改
            connection.rollback()
            # 向上抛出异常，外层捕获处理业务错误
            raise
        finally:
            # 无论成功失败，强制关闭数据库连接，释放文件锁
            connection.close()

    # 静态工具方法：获取当前UTC标准时间（统一时区避免本地时区时差导致过期校验错乱）
    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    # 静态加密工具：对明文Token进行sha256不可逆哈希加密，仅存储哈希值保护安全
    @staticmethod
    def _hash_token(token: str) -> str:
        # 将字符串转为utf8字节流计算哈希，返回十六进制加密字符串
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    # 内部初始化迁移方法：创建数据表、新增缺失字段、兼容旧版本数据库数据
    def _setup(self) -> None:
        # 使用上下文管理器获取数据库连接执行建表语句
        with self._connect() as connection:
            # 批量执行两张数据表创建SQL，不存在表才创建，防止重复执行报错
            connection.executescript(
                """
                -- 用户登录会话表：存储Token哈希、用户ID、创建/过期/注销时间，管理登录凭证生命周期
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,       -- Token加密哈希，唯一主键，每条会话一条记录
                    user_id TEXT NOT NULL,             -- 会话归属用户唯一ID
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 会话创建UTC时间
                    expires_at TEXT NOT NULL,          -- Token过期UTC时间，到期自动失效
                    revoked_at TEXT                    -- 手动注销时间，不为空代表该Token已作废
                );

                -- 对话线程归属权限表：绑定thread_id与user_id，实现多用户对话数据隔离
                CREATE TABLE IF NOT EXISTS threads (
                    thread_id TEXT PRIMARY KEY,        -- 对话会话唯一标识
                    user_id TEXT NOT NULL,             -- 该线程所属用户ID
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, -- 线程绑定创建时间
                    title TEXT NOT NULL DEFAULT '新会话', -- 首次问题生成的会话标题
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP -- 最近提问时间
                );

                -- 用户账号主表，存储注册用户名、加密密码、用户唯一标识
    CREATE TABLE IF NOT EXISTS users (
    -- 用户全局唯一ID，主键，关联会话、线程表
    user_id TEXT PRIMARY KEY,
    -- 登录用户名，非空、全局唯一；COLLATE NOCASE 大小写不敏感，Admin/admin视为同一个账号
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    -- 用户密码加密哈希，数据库永不存储明文密码
    password_hash TEXT NOT NULL,
    -- 全局账号身份：teacher 教师 / student 学生；新库默认学生
    role TEXT NOT NULL DEFAULT 'student',
    -- 账号创建时间，默认取数据库当前时间
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 长效刷新令牌会话表，用于access_token过期后免密码续期登录
CREATE TABLE IF NOT EXISTS refresh_sessions (
    -- refresh_token加密哈希，主键，一条刷新凭证对应一条记录
    token_hash TEXT PRIMARY KEY,
    -- 所属用户ID，关联users表的用户主键
    user_id TEXT NOT NULL,
    -- 刷新凭证创建时间
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 刷新凭证过期时间，到期自动失效
    expires_at TEXT NOT NULL,
    -- 手动注销时间，不为空代表该刷新令牌已作废
    revoked_at TEXT,
    -- 外键约束：user_id必须存在于users用户表，禁止创建无归属用户的刷新会话
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

-- 为refresh_sessions表的user_id创建索引，按用户查询刷新会话时大幅提升查询速度
CREATE INDEX IF NOT EXISTS idx_refresh_sessions_user_id
ON refresh_sessions(user_id);
                """
            )

            # 注释说明：CREATE TABLE IF NOT EXISTS 只会新建空表，旧表不会自动新增字段，必须手动执行字段迁移SQL
            # 查询当前sessions表已存在的所有字段名
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(sessions)")
            }
            # 旧库缺少expires_at过期字段，执行ALTER新增字段
            if "expires_at" not in columns:
                connection.execute(
                    "ALTER TABLE sessions ADD COLUMN expires_at TEXT"
                )
            # 旧库缺少revoked_at注销字段，执行ALTER新增字段
            if "revoked_at" not in columns:
                connection.execute(
                    "ALTER TABLE sessions ADD COLUMN revoked_at TEXT"
                )

            # 兼容逻辑：历史旧数据没有设置过期时间，无法做有效期校验，全部标记为已注销失效
            # 查询users表结构，兼容旧版本账号库没有role字段的情况
            user_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(users)")
            }
            if "role" not in user_columns:
                # 旧账号原来默认拥有教师端能力，迁移时保留为teacher，避免已有演示账号权限突然丢失
                connection.execute(
                    "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'teacher'"
                )

            connection.execute(
                "UPDATE sessions SET revoked_at = CURRENT_TIMESTAMP "
                "WHERE expires_at IS NULL AND revoked_at IS NULL"
            )
            # 查询threads数据表结构信息，遍历结果提取所有字段名称，存入集合
            thread_columns = {
                # 获取表结构每条记录中的字段名
                row["name"]
                # SQLite内置指令：读取threads表的完整字段定义信息
                for row in connection.execute("PRAGMA table_info(threads)")
            }

            # 判断表内不存在title字段时执行新增逻辑
            if "title" not in thread_columns:
                # 执行SQL，为threads表新增title文本字段
                connection.execute(
                    # 新增title字段，TEXT类型；非空约束，历史数据/新建数据默认填充“新会话”
                    "ALTER TABLE threads ADD COLUMN title TEXT "
                    "NOT NULL DEFAULT '新会话'"
                )

            # 判断表内不存在updated_at字段时执行新增逻辑
            if "updated_at" not in thread_columns:
                # SQLite 不允许旧表通过 ALTER TABLE 添加 CURRENT_TIMESTAMP 默认值。
                # 先增加普通字段，再用已有创建时间回填历史记录。
                connection.execute(
                    "ALTER TABLE threads ADD COLUMN updated_at TEXT"
                )
            connection.execute(
                "UPDATE threads SET updated_at = COALESCE(updated_at, created_at)"
            )

    # 内部工具：生成新Token、加密哈希、过期时间三元组
    #:param user_id: 当前新建会话归属用户ID
    #:return: (明文token, token哈希, 过期时间iso字符串)
    def _new_token_values(self, user_id: str) -> tuple[str, str, str]:
        # 生成32字节安全随机URL友好Token明文，仅返回给前端，数据库不存储
        token = secrets.token_urlsafe(32)
        # 对明文Token做sha256加密
        token_hash = self._hash_token(token)
        # 当前UTC时间 + 配置有效期，计算Token到期时间，转为标准ISO字符串存入数据库
        expires_at = (
            self._now() + timedelta(seconds=self.token_ttl_seconds)
        ).isoformat()
        return token, token_hash, expires_at


    # 静态工具方法：统一标准化用户名，实现大小写不敏感登录/注册校验
    @staticmethod
    def _normalize_username(username: str) -> str:
        # 1.strip() 去除首尾空格  2.casefold() 全转为小写，兼容大小写同名账号（Admin/admin视为同一用户）
        return username.strip().casefold()

    # 用户注册方法：接收原始用户名+明文密码，写入users账号表，返回唯一user_id
    def register_user(self, username: str, password: str, role: str = "student") -> str:
        # 标准化处理用户名，统一格式用于数据库匹配
        normalized = self._normalize_username(username)
        # 校验标准化后用户名长度，至少3字符，不满足抛出参数错误
        if len(normalized) < 3:
            raise ValueError("用户名至少需要 3 个字符")
        # Validate global account role: teacher or student only
        if role not in {"teacher", "student"}:
            raise ValueError("role must be teacher or student")

        # 生成全局唯一用户ID（UUID字符串）
        user_id = str(uuid4())
        # 使用pwdlib对明文密码进行高强度Argon2加盐哈希加密，得到存储用哈希串
        encoded_password = password_hash.hash(password)
        try:
            # 使用数据库上下文管理器开启事务
            with self._connect() as connection:
                # 插入用户记录到users表，存储标准化用户名、加密密码、用户ID
                connection.execute(
                    "INSERT INTO users(user_id, username, password_hash, role) VALUES (?, ?, ?, ?)",
                    (user_id, normalized, encoded_password, role),
                )
        # 捕获唯一性约束冲突：数据库username字段UNIQUE，重复注册触发该异常
        except sqlite3.IntegrityError as exc:
            # 转换为业务可读异常，保留原始异常堆栈
            raise ValueError("用户名已存在") from exc
        # 注册成功，返回新用户唯一标识user_id
        return user_id

    # 账号密码登录校验方法：验证用户名+密码是否匹配，合法返回user_id，错误返回None
    # 查询账号全局身份：用于登录返回、菜单权限和教师端接口保护
    def get_user_role(self, user_id: str) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT role FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return str(row["role"]) if row and row["role"] else "student"

    def verify_user(self, username: str, password: str) -> str | None:
        # 标准化输入的用户名，和数据库存储格式统一
        normalized = self._normalize_username(username)
        # 打开数据库连接查询用户记录
        with self._connect() as connection:
            # 根据标准化用户名查询用户ID与存储的密码哈希
            row = connection.execute(
                "SELECT user_id, password_hash FROM users WHERE username = ?",
                (normalized,),
            ).fetchone()
        # 两种失败场景：1.无此用户 2.密码哈希校验不匹配
        if not row or not password_hash.verify(password, row["password_hash"]):
            return None
        # 账号密码校验全部通过，返回用户ID
        return str(row["user_id"])

    # 创建完整双Token会话：同时生成短期access_token + 长效refresh_token，写入两张会话表
    #:return: (access明文令牌, access过期时间, refresh明文令牌, refresh过期时间)
    def create_account_session(self, user_id: str) -> tuple[str, str, str, str]:
        # 调用工具生成短期access_token、哈希、过期时间
        access_token, access_hash, access_expires_at = self._new_token_values(user_id)
        # 生成48字符长度的长效refresh_token明文
        refresh_token = secrets.token_urlsafe(48)
        # 对refresh_token做sha256哈希加密，数据库只存哈希不存明文
        refresh_hash = self._hash_token(refresh_token)
        # 计算refresh_token过期UTC时间，转为ISO标准字符串
        refresh_expires_at = (
            self._now() + timedelta(seconds=self.refresh_token_ttl_seconds)
        ).isoformat()

        # 开启数据库事务，同时写入两张会话表，原子操作要么全部成功要么全部失败
        with self._connect() as connection:
            # 将短期access会话存入sessions表，用于业务接口鉴权
            connection.execute(
                "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (access_hash, user_id, access_expires_at),
            )
            # 将长效刷新会话存入refresh_sessions表，用于access过期后免密续期
            connection.execute(
                "INSERT INTO refresh_sessions(token_hash, user_id, expires_at) "
                "VALUES (?, ?, ?)",
                (refresh_hash, user_id, refresh_expires_at),
            )
        # 返回两套令牌与对应过期时间给接口封装返回
        return access_token, access_expires_at, refresh_token, refresh_expires_at

    # 刷新长效refresh_token接口：旧refresh作废，生成全新access+refresh双令牌
    #:return: (用户ID, 新access_token, access过期时间, 新refresh_token, refresh过期时间)
    def rotate_refresh_token(self, refresh_token: str) -> tuple[str, str, str, str, str]:
        # 对前端传入的旧refresh_token加密哈希，用于数据库查询匹配
        old_hash = self._hash_token(refresh_token)
        # 获取当前UTC标准时间，用于过期、注销时间标记
        now = self._now()
        # 时间转为ISO字符串，用于数据库字段存储
        now_text = now.isoformat()

        # 开启数据库事务执行查询与更新
        with self._connect() as connection:
            # 根据旧refresh哈希查询完整刷新会话信息
            row = connection.execute(
                "SELECT user_id, expires_at, revoked_at FROM refresh_sessions "
                "WHERE token_hash = ?",
                (old_hash,),
            ).fetchone()
            # 三重校验刷新令牌合法性：1.无记录 2.已手动注销 3.已过期
            if (
                not row
                or row["revoked_at"]
                or datetime.fromisoformat(str(row["expires_at"])) <= now
            ):
                raise PermissionError("Refresh Token 无效、已过期或已注销")

            # 将合法未过期的旧refresh_token标记为已注销，使其立刻失效
            updated = connection.execute(
                "UPDATE refresh_sessions SET revoked_at = ? "
                "WHERE token_hash = ? AND revoked_at IS NULL AND expires_at > ?",
                (now_text, old_hash, now_text),
            )
            # 更新行数不等于1代表旧令牌已经失效，抛出权限异常禁止刷新
            if updated.rowcount != 1:
                raise PermissionError("旧 Refresh Token 已经失效")

            # 取出绑定的用户ID，刷新前后用户保持不变
            user_id = str(row["user_id"])
            # 生成全新短期access_token及对应过期信息
            access_token, access_hash, access_expires_at = self._new_token_values(user_id)
            # 生成全新长效refresh_token明文
            new_refresh_token = secrets.token_urlsafe(48)
            # 对新refresh加密哈希
            new_refresh_hash = self._hash_token(new_refresh_token)
            # 计算新refresh的过期时间
            refresh_expires_at = (
                now + timedelta(seconds=self.refresh_token_ttl_seconds)
            ).isoformat()
            # 插入新的短期access会话记录
            connection.execute(
                "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (access_hash, user_id, access_expires_at),
            )
            # 插入新的长效refresh会话记录
            connection.execute(
                "INSERT INTO refresh_sessions(token_hash, user_id, expires_at) "
                "VALUES (?, ?, ?)",
                (new_refresh_hash, user_id, refresh_expires_at),
            )

        # 返回全套全新会话信息，前端替换本地旧令牌
        return (
            user_id,
            access_token,
            access_expires_at,
            new_refresh_token,
            refresh_expires_at,
        )

    # 主动注销长效refresh_token，手动作废刷新凭证
    #:return True=注销成功；False=令牌不存在/已注销
    def revoke_refresh_token(self, refresh_token: str) -> bool:
        # 对目标刷新令牌加密哈希
        token_hash = self._hash_token(refresh_token)
        # 打开数据库连接执行更新注销标记
        with self._connect() as connection:
            # 仅更新未注销的记录，填入当前UTC时间作为注销时间
            result = connection.execute(
                "UPDATE refresh_sessions SET revoked_at = ? "
                "WHERE token_hash = ? AND revoked_at IS NULL",
                (self._now().isoformat(), token_hash),
            )
        # 数据库影响行数为1代表注销成功，返回布尔结果
        return result.rowcount == 1


    # 创建全新用户登录会话，生成user_id、访问令牌、过期时间
    #:return: (用户唯一ID, 明文access_token, token过期时间)
    def create_session(self) -> tuple[str, str, str]:
        # 生成全局唯一用户ID
        user_id = str(uuid4())
        # 调用工具生成Token、哈希、过期时间
        token, token_hash, expires_at = self._new_token_values(user_id)
        # 写入会话记录到数据库
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO sessions"
                "(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (token_hash, user_id, expires_at),
            )
        # 返回用户ID、前端明文令牌、令牌过期时间
        return user_id, token, expires_at

    # 鉴权校验函数：传入前端Bearer Token，校验是否合法、未过期、未注销
    #:param token: 前端传来的明文访问令牌
    #:return: 合法返回user_id；失效/不存在返回None
    def authenticate(self, token: str) -> str | None:
        # 加密前端传入的Token，和库内存储的哈希匹配查询
        token_hash = self._hash_token(token)
        with self._connect() as connection:
            # 根据哈希查询该会话完整信息
            row = connection.execute(
                "SELECT user_id, expires_at, revoked_at "
                "FROM sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()

        # 1.无记录 2.已手动注销 3.无过期时间标记，任意一种直接鉴权失败
        if not row or row["revoked_at"] or not row["expires_at"]:
            return None

        # 将数据库存储的ISO时间字符串转为UTC时间对象
        expires_at = datetime.fromisoformat(str(row["expires_at"]))
        # 当前时间 >= 过期时间，Token已超时失效
        if expires_at <= self._now():
            return None
        # 鉴权全部校验通过，返回该会话绑定的用户ID
        return str(row["user_id"])

    # Token续期刷新接口：旧合法Token作废，生成全新有效Token
    #:param token: 当前未过期未注销的旧令牌
    #:return: (用户ID, 新明文Token, 新Token过期时间)
    def refresh_session(self, token: str) -> tuple[str, str, str]:
        # 先校验旧Token是否合法有效
        user_id = self.authenticate(token)
        if not user_id:
            raise PermissionError("Token 无效、已过期或已注销")

        # 生成全新一套Token、哈希、过期时间
        new_token, new_hash, expires_at = self._new_token_values(user_id)
        # 对旧Token加密，用于更新注销标记
        old_hash = self._hash_token(token)
        # 数据库更新时再次校验有效期，防止 Token 在 authenticate() 返回后、
        # UPDATE 执行前恰好到期却仍被刷新。
        now = self._now().isoformat()

        with self._connect() as connection:
            # 将旧Token标记为已注销，使其立刻失效
            updated = connection.execute(
                "UPDATE sessions SET revoked_at = ? "
                "WHERE token_hash = ? AND revoked_at IS NULL "
                "AND expires_at > ?",
                (now, old_hash, now),
            )
            # 更新行数不等于1，说明旧Token已经失效，抛出异常禁止刷新
            if updated.rowcount != 1:
                raise PermissionError("旧 Token 已经失效")
            # 插入全新的有效会话记录
            connection.execute(
                "INSERT INTO sessions"
                "(token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (new_hash, user_id, expires_at),
            )

        # 返回全新有效Token信息给前端
        return user_id, new_token, expires_at

    # 主动注销单条Token会话，手动使令牌失效
    #:param token: 需要注销的明文访问令牌
    #:return: True=注销成功；False=该Token不存在/已注销
    def revoke_session(self, token: str) -> bool:
        # 加密目标Token
        token_hash = self._hash_token(token)
        with self._connect() as connection:
            # 更新revoked_at注销时间，仅修改未注销的记录
            result = connection.execute(
                "UPDATE sessions SET revoked_at = ? "
                "WHERE token_hash = ? AND revoked_at IS NULL",
                (self._now().isoformat(), token_hash),
            )
        # 数据库影响行数为1代表成功注销，返回布尔结果
        return result.rowcount == 1

    # 定时清理失效会话：删除已注销、已过期的所有Token记录，减少数据库体积
    #:return: 本次清理删除的记录总条数
    def cleanup_sessions(self) -> int:
        # 获取当前UTC标准时间字符串
        now = self._now().isoformat()
        with self._connect() as connection:
            # 删除两类记录：1.手动注销 2.已过期
            result = connection.execute(
                "DELETE FROM sessions "
                "WHERE revoked_at IS NOT NULL OR expires_at <= ?",
                (now,),
            )
        # 返回本次清理删除的行数
        return result.rowcount

    # 绑定对话线程归属关系：将thread_id与当前用户绑定，禁止其他用户占用
    #:param user_id: 当前操作登录用户ID
    #:param thread_id: 对话会话唯一标识
    def claim_thread(self, user_id: str, thread_id: str) -> None:
        with self._connect() as connection:
            # 不存在该线程则插入绑定关系；已存在不修改原有归属，保证归属不可篡改
            connection.execute(
                "INSERT OR IGNORE INTO threads(thread_id, user_id) VALUES (?, ?)",
                (thread_id, user_id),
            )
            # 查询该线程当前绑定的所有者
            row = connection.execute(
                "SELECT user_id FROM threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        # 无记录 或 绑定用户与当前操作者不一致，抛出权限拒绝异常
        if not row or row["user_id"] != user_id:
            raise PermissionError("该线程属于其他用户")

    @staticmethod
    def make_thread_title(question: str, max_length: int = 28) -> str:
        # 去除首尾空白，多个空格统一压缩为单个空格，清洗输入文本
        title = " ".join(question.strip().split())
        # 清洗后内容为空，返回默认会话名称
        if not title:
            return "新会话"
        # 文本长度≤阈值直接使用；超长则截断并添加省略号
        return title if len(title) <= max_length else f"{title[:max_length]}..."

    def update_thread_title(
            self,
            user_id: str,
            thread_id: str,
            question: str,
    ) -> None:
        # 权限校验：确认当前用户是该对话线程的所有者，无权限直接抛出异常
        self.require_thread_owner(user_id, thread_id)
        # 调用静态方法，基于用户提问生成标准化会话标题
        title = self.make_thread_title(question)
        # 获取数据库连接，开启事务执行更新
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE threads
                -- CASE分支：只有当前标题是默认值「新会话」时，才更新标题
                -- 一旦用户自定义标题/首次生成标题后，后续不会覆盖
                SET title      = CASE
                                     WHEN title = '新会话' THEN ?
                                     ELSE title
                    END,
                    -- 无论标题是否修改，更新线程最后修改时间
                    updated_at = CURRENT_TIMESTAMP
                -- 匹配指定线程ID + 用户ID，防止越权修改其他用户线程
                WHERE thread_id = ?
                  AND user_id = ?
                """,
                # SQL占位符参数：新标题、线程ID、用户ID
                (title, thread_id, user_id),
            )

    # 权限校验工具：校验当前用户是否为目标线程合法所有者，无权限直接抛异常
    #:param user_id: 当前登录用户ID
    #:param thread_id: 需要操作的对话线程ID
    def require_thread_owner(self, user_id: str, thread_id: str) -> None:
        with self._connect() as connection:
            # 查询线程归属用户
            row = connection.execute(
                "SELECT user_id FROM threads WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        # 未查询到该线程绑定记录，抛出404类异常
        if not row:
            raise LookupError("线程不存在或尚未绑定用户")
        # 线程所有者与当前用户不匹配，抛出403权限异常
        if row["user_id"] != user_id:
            raise PermissionError("该线程属于其他用户")

    # 查询当前用户拥有的全部线程，用于前端在刷新页面或重启容器后恢复历史会话入口
    #:param user_id: 当前登录用户ID
    #:return: 按创建时间倒序排列的线程元数据列表
    def list_threads(self, user_id: str) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT thread_id, created_at, title, updated_at
                FROM threads
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [
            {
                "thread_id": row["thread_id"],
                "created_at": row["created_at"],
                "title": row["title"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    # 删除对话线程归属记录，删除前强制校验用户所有权
    #:param user_id: 当前登录操作者用户ID
    #:param thread_id: 需要清空的对话线程ID
    def delete_thread(self, user_id: str, thread_id: str) -> None:
        # 先执行所有权校验，无权限直接抛出异常终止操作
        self.require_thread_owner(user_id, thread_id)
        with self._connect() as connection:
            # 根据thread_id删除线程归属绑定记录
            connection.execute(
                "DELETE FROM threads WHERE thread_id = ?",
                (thread_id,),
            )

# --------------------------全局单例初始化代码--------------------------
# 读取配置文件中认证数据库文件路径，转为Path对象
auth_path = Path(settings.auth_db_path)
# 判断路径是否为相对路径
if not auth_path.is_absolute():
    # 拼接项目根目录，转换为完整绝对路径
    auth_path = PROJECT_ROOT / auth_path

# 全局唯一认证存储单例，全项目统一调用账号、会话、权限相关逻辑
auth_store = AuthStore(
    # 第一个入参：认证数据库文件路径Path对象
    auth_path,
    # 第二个入参：短期access_token有效期，配置文件单位为分钟，乘以60转换为秒传入类构造函数
    token_ttl_seconds=settings.access_token_ttl_minutes * 60,
    # 第三个入参：长效refresh_token有效期，配置文件单位为天，换算公式 天*24小时*60分*60秒 转为秒
    refresh_token_ttl_seconds=settings.refresh_token_ttl_days * 24 * 60 * 60,
)
