from functools import lru_cache

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import get_settings
from app.core.errors import ProblemError
from app.core.ratelimit import LoginGuard
from app.schemas.auth import DemoStatus, LoginIn, RefreshIn, TokenPair
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@lru_cache
def get_login_guard() -> LoginGuard:
    settings = get_settings()
    return LoginGuard(
        max_failures=settings.login_max_failures,
        lockout_seconds=settings.login_lockout_seconds,
        per_minute=settings.login_rate_limit_per_minute,
    )


@router.post("/login", response_model=TokenPair)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    guard = get_login_guard()
    email = body.email.strip().lower()
    guard.check(email, request.client.host if request.client else "unknown")
    try:
        user = auth_service.authenticate(db, body.email, body.password)
    except ProblemError as error:
        if error.code == "invalid_credentials":
            guard.record_failure(email)
        raise
    guard.record_success(email)
    return auth_service.issue_tokens(db, user)


@router.get("/demo", response_model=DemoStatus)
def demo_status(db: Session = Depends(get_db)) -> DemoStatus:
    """Tells the login page whether to offer "Try the demo"."""
    user = auth_service.demo_user(db)
    return DemoStatus(enabled=user is not None, email=user.email if user else None)


@router.post("/demo", response_model=TokenPair)
def demo_login(request: Request, db: Session = Depends(get_db)) -> TokenPair:
    """Signs in as the read-only demo account, without a password. Off unless DEMO_LOGIN_EMAIL is set."""
    get_login_guard().check("demo-login", request.client.host if request.client else "unknown")
    user = auth_service.demo_user(db)
    if user is None:
        raise ProblemError(404, "demo_unavailable", "The demo login is not available.")
    return auth_service.issue_tokens(db, user)


@router.post("/refresh", response_model=TokenPair)
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> TokenPair:
    return auth_service.rotate_refresh_token(db, body.refresh_token)
