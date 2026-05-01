from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import User, UserType
from app.db.session import get_db
from app.web.dependencies import can_manage, get_current_user
from app.web.templates import templates


router = APIRouter()


@router.get("/")
async def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return templates.TemplateResponse(
        request,
        "pages/users.html",
        {
            "active_page": "users",
            "users": users,
            "roles": list(UserType),
            "current_user": current_user,
            "can_manage": can_manage(current_user),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    user_type: UserType = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_manage(current_user):
        return RedirectResponse("/dashboard/users/?error=forbidden", status_code=303)

    db.add(
        User(
            username=username.strip(),
            rsa_password=hash_password(password),
            user_type=user_type,
        )
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse("/dashboard/users/?error=duplicate", status_code=303)

    return RedirectResponse("/dashboard/users/", status_code=303)
