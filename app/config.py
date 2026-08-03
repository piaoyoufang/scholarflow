from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    dashscope_api_key: str
    dashscope_base_url: str
    chat_model: str = "qwen-plus"
    fast_model: str = "qwen-turbo"
    embedding_model: str = "text-embedding-v3"
    rerank_model: str = "gte-rerank-v2"
    rerank_base_url: str = (
        "https://dashscope.aliyuncs.com/api/v1/services/"
        "rerank/text-rerank/text-rerank"
    )
    rerank_timeout_seconds: float = 20
    vector_db_dir: str = "./data/chroma"
    checkpoint_db_path: str = "./data/memory/checkpoints.sqlite"
    auth_db_path: str = "./data/auth/auth.sqlite"
    api_base_url: str = "http://127.0.0.1:8000"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    log_level: str = "INFO"
    log_dir: str = "./logs"
    slow_request_ms: int = 3000
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 30
    ask_rate_limit_max_requests: int = 10
    model_max_concurrency: int = 2
    chat_timeout_seconds: float = 60
    fast_timeout_seconds: float = 30
    model_max_attempts: int = 2
    retry_base_delay_seconds: float = 0.5
    mcp_timeout_seconds: float = 20
    mcp_max_attempts: int = 2


    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
