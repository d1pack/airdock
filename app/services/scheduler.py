import asyncio
import json
from contextlib import suppress
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import ActivityLog, Project
from app.db.session import SessionLocal
from app.services.server_metrics import MetricsUnavailableError, collect_node_containers, collect_node_metrics


SCHEDULER_INTERVAL_SECONDS = 300
SCHEDULER_STATE = {
    "active": False,
    "last_success_at": None,
    "last_error_at": None,
    "last_error": None,
    "last_started_at": None,
    "last_finished_at": None,
    "interval_seconds": SCHEDULER_INTERVAL_SECONDS,
}


def start_scheduler() -> asyncio.Task:
    return asyncio.create_task(_scheduler_loop(), name="airdock-metrics-scheduler")


async def stop_scheduler(task: asyncio.Task | None) -> None:
    if task is None:
        return
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def _scheduler_loop() -> None:
    await asyncio.sleep(5)
    while True:
        SCHEDULER_STATE["active"] = True
        SCHEDULER_STATE["last_started_at"] = datetime.utcnow().isoformat()
        try:
            await asyncio.to_thread(run_metrics_poll_once)
            SCHEDULER_STATE["last_success_at"] = datetime.utcnow().isoformat()
            SCHEDULER_STATE["last_error"] = None
        except Exception as exc:
            SCHEDULER_STATE["last_error_at"] = datetime.utcnow().isoformat()
            SCHEDULER_STATE["last_error"] = str(exc)
        finally:
            SCHEDULER_STATE["last_finished_at"] = datetime.utcnow().isoformat()
            SCHEDULER_STATE["active"] = SCHEDULER_STATE["last_error"] is None
        await asyncio.sleep(SCHEDULER_INTERVAL_SECONDS)


def get_scheduler_state() -> dict:
    return dict(SCHEDULER_STATE)


def run_metrics_poll_once() -> None:
    with SessionLocal() as db:
        projects = db.scalars(
            select(Project)
            .options(selectinload(Project.nodes))
            .order_by(Project.created_at.desc())
        ).all()

        for project in projects:
            if not project.nodes:
                _log(
                    db,
                    level="warning",
                    event_type="scheduler.project.empty",
                    message=f"Проект {project.name}: нет привязанных курьеров.",
                    project_id=project.id,
                    payload={"project": project.name},
                )
                continue

            online_nodes = 0
            containers_total = 0
            errors: list[str] = []

            for node in project.nodes:
                try:
                    metrics = collect_node_metrics(node)
                    node.status = "up"
                    online_nodes += 1

                    try:
                        containers = collect_node_containers(node)
                        containers_total += len(containers)
                    except MetricsUnavailableError as exc:
                        errors.append(f"{node.name}: {exc}")

                    _log(
                        db,
                        level="info",
                        event_type="scheduler.node.metrics",
                        message=f"Курьер {node.name}: метрики получены.",
                        project_id=project.id,
                        node_id=node.id,
                        payload={
                            "project": project.name,
                            "node": node.name,
                            "server_ip": node.server_ip,
                            "cpu": metrics.cpu,
                            "services": metrics.services,
                            "ram": metrics.ram,
                            "disk": metrics.disk,
                        },
                    )
                except MetricsUnavailableError as exc:
                    node.status = "down"
                    errors.append(f"{node.name}: {exc}")
                    _log(
                        db,
                        level="error",
                        event_type="scheduler.node.failed",
                        message=f"Курьер {node.name}: не удалось получить метрики.",
                        project_id=project.id,
                        node_id=node.id,
                        payload={
                            "project": project.name,
                            "node": node.name,
                            "server_ip": node.server_ip,
                            "error": str(exc),
                        },
                    )

            level = "warning" if errors else "info"
            _log(
                db,
                level=level,
                event_type="scheduler.project.poll",
                message=f"Проект {project.name}: онлайн {online_nodes}/{len(project.nodes)}, контейнеров {containers_total}.",
                project_id=project.id,
                payload={
                    "project": project.name,
                    "nodes_total": len(project.nodes),
                    "nodes_online": online_nodes,
                    "containers_total": containers_total,
                    "errors": errors,
                },
            )
        db.commit()


def _log(
    db,
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
