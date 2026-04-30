from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_token,
    verify_password,
)
from app.db.models import AuthSession, User


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.rsa_password):
        return None
    return user


def create_auth_pair(db: Session, user: User) -> tuple[str, str]:
    access_token = create_access_token(user.username)
    refresh_token = create_refresh_token()
    db.add(
        AuthSession(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            expires_at=datetime.utcnow() + timedelta(days=settings.refresh_token_days),
        )
    )
    db.commit()
    return access_token, refresh_token


def refresh_auth_pair(db: Session, refresh_token: str) -> tuple[str, str, User] | None:
    session = db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == hash_token(refresh_token))
    )
    now = datetime.utcnow()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None

    session.revoked_at = now
    access_token = create_access_token(session.user.username)
    new_refresh_token = create_refresh_token()
    db.add(
        AuthSession(
            user_id=session.user_id,
            refresh_token_hash=hash_token(new_refresh_token),
            expires_at=now + timedelta(days=settings.refresh_token_days),
        )
    )
    db.commit()
    return access_token, new_refresh_token, session.user


def revoke_refresh_token(db: Session, refresh_token: str | None) -> None:
    if not refresh_token:
        return

    session = db.scalar(
        select(AuthSession).where(AuthSession.refresh_token_hash == hash_token(refresh_token))
    )
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.utcnow()
        db.commit()
