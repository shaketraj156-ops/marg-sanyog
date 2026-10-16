import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import get_settings
from app.core.errors import ProblemError

ALGORITHM = "HS256"
TokenType = Literal["access", "refresh"]

_BEARER = {"WWW-Authenticate": "Bearer"}
_hasher = PasswordHasher()  # argon2id with the library's default cost parameters
_dummy_hash: str | None = None


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def dummy_hash() -> str:
    """A real hash to verify against when the email is unknown, so timing does not leak it."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-a-real-password")
    return _dummy_hash


def _encode(
    user_id: int, token_type: TokenType, lifetime: timedelta, jti: str
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires = now + lifetime
    claims = {"sub": str(user_id), "type": token_type, "jti": jti, "iat": now, "exp": expires}
    return jwt.encode(claims, get_settings().jwt_secret, algorithm=ALGORITHM), expires


def create_access_token(user_id: int, lifetime: timedelta | None = None) -> str:
    lifetime = lifetime or timedelta(minutes=get_settings().access_token_minutes)
    token, _ = _encode(user_id, "access", lifetime, uuid.uuid4().hex)
    return token


def create_refresh_token(
    user_id: int, lifetime: timedelta | None = None
) -> tuple[str, str, datetime]:
    """Returns (token, jti, expires_at)."""
    lifetime = lifetime or timedelta(days=get_settings().refresh_token_days)
    jti = str(uuid.uuid4())
    token, expires = _encode(user_id, "refresh", lifetime, jti)
    return token, jti, expires


def decode_token(token: str, expected_type: TokenType) -> dict:
    try:
        claims = jwt.decode(
            token,
            get_settings().jwt_secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "type", "jti"]},
        )
    except jwt.ExpiredSignatureError:
        raise ProblemError(401, "token_expired", "Token has expired", _BEARER) from None
    except jwt.PyJWTError:
        raise ProblemError(401, "invalid_token", "Token is invalid", _BEARER) from None
    if claims["type"] != expected_type or not str(claims["sub"]).isdigit():
        raise ProblemError(401, "invalid_token", "Token is invalid", _BEARER)
    return claims
