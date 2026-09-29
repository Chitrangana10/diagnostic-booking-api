import json
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)

# Every function swallows Redis errors: if Redis is down the API still works, just uncached.


def get_json(key: str):
    try:
        value = _client.get(key)
        return json.loads(value) if value else None
    except redis.RedisError:
        logger.warning("cache read failed", extra={"key": key})
        return None


def set_json(key: str, value, ttl_seconds: int = 60):
    try:
        _client.set(key, json.dumps(value), ex=ttl_seconds)
    except redis.RedisError:
        logger.warning("cache write failed", extra={"key": key})


def delete_prefix(prefix: str):
    try:
        for key in _client.scan_iter(f"{prefix}*"):
            _client.delete(key)
    except redis.RedisError:
        logger.warning("cache invalidate failed", extra={"prefix": prefix})
