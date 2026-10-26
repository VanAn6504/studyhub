"""Private profile/security APIs. Password changes revoke every old session."""
from collections import defaultdict, deque
from threading import Lock
import time

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import AuthSession, User
from app.security import COOKIE_NAME, AuthContext, get_auth, hash_password, utcnow, verify_password
from app.website_schemas import PasswordInput, ProfileOutput, ProfilePatch

router = APIRouter(prefix='/me', tags=['private account'])
_password_hits = defaultdict(deque)
_password_lock = Lock()


def password_limit(user_id):
    now = time.monotonic()
    with _password_lock:
        for key in list(_password_hits):
            while _password_hits[key] and _password_hits[key][0] <= now - 600:
                _password_hits[key].popleft()
            if not _password_hits[key]:
                del _password_hits[key]
        hits = _password_hits[user_id]
        if len(hits) >= 5:
            raise ApiError(429, 'PASSWORD_RATE_LIMIT', 'Quá nhiều lần đổi mật khẩu. Vui lòng thử lại sau10 phút.')
        hits.append(now)


@router.get('/profile', response_model=ProfileOutput)
def profile(context: AuthContext = Depends(get_auth)):
    return context.user


@router.patch('/profile', response_model=ProfileOutput)
def update_profile(body: ProfilePatch, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.id == context.user.id).with_for_update().execution_options(populate_existing=True))
    user.display_name, user.bio = body.display_name, body.bio
    db.commit()
    return user


@router.post('/password', status_code=204)
def change_password(body: PasswordInput, response: Response, context: AuthContext = Depends(get_auth), db: Session = Depends(get_db)):
    password_limit(context.user.id)
    user = db.scalar(select(User).where(User.id == context.user.id).with_for_update().execution_options(populate_existing=True))
    session = db.get(AuthSession, context.session.id, populate_existing=True)
    if session.revoked_at is not None:
        raise ApiError(401, 'AUTHENTICATION_REQUIRED', 'Phiên đăng nhập đã hết hạn.')
    if not verify_password(user.password_hash, body.current_password):
        raise ApiError(422, 'CURRENT_PASSWORD_INVALID', 'Mật khẩu hiện tại không đúng.', {'field':'current_password'})
    if body.current_password == body.new_password:
        raise ApiError(422, 'PASSWORD_UNCHANGED', 'Mật khẩu mới phải khác mật khẩu hiện tại.', {'field':'new_password'})
    user.password_hash = hash_password(body.new_password)
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    db.commit()
    response.delete_cookie(COOKIE_NAME, path='/', secure=get_settings().cookie_secure, httponly=True, samesite='lax')
