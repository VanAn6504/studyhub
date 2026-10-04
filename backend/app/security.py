from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
import secrets
import time
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import AuthSession, User

COOKIE_NAME = "studyhub_access"
SESSION_SECONDS = 24 * 60 * 60
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
password_hasher = PasswordHasher()
# A valid Argon2 hash is used even for nonexistent accounts to reduce timing differences.
dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@dataclass
class AuthContext:
    user: User
    session: AuthSession


def resolve_auth(request: Request, db: Session, required: bool = True) -> AuthContext | None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        try:
            payload = jwt.decode(
                token, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"],
                options={"require": ["sub", "jti", "iat", "exp"]},
            )
            user_id, session_id = UUID(payload["sub"]), UUID(payload["jti"])
        except (jwt.InvalidTokenError, ValueError, TypeError, KeyError, AttributeError):
            payload = None
        if payload is not None:
            session = db.get(AuthSession, session_id)
            if session and session.user_id == user_id and session.revoked_at is None and session.expires_at > utcnow():
                user = db.get(User, user_id)
                if user and user.is_active:
                    return AuthContext(user, session)
    if required:
        raise ApiError(401, "AUTHENTICATION_REQUIRED", "Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
    return None


def require_csrf(request: Request, context: AuthContext) -> None:
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not secrets.compare_digest(supplied.encode("utf-8"), context.session.csrf_token.encode("utf-8")):
        raise ApiError(403, "CSRF_INVALID", "Token bảo vệ yêu cầu không hợp lệ.")


def get_auth(request: Request, db: Session = Depends(get_db)) -> AuthContext:
    context = resolve_auth(request, db)
    if request.method in UNSAFE_METHODS:
        require_csrf(request, context)
    return context


def require_teacher(context: AuthContext = Depends(get_auth)) -> AuthContext:
    if context.user.role != "teacher":
        raise ApiError(403, "ROLE_FORBIDDEN", "Chức năng này dành cho giảng viên.")
    return context


def create_session(db: Session, user: User) -> tuple[AuthSession, str]:
    now = utcnow()
    session = AuthSession(user_id=user.id, csrf_token=secrets.token_urlsafe(32), expires_at=now + timedelta(seconds=SESSION_SECONDS))
    db.add(session)
    db.flush()
    token = jwt.encode({"sub": str(user.id), "jti": str(session.id), "iat": now, "exp": session.expires_at}, get_settings().jwt_secret.get_secret_value(), algorithm="HS256")
    return session, token


class AuthRateLimiter:
    """Single-process local-demo limiter. Deployments need a shared limiter."""

    def __init__(self):
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = Lock()

    def check(self, request: Request):
        # Ignore forwarded IP headers; proxy trust has not been configured.
        key = request.client.host if request.client else "unknown"
        settings, now = get_settings(), time.monotonic()
        with self.lock:
            for stale_key in list(self.hits):
                history = self.hits[stale_key]
                while history and history[0] <= now - settings.auth_rate_window_seconds:
                    history.popleft()
                if not history:
                    del self.hits[stale_key]
            history = self.hits[key]
            if len(history) >= settings.auth_rate_limit:
                raise ApiError(429, "AUTH_RATE_LIMIT", "Quá nhiều lần thử. Vui lòng thử lại sau.")
            history.append(now)


auth_rate_limiter = AuthRateLimiter()
