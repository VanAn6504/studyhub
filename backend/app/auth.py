from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import User
from app.schemas import AuthOutput, LoginInput, RegisterInput, UserOutput
from app.security import (
    COOKIE_NAME, SESSION_SECONDS, AuthContext, auth_rate_limiter, create_session,
    dummy_password_hash, get_auth, hash_password, password_hasher, require_csrf, resolve_auth,
    utcnow, verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def public_auth_guard(request: Request, db: Session):
    auth_rate_limiter.check(request)
    existing = resolve_auth(request, db, required=False)
    if existing:
        require_csrf(request, existing)


@router.post("/register", response_model=UserOutput, status_code=201)
def register(body: RegisterInput, request: Request, db: Session = Depends(get_db)):
    public_auth_guard(request, db)
    if db.scalar(select(User.id).where(User.email == str(body.email))):
        raise ApiError(409, "EMAIL_EXISTS", "Email đã được đăng ký.")
    user = User(email=str(body.email), password_hash=hash_password(body.password), display_name=body.display_name, role="student")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=AuthOutput)
def login(body: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    public_auth_guard(request, db)
    user = db.scalar(select(User).where(User.email == str(body.email)))
    valid_password = verify_password(user.password_hash if user else dummy_password_hash, body.password)
    if not user or not valid_password or not user.is_active:
        raise ApiError(401, "INVALID_CREDENTIALS", "Email hoặc mật khẩu không đúng.")
    if password_hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    session, token = create_session(db, user)
    db.commit()
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_SECONDS, httponly=True, secure=get_settings().cookie_secure, samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return AuthOutput(user=UserOutput.model_validate(user), csrf_token=session.csrf_token)


@router.get("/me", response_model=AuthOutput)
def me(response: Response, context: AuthContext = Depends(get_auth)):
    response.headers["Cache-Control"] = "no-store"
    return AuthOutput(user=UserOutput.model_validate(context.user), csrf_token=context.session.csrf_token)


@router.post("/logout", status_code=204)
def logout(response: Response, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    context.session.revoked_at = utcnow()
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", secure=get_settings().cookie_secure, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "no-store"
