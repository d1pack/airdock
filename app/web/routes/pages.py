from fastapi import APIRouter, Depends, Request

from app.db.models import User
from app.web.dependencies import get_current_user
from app.web.templates import templates


router = APIRouter()


@router.get("/")
async def dashboard(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "pages/dashboard.html",
        {"active_page": "dashboard", "current_user": current_user},
    )
