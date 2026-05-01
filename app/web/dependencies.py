from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.models import User, UserType
from app.db.session import get_db


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if token is None:
        token = request.cookies.get("airdock_access")

    payload = decode_access_token(token) if token else None
    username = payload.get("sub") if payload else None
    if not isinstance(username, str):
        raise _auth_error(request)

    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        raise _auth_error(request)

    return user


def get_optional_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    token = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if token is None:
        token = request.cookies.get("airdock_access")

    payload = decode_access_token(token) if token else None
    username = payload.get("sub") if payload else None
    if not isinstance(username, str):
        return None

    return db.scalar(select(User).where(User.username == username))


def can_manage(current_user: User) -> bool:
    return current_user.user_type.can_manage


def _auth_error(request: Request) -> HTTPException:
    accepts = request.headers.get("accept", "")
    if "text/html" in accepts:
        return HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/dashboard/login"},
        )

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
