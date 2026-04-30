from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ActivityLog, User
from app.db.session import get_db
from app.services.scheduler import get_scheduler_state
from app.services.task_manager import get_task_manager_state
from app.web.dependencies import can_manage, get_current_user
from app.web.templates import templates


router = APIRouter()


@router.get("/health")
async def health():
    return JSONResponse(
        {
            "status": "ok",
            "http": "OK",
            "checked_at": datetime.utcnow().isoformat(),
            "scheduler": get_scheduler_state(),
            "tasks": get_task_manager_state(),
        }
    )


@router.get("/admin/activity-log")
async def activity_log(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not can_manage(current_user):
        return RedirectResponse("/projects/?error=forbidden", status_code=303)

    events = db.scalars(select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(120)).all()
    return templates.TemplateResponse(
        request,
        "pages/activity_log.html",
        {
            "active_page": "activity_log",
            "current_user": current_user,
            "events": events,
        },
    )


@router.get("/docs/docker-access")
async def docker_access_docs(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request,
        "pages/docs_docker_access.html",
        {
            "active_page": "docs",
            "current_user": current_user,
        },
    )
