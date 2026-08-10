import json
from typing import Any

import redis
from redis.exceptions import RedisError

from app.config import settings

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def get_json(key: str) -> Any | None:
    try:
        raw = redis_client.get(key)
    except RedisError:
        return None
    if raw is None:
        return None
    return json.loads(raw)


def set_json(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    try:
        redis_client.setex(
            key,
            ttl_seconds or settings.cache_ttl_seconds,
            json.dumps(value, ensure_ascii=False),
        )
    except RedisError:
        return None


def delete_key(key: str) -> None:
    try:
        redis_client.delete(key)
    except RedisError:
        return None


def delete_prefix(prefix: str) -> None:
    try:
        for key in redis_client.scan_iter(f"{prefix}*"):
            redis_client.delete(key)
    except RedisError:
        return None


def ping() -> tuple[bool, str]:
    try:
        return bool(redis_client.ping()), "ok"
    except RedisError as exc:
        return False, type(exc).__name__
