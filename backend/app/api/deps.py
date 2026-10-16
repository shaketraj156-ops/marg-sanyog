from collections.abc import Callable, Iterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ProblemError
from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_session

bearer = HTTPBearer(auto_error=False)
_BEARER = {"WWW-Authenticate": "Bearer"}


def get_db() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise ProblemError(401, "not_authenticated", "Sign in first", _BEARER)
    claims = decode_token(credentials.credentials, "access")
    user = db.get(User, int(claims["sub"]))
    # Role and active flag come from the database, so changes apply immediately.
    if user is None or not user.is_active:
        raise ProblemError(401, "invalid_token", "Token is invalid", _BEARER)
    request.state.user_id = user.id  # picked up by the request log line
    return user


def require_role(*roles: str) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise ProblemError(403, "forbidden", f"role '{user.role}' may not do this")
        return user

    return dependency
