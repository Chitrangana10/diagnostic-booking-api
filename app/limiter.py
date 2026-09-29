from slowapi import Limiter
from slowapi.util import get_remote_address

# in-memory counters are fine for a single api container
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
