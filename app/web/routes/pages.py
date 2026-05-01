from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import ActivityLog, Node, Pipeline, Project, ProjectUser, Task, User
from app.db.session import get_db
from app.services.server_metrics import MetricsUnavailableError, ServerMetrics, collect_node_metrics
from app.web.dependencies import can_manage, get_current_user
from app.web.templates import templates


router = APIRouter()


@router.get("/")
async def dashboard():
    return RedirectResponse("/dashboard/analytics", status_code=303)


@router.get("/analytics")
async def analytics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    projects = _available_projects(db, current_user)
    nodes = _available_nodes(db, current_user, projects)
    project_ids = [project.id for project in projects]

    tasks_query = select(Task).order_by(Task.created_at.desc()).limit(6)
    if not can_manage(current_user):
        tasks_query = tasks_query.where(Task.project_id.in_(project_ids) if project_ids else Task.owner_id == current_user.id)
    latest_tasks = db.scalars(tasks_query).all()

    task_total_query = select(func.count(Task.id))
    task_running_query = select(func.count(Task.id)).where(Task.status == "running")
    task_failed_query = select(func.count(Task.id)).where(Task.status == "failed")
    if not can_manage(current_user):
        if project_ids:
            task_total_query = task_total_query.where(Task.project_id.in_(project_ids))
            task_running_query = task_running_query.where(Task.project_id.in_(project_ids))
            task_failed_query = task_failed_query.where(Task.project_id.in_(project_ids))
        else:
            task_total_query = task_total_query.where(Task.owner_id == current_user.id)
            task_running_query = task_running_query.where(Task.owner_id == current_user.id)
            task_failed_query = task_failed_query.where(Task.owner_id == current_user.id)

    return templates.TemplateResponse(
        request,
        "pages/analytics.html",
        {
            "active_page": "analytics",
            "current_user": current_user,
            "projects": projects,
            "nodes": nodes,
            "latest_tasks": latest_tasks,
            "stats": {
                "projects": len(projects),
                "nodes": len(nodes),
                "nodes_up": sum(1 for node in nodes if node.status == "up"),
                "tasks": db.scalar(task_total_query) or 0,
                "tasks_running": db.scalar(task_running_query) or 0,
                "tasks_failed": db.scalar(task_failed_query) or 0,
                "pipelines": _pipeline_count(db, project_ids, current_user),
                "events": db.scalar(select(func.count(ActivityLog.id))) or 0,
            },
        },
    )


@router.get("/analytics/metrics")
async def analytics_metrics(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    projects = _available_projects(db, current_user)
    nodes = _available_nodes(db, current_user, projects)
    payload = await run_in_threadpool(_collect_analytics_metrics, nodes)
    return JSONResponse(payload)


def _available_projects(db: Session, current_user: User) -> list[Project]:
    query = (
        select(Project)
        .options(selectinload(Project.nodes), selectinload(Project.users))
        .order_by(Project.created_at.desc())
    )
    if not can_manage(current_user):
        query = query.join(ProjectUser).where(ProjectUser.user_id == current_user.id)
    return db.execute(query).scalars().unique().all()


def _available_nodes(db: Session, current_user: User, projects: list[Project]) -> list[Node]:
    if can_manage(current_user):
        return db.scalars(select(Node).order_by(Node.name)).all()

    seen: set[int] = set()
    nodes: list[Node] = []
    for project in projects:
        for node in project.nodes:
            if node.id not in seen:
                nodes.append(node)
                seen.add(node.id)
    return sorted(nodes, key=lambda node: node.name.lower())


def _pipeline_count(db: Session, project_ids: list[int], current_user: User) -> int:
    query = select(func.count(Pipeline.id))
    if not can_manage(current_user):
        if not project_ids:
            return 0
        query = query.where(Pipeline.project_id.in_(project_ids))
    return db.scalar(query) or 0


def _collect_analytics_metrics(nodes: list[Node]) -> dict:
    samples: list[ServerMetrics] = []
    node_payload: list[dict] = []
    errors: list[str] = []

    for node in nodes:
        try:
            metrics = collect_node_metrics(node)
            samples.append(metrics)
            node_payload.append(
                {
                    "id": node.id,
                    "name": node.name,
                    "server_ip": node.server_ip,
                    "status": "up",
                    "cpu": metrics.cpu,
                    "ram": metrics.ram,
                    "disk": metrics.disk,
                    "services": metrics.services,
                    "uptime": _format_duration(metrics.uptime_seconds),
                }
            )
        except MetricsUnavailableError as exc:
            errors.append(f"{node.name}: {exc}")
            node_payload.append(
                {
                    "id": node.id,
                    "name": node.name,
                    "server_ip": node.server_ip,
                    "status": "down",
                    "cpu": 0,
                    "ram": 0,
                    "disk": 0,
                    "services": 0,
                    "uptime": "нет связи",
                }
            )

    return {
        "nodes_total": len(nodes),
        "nodes_online": len(samples),
        "errors": errors,
        "nodes": node_payload,
        "metrics": _aggregate_metrics(samples),
    }


def _aggregate_metrics(samples: list[ServerMetrics]) -> dict:
    if not samples:
        return {"cpu": 0, "ram": 0, "disk": 0, "services": 0, "tasks": 0}

    ram_used = sum(sample.ram_used_kb for sample in samples)
    ram_total = sum(sample.ram_total_kb for sample in samples)
    disk_used = sum(sample.disk_used_kb for sample in samples)
    disk_total = sum(sample.disk_total_kb for sample in samples)

    return {
        "cpu": round(sum(sample.cpu for sample in samples) / len(samples), 1),
        "ram": round((ram_used / ram_total) * 100, 1) if ram_total else round(sum(sample.ram for sample in samples) / len(samples), 1),
        "disk": round((disk_used / disk_total) * 100, 1) if disk_total else round(sum(sample.disk for sample in samples) / len(samples), 1),
        "services": sum(sample.services for sample in samples),
        "tasks": sum(sample.tasks for sample in samples),
    }


def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "нет данных"
    days, remainder = divmod(seconds, 86400)
    hours, _ = divmod(remainder, 3600)
    if days:
        return f"{days} д {hours} ч"
    return f"{hours} ч"
