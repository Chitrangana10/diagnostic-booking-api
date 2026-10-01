from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

# Counters live in Redis, so the limits are shared if several api containers run.
# If Redis is down we fall back to counting in memory instead of failing the request.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],
    storage_uri=settings.redis_url,
    in_memory_fallback_enabled=True,
)
