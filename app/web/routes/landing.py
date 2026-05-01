from fastapi import APIRouter, Depends, Request

from app.db.models import User
from app.web.dependencies import get_optional_current_user
from app.web.templates import templates


router = APIRouter()


@router.get("/")
async def landing(request: Request, current_user: User | None = Depends(get_optional_current_user)):
    return templates.TemplateResponse(
        request,
        "pages/landing.html",
        {"active_page": "home", "current_user": current_user},
    )
