from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )
    return _engine


def execute(sql: str, params: dict | None = None) -> int:
    with get_engine().begin() as conn:
        result = conn.execute(text(sql), params or {})
        return int(result.rowcount or 0)


def fetch_one(sql: str, params: dict | None = None) -> dict | None:
    with get_engine().begin() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row else None


def fetch_all(sql: str, params: dict | None = None) -> list[dict]:
    with get_engine().begin() as conn:
        rows = conn.execute(text(sql), params or {}).mappings().all()
    return [dict(row) for row in rows]


def mysql_enabled() -> bool:
    return settings.relational_backend.lower() == "mysql"
