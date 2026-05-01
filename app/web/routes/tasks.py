from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import AnsiblePlaybook, Project, ProjectUser, Task, User
from app.db.session import get_db
from app.services.task_manager import enqueue_task_id, stop_task_id
from app.web.dependencies import can_manage, get_current_user
from app.web.templates import templates


router = APIRouter()


@router.get("/")
async def index(
    request: Request,
    status: str = Query(""),
    created_from: str = Query(""),
    created_to: str = Query(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    status = status if status in _TASK_STATUS_FILTERS else ""
    query = (
        select(Task)
        .options(selectinload(Task.project), selectinload(Task.playbook), selectinload(Task.pipeline), selectinload(Task.owner))
    )
    if not can_manage(current_user):
        query = query.where((Task.owner_id == current_user.id) | (Task.owner_id.is_(None)))
    if status:
        query = query.where(Task.status == status)
    created_from_dt = _parse_msk_date_start(created_from)
    created_to_dt = _parse_msk_date_end(created_to)
    if created_from_dt is not None:
        query = query.where(Task.created_at >= created_from_dt)
    if created_to_dt is not None:
        query = query.where(Task.created_at < created_to_dt)
    query = query.order_by(Task.created_at.desc()).limit(160)
    tasks = db.scalars(query).all()
    playbooks = _available_playbooks(db, current_user)
    return templates.TemplateResponse(
        request,
        "pages/tasks.html",
        {
            "active_page": "tasks",
            "current_user": current_user,
            "tasks": tasks,
            "playbooks": playbooks,
            "can_manage_tasks": can_manage(current_user),
            "filters": {
                "status": status,
                "created_from": created_from,
                "created_to": created_to,
            },
            "status_filters": _TASK_STATUS_FILTERS,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/")
async def create_task(
    title: str = Form(""),
    playbook_id: int = Form(...),
    scheduled_at_msk: str = Form(""),
    action: str = Form("create"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    playbook = db.scalar(
        select(AnsiblePlaybook)
        .where(AnsiblePlaybook.id == playbook_id)
        .options(selectinload(AnsiblePlaybook.project))
    )
    if playbook is None or not _can_use_playbook(current_user, playbook):
        return RedirectResponse("/dashboard/tasks/?error=missing_playbook", status_code=303)

    should_enqueue = action == "enqueue"
    scheduled_at = _parse_msk_datetime(scheduled_at_msk)
    should_schedule = action == "schedule" and scheduled_at is not None
    task = Task(
        title=title.strip() or f"Запуск playbook {playbook.name}",
        task_type="playbook",
        status="queued" if should_enqueue else "scheduled" if should_schedule else "draft",
        owner_id=current_user.id,
        owner_name=current_user.username,
        project_id=playbook.project_id,
        playbook_id=playbook.id,
        scheduled_at=scheduled_at if should_schedule else None,
        queued_at=datetime.utcnow() if should_enqueue else None,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    if should_enqueue:
        await enqueue_task_id(task.id)
    return RedirectResponse(f"/dashboard/tasks/{task.id}", status_code=303)


@router.get("/{task_id}")
async def detail(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.scalar(
        select(Task)
        .where(Task.id == task_id)
        .options(selectinload(Task.project), selectinload(Task.playbook), selectinload(Task.pipeline), selectinload(Task.owner))
    )
    if task is None:
        return RedirectResponse("/dashboard/tasks/?error=missing", status_code=303)
    if not _can_view_task(current_user, task):
        return RedirectResponse("/dashboard/tasks/?error=forbidden", status_code=303)

    playbooks = []
    if task.project_id:
        playbooks = db.scalars(
            select(AnsiblePlaybook).where(AnsiblePlaybook.project_id == task.project_id).order_by(AnsiblePlaybook.name)
        ).all()
    projects = db.scalars(select(Project).order_by(Project.name)).all() if can_manage(current_user) else []
    return templates.TemplateResponse(
        request,
        "pages/task_detail.html",
        {
            "active_page": "tasks",
            "current_user": current_user,
            "task": task,
            "playbooks": playbooks,
            "projects": projects,
            "can_edit_task": _can_edit_task(current_user, task),
        },
    )


@router.post("/{task_id}")
async def update_task(
    task_id: int,
    title: str = Form(...),
    playbook_id: int | None = Form(None),
    scheduled_at_msk: str = Form(""),
    action: str = Form("save"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.get(Task, task_id)
    if task is None:
        return RedirectResponse("/dashboard/tasks/?error=missing", status_code=303)
    if not _can_edit_task(current_user, task):
        return RedirectResponse(f"/dashboard/tasks/{task_id}?error=forbidden", status_code=303)

    task.title = title.strip() or task.title
    if task.task_type == "playbook":
        playbook = db.get(AnsiblePlaybook, playbook_id) if playbook_id else None
        if playbook is not None and playbook.project_id == task.project_id:
            task.playbook_id = playbook.id
    scheduled_at = _parse_msk_datetime(scheduled_at_msk)
    if action == "schedule" and scheduled_at is not None:
        task.scheduled_at = scheduled_at
        task.status = "scheduled"
        task.queued_at = None
        task.started_at = None
        task.finished_at = None
        task.error = ""
    elif action == "clear_schedule":
        task.scheduled_at = None
        if task.status == "scheduled":
            task.status = "draft"
    db.commit()
    return RedirectResponse(f"/dashboard/tasks/{task_id}", status_code=303)


@router.post("/{task_id}/enqueue")
async def enqueue_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.get(Task, task_id)
    if task is None:
        return RedirectResponse("/dashboard/tasks/?error=missing", status_code=303)
    if not _can_edit_task(current_user, task):
        return RedirectResponse(f"/dashboard/tasks/{task_id}?error=forbidden", status_code=303)
    task.status = "queued"
    task.error = ""
    task.scheduled_at = None
    task.queued_at = datetime.utcnow()
    db.commit()
    await enqueue_task_id(task.id)
    return RedirectResponse(f"/dashboard/tasks/{task_id}", status_code=303)


@router.post("/{task_id}/stop")
async def stop_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    task = db.get(Task, task_id)
    if task is None:
        return RedirectResponse("/dashboard/tasks/?error=missing", status_code=303)
    if not _can_edit_task(current_user, task):
        return RedirectResponse(f"/dashboard/tasks/{task_id}?error=forbidden", status_code=303)
    stop_task_id(task.id)
    return RedirectResponse(f"/dashboard/tasks/{task_id}", status_code=303)


def _can_view_task(user: User, task: Task) -> bool:
    return can_manage(user) or task.owner_id == user.id or task.owner_id is None


def _can_edit_task(user: User, task: Task) -> bool:
    return can_manage(user) or task.owner_id == user.id


def _parse_msk_datetime(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        msk_time = datetime.fromisoformat(value)
    except ValueError:
        return None
    return msk_time - timedelta(hours=3)


def _parse_msk_date_start(value: str) -> datetime | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        local_date = datetime.fromisoformat(value)
    except ValueError:
        return None
    return local_date - timedelta(hours=3)


def _parse_msk_date_end(value: str) -> datetime | None:
    start = _parse_msk_date_start(value)
    return start + timedelta(days=1) if start else None


def _available_playbooks(db: Session, user: User) -> list[AnsiblePlaybook]:
    query = select(AnsiblePlaybook).options(selectinload(AnsiblePlaybook.project)).order_by(AnsiblePlaybook.name)
    if not can_manage(user):
        query = query.join(Project).outerjoin(ProjectUser, ProjectUser.project_id == Project.id).where(
            (Project.owner_id == user.id) | (ProjectUser.user_id == user.id)
        )
    return db.scalars(query).unique().all()


def _can_use_playbook(user: User, playbook: AnsiblePlaybook) -> bool:
    project = playbook.project
    if project is None:
        return False
    if can_manage(user) or project.owner_id == user.id:
        return True
    return any(access.user_id == user.id for access in project.users)


_TASK_STATUS_FILTERS = {
    "draft": "Черновик",
    "scheduled": "Запланирована",
    "queued": "В очереди",
    "running": "Выполняется",
    "cancel_requested": "Останавливается",
    "cancelled": "Остановлена",
    "success": "Выполнена",
    "failed": "Ошибка",
}
