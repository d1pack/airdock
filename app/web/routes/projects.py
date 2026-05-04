from datetime import datetime
import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.security import encrypt_secret
from app.db.models import ActivityLog, AnsiblePlaybook, AnsiblePlaybookFile, Node, Project, ProjectContainer, ProjectNode, ProjectUser, User
from app.db.session import get_db
from app.services.task_manager import create_playbook_task, enqueue_task_id, ensure_metrics_task
from app.services.server_metrics import (
    DockerContainerInfo,
    DockerImageInfo,
    MetricsUnavailableError,
    ServerMetrics,
    collect_node_containers,
    collect_node_container_logs,
    collect_node_images,
    collect_node_metrics,
    run_node_container_action,
    run_node_image_delete,
)
from app.web.dependencies import can_manage, get_current_user
from app.web.templates import templates


router = APIRouter()


@router.get("/")
async def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(Project)
        .options(selectinload(Project.nodes), selectinload(Project.users).selectinload(ProjectUser.user))
        .order_by(Project.created_at.desc())
    )
    if not can_manage(current_user):
        query = query.join(ProjectUser).where(ProjectUser.user_id == current_user.id)

    projects = db.execute(query).scalars().unique().all()
    return templates.TemplateResponse(
        request,
        "pages/projects.html",
        {
            "active_page": "projects",
            "projects": projects,
            "current_user": current_user,
            "can_manage": can_manage(current_user),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/")
async def create_project(
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(name=name.strip(), description=description.strip(), owner_id=current_user.id)
    db.add(project)
    try:
        db.flush()
        db.add(ProjectUser(project_id=project.id, user_id=current_user.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse("/dashboard/projects/?error=duplicate", status_code=303)

    return RedirectResponse(f"/dashboard/projects/{project.id}", status_code=303)


@router.get("/{project_id}")
async def detail(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    if project is None:
        return RedirectResponse("/dashboard/projects/?error=missing", status_code=303)
    if not _can_view_project(current_user, project):
        return RedirectResponse("/dashboard/projects/?error=forbidden", status_code=303)

    metrics_task = ensure_metrics_task(db, project=project)
    if metrics_task is not None:
        await enqueue_task_id(metrics_task.id)
    return templates.TemplateResponse(
        request,
        "pages/project_detail.html",
        {
            "active_page": "projects",
            "project": project,
            "current_user": current_user,
            "can_edit_project": _can_edit_project(current_user, project),
            "error": request.query_params.get("error"),
        },
    )


@router.get("/{project_id}/settings")
async def settings(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    if project is None:
        return RedirectResponse("/dashboard/projects/?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    users = db.scalars(select(User).order_by(User.username)).all()
    all_nodes = db.scalars(select(Node).order_by(Node.name)).all()
    linked_node_ids = {node.id for node in project.nodes}
    available_nodes = [node for node in all_nodes if node.id not in linked_node_ids]
    return templates.TemplateResponse(
        request,
        "pages/project_settings.html",
        {
            "active_page": "projects",
            "project": project,
            "users": users,
            "nodes": available_nodes,
            "current_user": current_user,
            "can_edit_project": True,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{project_id}/settings")
async def update_project_settings(
    project_id: int,
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    if project is None:
        return RedirectResponse("/dashboard/projects/?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    project.name = name.strip()
    project.description = description.strip()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(f"/dashboard/projects/{project_id}/settings?error=duplicate", status_code=303)
    return RedirectResponse(f"/dashboard/projects/{project_id}/settings", status_code=303)


@router.get("/{project_id}/metrics")
async def metrics(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    if project is None:
        return JSONResponse({"detail": "Project not found."}, status_code=404)
    if not _can_view_project(current_user, project):
        return JSONResponse({"detail": "Forbidden."}, status_code=403)

    metrics_task = ensure_metrics_task(db, project=project)
    if metrics_task is not None:
        await enqueue_task_id(metrics_task.id)

    try:
        payload = await run_in_threadpool(_build_project_metrics, project)
    except MetricsUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=502)

    _sync_node_statuses(db, project, set(payload["online_node_ids"]))

    return JSONResponse(payload)


@router.post("/{project_id}/users")
async def add_project_user(
    project_id: int,
    user_id: int = Form(...),
    next: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    if project is None:
        return RedirectResponse("/dashboard/projects/?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    db.add(ProjectUser(project_id=project_id, user_id=user_id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(f"{_project_return_url(project_id, next)}?error=duplicate_user", status_code=303)
    return RedirectResponse(_project_return_url(project_id, next), status_code=303)


@router.post("/{project_id}/nodes")
async def assign_node(
    project_id: int,
    node_id: int = Form(...),
    next: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    node = db.get(Node, node_id)
    if project is None or node is None:
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    db.add(ProjectNode(project_id=project.id, node_id=node.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return RedirectResponse(_project_return_url(project_id, next), status_code=303)


@router.post("/{project_id}/nodes/create")
async def create_and_assign_node(
    project_id: int,
    name: str = Form(...),
    description: str = Form(""),
    server_ip: str = Form(...),
    server_user: str = Form(...),
    ssh_key: str = Form(...),
    next: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    if project is None:
        return RedirectResponse("/dashboard/projects/?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    node = Node(
        name=name.strip(),
        description=description.strip(),
        icon="truck",
        status="down",
        server_ip=server_ip.strip(),
        server_user=server_user.strip(),
        ssh_key=encrypt_secret(ssh_key),
    )
    db.add(node)
    try:
        db.flush()
        db.add(ProjectNode(project_id=project.id, node_id=node.id))
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(f"{_project_return_url(project_id, next)}?error=duplicate_node", status_code=303)
    return RedirectResponse(_project_return_url(project_id, next), status_code=303)


@router.post("/{project_id}/containers/{node_id}/{container_id}/{action}")
async def container_action(
    project_id: int,
    node_id: int,
    container_id: str,
    action: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    node = db.get(Node, node_id)
    if project is None or node is None or not _project_has_node(project, node.id):
        return JSONResponse({"detail": "Связанный курьер не найден."}, status_code=404)
    if not _can_edit_project(current_user, project):
        return JSONResponse({"detail": "Недостаточно прав для управления контейнером."}, status_code=403)
    if action not in {"stop", "restart", "delete"}:
        return JSONResponse({"detail": "Действие не поддерживается."}, status_code=400)

    try:
        output = await run_in_threadpool(run_node_container_action, node, container_id, action)
    except MetricsUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=502)

    return JSONResponse(
        {
            "status": "ok",
            "action": action,
            "container_id": container_id,
            "output": output,
        }
    )


@router.get("/{project_id}/containers/{node_id}/{container_id}/logs")
async def container_logs(
    project_id: int,
    node_id: int,
    container_id: str,
    tail: int = 300,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    node = db.get(Node, node_id)
    if project is None or node is None or not _project_has_node(project, node.id):
        return JSONResponse({"detail": "Связанный курьер не найден."}, status_code=404)
    if not _can_view_project(current_user, project):
        return JSONResponse({"detail": "Недостаточно прав для просмотра логов контейнера."}, status_code=403)

    try:
        output = await run_in_threadpool(collect_node_container_logs, node, container_id, tail)
    except MetricsUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=502)

    return JSONResponse(
        {
            "container_id": container_id,
            "node_id": str(node.id),
            "node_name": node.name,
            "server_ip": node.server_ip,
            "tail": min(max(tail, 20), 1000),
            "logs": output or "Логи контейнера пустые.",
        }
    )


@router.post("/{project_id}/images/{node_id}/{image_id}/delete")
async def image_delete(
    project_id: int,
    node_id: int,
    image_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    node = db.get(Node, node_id)
    if project is None or node is None or not _project_has_node(project, node.id):
        return JSONResponse({"detail": "Связанный курьер не найден."}, status_code=404)
    if not _can_edit_project(current_user, project):
        return JSONResponse({"detail": "Недостаточно прав для удаления образа."}, status_code=403)

    try:
        output = await run_in_threadpool(run_node_image_delete, node, image_id)
    except MetricsUnavailableError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=502)

    return JSONResponse(
        {
            "status": "ok",
            "action": "delete",
            "image_id": image_id,
            "output": output,
        }
    )


@router.post("/{project_id}/containers")
async def add_container(
    project_id: int,
    node_id: int = Form(...),
    container_name: str = Form(...),
    container_id: str = Form(""),
    image: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    node = db.get(Node, node_id)
    if project is None or node is None or not _project_has_node(project, node.id):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    db.add(
        ProjectContainer(
            project_id=project.id,
            node_id=node.id,
            container_name=container_name.strip(),
            container_id=container_id.strip(),
            image=image.strip(),
        )
    )
    db.commit()
    return RedirectResponse(f"/dashboard/projects/{project_id}", status_code=303)


def _get_project(db: Session, project_id: int) -> Project | None:
    return db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(
            selectinload(Project.owner),
            selectinload(Project.node_links).selectinload(ProjectNode.node),
            selectinload(Project.users).selectinload(ProjectUser.user),
            selectinload(Project.containers).selectinload(ProjectContainer.node),
            selectinload(Project.ansible_playbooks).selectinload(AnsiblePlaybook.files),
        )
    )


def _can_edit_project(user: User, project: Project) -> bool:
    return user.id == project.owner_id or can_manage(user)


def _can_view_project(user: User, project: Project) -> bool:
    if _can_edit_project(user, project):
        return True
    return any(access.user_id == user.id for access in project.users)


def _project_has_node(project: Project, node_id: int) -> bool:
    return any(node.id == node_id for node in project.nodes)


def _project_return_url(project_id: int, target: str) -> str:
    return f"/dashboard/projects/{project_id}/settings" if target == "settings" else f"/dashboard/projects/{project_id}"


@router.post("/{project_id}/playbooks")
async def add_playbook(
    project_id: int,
    name: str = Form(...),
    description: str = Form(""),
    run_command: str = Form("ansible-playbook -i {inventory} {playbook}"),
    content: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    if project is None:
        return RedirectResponse("/dashboard/projects/?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    db.add(
        AnsiblePlaybook(
            project_id=project.id,
            name=name.strip(),
            description=description.strip(),
            run_command=_normalize_playbook_run_command(run_command),
            content=content.strip(),
        )
    )
    db.commit()
    return RedirectResponse(f"/dashboard/projects/{project_id}", status_code=303)


@router.post("/{project_id}/playbooks/{playbook_id}/update")
async def update_playbook(
    project_id: int,
    playbook_id: int,
    name: str = Form(...),
    target_project_id: int = Form(...),
    description: str = Form(""),
    run_command: str = Form("ansible-playbook -i {inventory} {playbook}"),
    content: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    playbook = db.get(AnsiblePlaybook, playbook_id)
    if project is None or playbook is None or playbook.project_id != project.id:
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    target_project = db.get(Project, target_project_id)
    if target_project is None:
        return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}?error=missing", status_code=303)
    if not _can_edit_project(current_user, target_project):
        return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}?error=forbidden", status_code=303)

    playbook.name = name.strip()
    playbook.project_id = target_project.id
    playbook.description = description.strip()
    playbook.run_command = _normalize_playbook_run_command(run_command)
    playbook.content = content.strip()
    db.commit()
    return RedirectResponse(f"/dashboard/projects/{target_project.id}/playbooks/{playbook_id}", status_code=303)


@router.post("/{project_id}/playbooks/{playbook_id}/delete")
async def delete_playbook(
    project_id: int,
    playbook_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    playbook = db.get(AnsiblePlaybook, playbook_id)
    if project is None or playbook is None or playbook.project_id != project.id:
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    db.delete(playbook)
    db.commit()
    return RedirectResponse(f"/dashboard/projects/{project_id}", status_code=303)


@router.post("/{project_id}/playbooks/{playbook_id}/clone")
async def clone_playbook(
    project_id: int,
    playbook_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    playbook = db.get(AnsiblePlaybook, playbook_id)
    if project is None or playbook is None or playbook.project_id != project.id:
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    cloned_playbook = AnsiblePlaybook(
        project_id=project.id,
        name=_clone_playbook_name(playbook.name),
        description=playbook.description,
        run_command=playbook.run_command,
        content=playbook.content,
    )
    db.add(cloned_playbook)
    db.flush()
    for file in playbook.files:
        db.add(AnsiblePlaybookFile(playbook_id=cloned_playbook.id, path=file.path, content=file.content))
    db.commit()
    return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{cloned_playbook.id}", status_code=303)


@router.post("/{project_id}/playbooks/{playbook_id}/run")
async def run_project_playbook(
    project_id: int,
    playbook_id: int,
    next: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    playbook = db.get(AnsiblePlaybook, playbook_id)
    if project is None or playbook is None or playbook.project_id != project.id:
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=forbidden", status_code=303)

    task = create_playbook_task(db, project=project, playbook=playbook, user=current_user)
    playbook.last_status = "queued"
    db.commit()
    await enqueue_task_id(task.id)

    if next == "playbook":
        return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}?task={task.id}", status_code=303)
    return RedirectResponse(f"/dashboard/projects/{project_id}?task={task.id}", status_code=303)


@router.post("/{project_id}/playbooks/{playbook_id}/files")
async def add_playbook_file(
    project_id: int,
    playbook_id: int,
    path: str = Form(...),
    content: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    playbook = db.get(AnsiblePlaybook, playbook_id)
    if project is None or playbook is None or playbook.project_id != project.id:
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}?error=forbidden", status_code=303)

    db.add(AnsiblePlaybookFile(playbook_id=playbook.id, path=_normalize_playbook_file_path(path), content=content))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}?error=duplicate_file", status_code=303)
    return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}", status_code=303)


@router.post("/{project_id}/playbooks/{playbook_id}/files/{file_id}/update")
async def update_playbook_file(
    project_id: int,
    playbook_id: int,
    file_id: int,
    path: str = Form(...),
    content: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    playbook = db.get(AnsiblePlaybook, playbook_id)
    file = db.get(AnsiblePlaybookFile, file_id)
    if project is None or playbook is None or file is None or playbook.project_id != project.id or file.playbook_id != playbook.id:
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}?error=forbidden", status_code=303)

    file.path = _normalize_playbook_file_path(path)
    file.content = content
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}?error=duplicate_file", status_code=303)
    return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}", status_code=303)


@router.post("/{project_id}/playbooks/{playbook_id}/files/{file_id}/delete")
async def delete_playbook_file(
    project_id: int,
    playbook_id: int,
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    playbook = db.get(AnsiblePlaybook, playbook_id)
    file = db.get(AnsiblePlaybookFile, file_id)
    if project is None or playbook is None or file is None or playbook.project_id != project.id or file.playbook_id != playbook.id:
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=missing", status_code=303)
    if not _can_edit_project(current_user, project):
        return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}?error=forbidden", status_code=303)

    db.delete(file)
    db.commit()
    return RedirectResponse(f"/dashboard/projects/{project_id}/playbooks/{playbook_id}", status_code=303)


@router.get("/{project_id}/playbooks/{playbook_id}")
async def playbook_detail(
    project_id: int,
    playbook_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    playbook = db.get(AnsiblePlaybook, playbook_id)
    if project is None or playbook is None or playbook.project_id != project.id:
        return RedirectResponse(f"/dashboard/projects/{project_id}?error=missing", status_code=303)
    if not _can_view_project(current_user, project):
        return RedirectResponse("/dashboard/projects/?error=forbidden", status_code=303)

    return templates.TemplateResponse(
        request,
        "pages/playbook_detail.html",
        {
            "active_page": "projects",
            "project": project,
            "playbook": playbook,
            "editable_projects": _editable_projects(db, current_user),
            "current_user": current_user,
            "can_edit_project": _can_edit_project(current_user, project),
            "events": _playbook_activity_events(db, playbook.id),
            "error": request.query_params.get("error"),
        },
    )


def _add_activity_log(
    db: Session,
    *,
    level: str,
    event_type: str,
    message: str,
    project_id: int | None = None,
    node_id: int | None = None,
    payload: dict | None = None,
) -> None:
    db.add(
        ActivityLog(
            level=level,
            event_type=event_type,
            message=message,
            project_id=project_id,
            node_id=node_id,
            payload=json.dumps(payload or {}, ensure_ascii=False),
            created_at=datetime.utcnow(),
        )
    )


def _playbook_activity_events(db: Session, playbook_id: int) -> list[dict]:
    events = db.scalars(
        select(ActivityLog)
        .where(
            ActivityLog.event_type.in_(("ansible.playbook.run", "ansible.playbook.failed")),
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(120)
    ).all()
    playbook_events: list[dict] = []
    for event in events:
        try:
            payload = json.loads(event.payload or "{}")
        except json.JSONDecodeError:
            payload = {}
        if payload.get("playbook_id") == playbook_id:
            playbook_events.append({"event": event, "payload": payload})
        if len(playbook_events) >= 20:
            break
    return playbook_events


def _editable_projects(db: Session, user: User) -> list[Project]:
    query = select(Project).order_by(Project.name.asc())
    if not can_manage(user):
        query = query.where(Project.owner_id == user.id)
    return list(db.scalars(query).all())


def _clone_playbook_name(name: str) -> str:
    base_name = " ".join((name or "playbook").strip().split()) or "playbook"
    cloned_name = f"{base_name} копия"
    return cloned_name[:160]


def _normalize_playbook_run_command(command: str) -> str:
    normalized = (command or "").strip()
    return normalized[:500] if normalized else "ansible-playbook -i {inventory} {playbook}"


def _normalize_playbook_file_path(path: str) -> str:
    parts = []
    for part in path.replace("\\", "/").split("/"):
        part = part.strip()
        if not part or part in {".", ".."}:
            continue
        parts.append(part)
    return "/".join(parts)[:240] or "file.txt"


_METRICS_HISTORY: dict[int, dict[str, list[float]]] = {}


def _build_project_metrics(project: Project) -> dict:
    nodes = list(project.nodes)
    if not nodes:
        raise MetricsUnavailableError("В проекте нет привязанных курьеров.")

    samples: list[ServerMetrics] = []
    containers: list[dict[str, str]] = []
    images: list[dict[str, str]] = []
    online_node_ids: list[int] = []
    errors: list[str] = []
    for node in nodes:
        try:
            samples.append(collect_node_metrics(node))
            online_node_ids.append(node.id)
            try:
                containers.extend(_containers_payload(node, collect_node_containers(node)))
                images.extend(_images_payload(node, collect_node_images(node)))
            except MetricsUnavailableError as exc:
                errors.append(f"{node.name}: {exc}")
        except MetricsUnavailableError as exc:
            errors.append(f"{node.name}: {exc}")

    if not samples:
        raise MetricsUnavailableError("Не удалось получить метрики с курьеров: " + "; ".join(errors))

    ram_used_kb = sum(sample.ram_used_kb for sample in samples)
    ram_total_kb = sum(sample.ram_total_kb for sample in samples)
    disk_used_kb = sum(sample.disk_used_kb for sample in samples)
    disk_total_kb = sum(sample.disk_total_kb for sample in samples)
    current = ServerMetrics(
        cpu=round(sum(sample.cpu for sample in samples) / len(samples), 1),
        cpu_cores=sum(sample.cpu_cores for sample in samples),
        load_1=round(sum(sample.load_1 for sample in samples), 2),
        load_5=round(sum(sample.load_5 for sample in samples), 2),
        load_15=round(sum(sample.load_15 for sample in samples), 2),
        tasks=sum(sample.tasks for sample in samples),
        uptime_seconds=min((sample.uptime_seconds for sample in samples if sample.uptime_seconds > 0), default=0),
        services=sum(sample.services for sample in samples),
        services_total=sum(sample.services_total for sample in samples),
        ram=round((ram_used_kb / ram_total_kb) * 100, 1) if ram_total_kb else round(sum(sample.ram for sample in samples) / len(samples), 1),
        ram_used_kb=ram_used_kb,
        ram_total_kb=ram_total_kb,
        disk=round((disk_used_kb / disk_total_kb) * 100, 1) if disk_total_kb else round(sum(sample.disk for sample in samples) / len(samples), 1),
        disk_used_kb=disk_used_kb,
        disk_total_kb=disk_total_kb,
    )
    history = _append_metrics_history(project.id, current)
    services_total = max(current.services_total, current.services)

    return {
        "updated_at": datetime.utcnow().isoformat(),
        "source": "ssh",
        "nodes_total": len(nodes),
        "nodes_online": len(samples),
        "online_node_ids": online_node_ids,
        "errors": errors,
        "containers": containers,
        "images": images,
        "metrics": [
            _metric(
                "cpu",
                "Нагрузка CPU",
                "%",
                current.cpu,
                100,
                history["cpu"],
                [
                    {"label": "Ядра", "value": str(current.cpu_cores)},
                    {"label": "Load avg", "value": f"{current.load_1:.2f} / {current.load_5:.2f} / {current.load_15:.2f}"},
                    {"label": "Uptime", "value": _format_duration(current.uptime_seconds)},
                ],
            ),
            _metric(
                "services",
                "Запущенные службы",
                "",
                current.services,
                max(8, services_total + 2),
                history["services"],
                [
                    {"label": "Запущено", "value": str(current.services)},
                    {"label": "Всего", "value": str(services_total)},
                    {"label": "Процессы", "value": str(current.tasks)},
                ],
                percent=round((current.services / services_total) * 100, 1) if services_total else 0,
            ),
            _metric(
                "ram",
                "Потребление RAM",
                "%",
                current.ram,
                100,
                history["ram"],
                [
                    {"label": "Использовано", "value": _format_kb(current.ram_used_kb)},
                    {"label": "Всего", "value": _format_kb(current.ram_total_kb)},
                    {"label": "Свободно", "value": _format_kb(max(current.ram_total_kb - current.ram_used_kb, 0))},
                ],
            ),
            _metric(
                "disk",
                "Потребление диска",
                "%",
                current.disk,
                100,
                history["disk"],
                [
                    {"label": "Использовано", "value": _format_kb(current.disk_used_kb)},
                    {"label": "Всего", "value": _format_kb(current.disk_total_kb)},
                    {"label": "Свободно", "value": _format_kb(max(current.disk_total_kb - current.disk_used_kb, 0))},
                ],
            ),
        ],
    }


def _sync_node_statuses(db: Session, project: Project, online_node_ids: set[int]) -> None:
    changed = False
    for node in project.nodes:
        status = "up" if node.id in online_node_ids else "down"
        if node.status != status:
            node.status = status
            changed = True
    if changed:
        db.commit()


def _containers_payload(node: Node, containers: list[DockerContainerInfo]) -> list[dict[str, str]]:
    return [
        {
            "id": container.id,
            "name": container.name,
            "image": container.image,
            "status": container.status,
            "state": container.state,
            "node_id": str(node.id),
            "node_name": node.name,
            "server_ip": node.server_ip,
        }
        for container in containers
    ]


def _images_payload(node: Node, images: list[DockerImageInfo]) -> list[dict[str, str]]:
    return [
        {
            "id": image.id,
            "repository": image.repository,
            "tag": image.tag,
            "size": image.size,
            "created_since": image.created_since,
            "node_id": str(node.id),
            "node_name": node.name,
            "server_ip": node.server_ip,
        }
        for image in images
    ]


def _append_metrics_history(project_id: int, metrics: ServerMetrics) -> dict[str, list[float]]:
    history = _METRICS_HISTORY.setdefault(
        project_id,
        {
            "cpu": [],
            "services": [],
            "ram": [],
            "disk": [],
        },
    )
    history["cpu"].append(metrics.cpu)
    history["services"].append(metrics.services)
    history["ram"].append(metrics.ram)
    history["disk"].append(metrics.disk)
    for values in history.values():
        del values[:-28]
    return history


def _format_kb(value: int) -> str:
    if value <= 0:
        return "0 MB"
    mb = value / 1024
    if mb < 1024:
        return f"{mb:.0f} MB"
    gb = mb / 1024
    if gb < 1024:
        return f"{gb:.1f} GB"
    return f"{gb / 1024:.1f} TB"


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "нет данных"
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days} д {hours} ч"
    if hours:
        return f"{hours} ч {minutes} мин"
    return f"{minutes} мин"


def _metric(
    key: str,
    title: str,
    unit: str,
    current: float,
    maximum: int,
    points: list[float],
    details: list[dict[str, str]] | None = None,
    *,
    percent: float | None = None,
) -> dict:
    chart_points = points if len(points) > 1 else points * 28
    fill = round(max(0, min(100, percent if percent is not None else (current / maximum) * 100 if maximum else 0)), 1)
    return {
        "key": key,
        "title": title,
        "unit": unit,
        "current": current,
        "max": maximum,
        "points": chart_points,
        "fill": fill,
        "details": details or [],
    }
