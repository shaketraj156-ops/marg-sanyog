from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.errors import ProblemError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    dummy_hash,
    verify_password,
)
from app.db.models import RefreshToken, User
from app.schemas.auth import TokenPair


def authenticate(db: Session, email: str, password: str) -> User:
    """Same error for unknown email, wrong password and inactive user."""
    user = db.scalar(select(User).where(User.email == email.lower()))
    password_ok = verify_password(user.password_hash if user else dummy_hash(), password)
    if user is None or not password_ok or not user.is_active:
        raise ProblemError(401, "invalid_credentials", "Invalid email or password")
    return user


def demo_user(db: Session) -> User | None:
    """The read-only account that the demo login signs in as, or None when the demo login is off.

    Only an active viewer is ever returned, so a wrong DEMO_LOGIN_EMAIL (an admin, say) cannot give
    anyone more than read access."""
    email = get_settings().demo_login_email.strip().lower()
    if not email:
        return None
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or user.role != "viewer":
        return None
    return user


def issue_tokens(db: Session, user: User) -> TokenPair:
    access = create_access_token(user.id)
    refresh, jti, expires_at = create_refresh_token(user.id)
    db.add(RefreshToken(jti=jti, user_id=user.id, expires_at=expires_at))
    db.commit()
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=get_settings().access_token_minutes * 60,
    )


def rotate_refresh_token(db: Session, token: str) -> TokenPair:
    claims = decode_token(token, "refresh")
    user_id = int(claims["sub"])
    # Revoke in one conditional UPDATE so two concurrent refreshes cannot both succeed.
    result = db.execute(
        update(RefreshToken)
        .where(
            RefreshToken.jti == claims["jti"],
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC))
    )
    if result.rowcount != 1:
        db.rollback()
        raise ProblemError(401, "invalid_token", "Refresh token is revoked or unknown")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        db.commit()  # keep the revocation
        raise ProblemError(401, "invalid_token", "Refresh token is revoked or unknown")
    return issue_tokens(db, user)
