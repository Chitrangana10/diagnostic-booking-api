from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

ALGORITHM = "HS256"

ACCESS = "access"
REFRESH = "refresh"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _create_token(user, token_type: str, lifetime: timedelta) -> str:
    payload = {
        "sub": str(user.id),
        "type": token_type,
        "ver": user.token_version,
        "exp": datetime.now(timezone.utc) + lifetime,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user) -> str:
    return _create_token(
        user, ACCESS, timedelta(minutes=settings.access_token_expire_minutes)
    )


def create_refresh_token(user) -> str:
    return _create_token(user, REFRESH, timedelta(days=settings.refresh_token_expire_days))


def decode_token(token: str, expected_type: str) -> dict | None:
    """Returns the token's data, or None if it is bad, expired or the wrong kind of token."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload
