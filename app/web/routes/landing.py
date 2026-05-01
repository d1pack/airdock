from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/")
async def landing():
    return RedirectResponse("/dashboard/login", status_code=303)


@router.get("/login")
async def login_alias():
    return RedirectResponse("/dashboard/login", status_code=303)
