from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.auth_service import authenticate_user, create_auth_pair, refresh_auth_pair, revoke_refresh_token
from app.web.templates import templates


router = APIRouter()


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "pages/login.html",
        {"error": request.query_params.get("error")},
    )


@router.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, username.strip(), password)
    if user is None:
        return RedirectResponse("/dashboard/login?error=invalid", status_code=303)

    access_token, refresh_token = create_auth_pair(db, user)
    response = RedirectResponse("/dashboard/", status_code=303)
    _set_auth_cookies(response, access_token, refresh_token)
    return response


@router.post("/auth/refresh")
async def refresh(request: Request, db: Session = Depends(get_db)):
    refresh_token = request.cookies.get("airdock_refresh")
    if not refresh_token:
        return RedirectResponse("/dashboard/login?error=expired", status_code=303)

    token_pair = refresh_auth_pair(db, refresh_token)
    if token_pair is None:
        response = RedirectResponse("/dashboard/login?error=expired", status_code=303)
        _clear_auth_cookies(response)
        return response

    access_token, new_refresh_token, _user = token_pair
    response = RedirectResponse("/dashboard/", status_code=303)
    _set_auth_cookies(response, access_token, new_refresh_token)
    return response


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    revoke_refresh_token(db, request.cookies.get("airdock_refresh"))
    response = RedirectResponse("/dashboard/login", status_code=303)
    _clear_auth_cookies(response)
    return response


def _set_auth_cookies(response: RedirectResponse, access_token: str, refresh_token: str) -> None:
    response.set_cookie(
        "airdock_access",
        access_token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.access_token_minutes * 60,
    )
    response.set_cookie(
        "airdock_refresh",
        refresh_token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
    )


def _clear_auth_cookies(response: RedirectResponse) -> None:
    response.delete_cookie("airdock_access")
    response.delete_cookie("airdock_refresh")
