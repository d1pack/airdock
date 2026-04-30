import asyncio
import json
import os
import threading
from contextlib import suppress
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import ActivityLog, AnsiblePlaybook, Node, Pipeline, PipelineProject, PipelineStep, Project, Task, User
from app.db.session import SessionLocal
from app.services.ansible_service import AnsibleRunCancelled, run_playbook
from app.services.server_metrics import MetricsUnavailableError, collect_node_containers, collect_node_metrics


TASK_MANAGER_STATE = {
    "active": False,
    "queued": 0,
    "running": 0,
    "workers": 0,
    "last_error": None,
}

_QUEUE: asyncio.Queue[int] | None = None
_WORKERS: list[asyncio.Task] = []
_SCHEDULE_LOOP: asyncio.Task | None = None
_LOOP: asyncio.AbstractEventLoop | None = None
_RUNNING_CANCEL_EVENTS: dict[int, threading.Event] = {}
_RUNNING_LOCK = threading.Lock()
_WORKER_COUNT = max(2, min(8, int(os.getenv("AIRDOCK_TASK_WORKERS", "4"))))


def start_task_manager() -> asyncio.Task:
    global _QUEUE, _SCHEDULE_LOOP, _LOOP
    _LOOP = asyncio.get_running_loop()
    if _QUEUE is None:
        _QUEUE = asyncio.Queue()
    if not any(not worker.done() for worker in _WORKERS):
        _WORKERS.clear()
        for index in range(_WORKER_COUNT):
            _WORKERS.append(asyncio.create_task(_worker_loop(index + 1), name=f"airdock-task-worker-{index + 1}"))
        asyncio.create_task(_restore_open_tasks(), name="airdock-task-restore")
    if _SCHEDULE_LOOP is None or _SCHEDULE_LOOP.done():
        _SCHEDULE_LOOP = asyncio.create_task(_scheduled_task_loop(), name="airdock-task-scheduler")
    TASK_MANAGER_STATE["workers"] = len(_WORKERS)
    return _WORKERS[0]


async def stop_task_manager() -> None:
    global _SCHEDULE_LOOP
    for event in list(_RUNNING_CANCEL_EVENTS.values()):
        event.set()
    for task in [_SCHEDULE_LOOP, *_WORKERS]:
        if task is None:
            continue
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    _WORKERS.clear()
    _SCHEDULE_LOOP = None
    TASK_MANAGER_STATE["active"] = False
    TASK_MANAGER_STATE["workers"] = 0
    TASK_MANAGER_STATE["running"] = 0


def get_task_manager_state() -> dict:
    state = dict(TASK_MANAGER_STATE)
    state["queued"] = _QUEUE.qsize() if _QUEUE else 0
    state["running"] = len(_RUNNING_CANCEL_EVENTS)
    state["workers"] = len([worker for worker in _WORKERS if not worker.done()])
    return state


async def enqueue_task_id(task_id: int) -> None:
    if _QUEUE is None:
        start_task_manager()
    await _QUEUE.put(task_id)
    TASK_MANAGER_STATE["queued"] = _QUEUE.qsize()


def stop_task_id(task_id: int) -> bool:
    with SessionLocal() as db:
        task = db.get(Task, task_id)
        if task is None:
            return False
        if task.status in {"success", "failed", "cancelled"}:
            return True
        with _RUNNING_LOCK:
            event = _RUNNING_CANCEL_EVENTS.get(task_id)
            if event is not None:
                event.set()
        if task.status in {"draft", "scheduled", "queued"}:
            task.status = "cancelled"
            task.error = "Задача остановлена пользователем до запуска."
            task.finished_at = datetime.utcnow()
            db.commit()
            return True
        if task.status in {"running", "cancel_requested"}:
            task.status = "cancel_requested"
            task.error = "Запрошена остановка задачи."
            db.commit()
            return True
    return False


def create_playbook_task(db, *, project: Project, playbook: AnsiblePlaybook, user: User) -> Task:
    task = Task(
        title=f"Запуск playbook {playbook.name}",
        task_type="playbook",
        status="queued",
        owner_id=user.id,
        owner_name=user.username,
        project_id=project.id,
        playbook_id=playbook.id,
        payload=json.dumps({"playbook_id": playbook.id, "project_id": project.id}, ensure_ascii=False),
        queued_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def create_pipeline_task(db, *, pipeline: Pipeline, user: User) -> Task:
    task = Task(
        title=f"Запуск пайплайна {pipeline.name}",
        task_type="pipeline",
        status="queued",
        owner_id=user.id,
        owner_name=user.username,
        project_id=pipeline.project_id,
        pipeline_id=pipeline.id,
        payload=json.dumps({"pipeline_id": pipeline.id}, ensure_ascii=False),
        queued_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def ensure_metrics_task(db, *, project: Project, node: Node | None = None) -> Task | None:
    if not project.nodes:
        return None
    query = select(Task).where(
        Task.task_type == "metrics",
        Task.project_id == project.id,
        Task.status.in_(("queued", "running")),
    )
    if node is not None:
        query = query.where(Task.node_id == node.id)
    existing = db.scalar(query.order_by(Task.created_at.desc()))
    if existing is not None:
        return existing

    title = f"Системный сбор метрик: {project.name}"
    if node is not None:
        title = f"Системный сбор метрик: {node.name}"
    task = Task(
        title=title,
        task_type="metrics",
        status="queued",
        owner_name="system",
        project_id=project.id,
        node_id=node.id if node else None,
        payload=json.dumps({"project_id": project.id, "node_id": node.id if node else None}, ensure_ascii=False),
        queued_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


async def _restore_open_tasks() -> None:
    await asyncio.sleep(0)
    with SessionLocal() as db:
        cancelled_tasks = db.scalars(select(Task).where(Task.status == "cancel_requested")).all()
        for task in cancelled_tasks:
            task.status = "cancelled"
            task.error = task.error or "Задача остановлена пользователем."
            task.finished_at = datetime.utcnow()
        tasks = db.scalars(select(Task).where(Task.status.in_(("queued", "running"))).order_by(Task.created_at)).all()
        db.commit()
        for task in tasks:
            task.status = "queued"
            task.queued_at = datetime.utcnow()
        db.commit()
        task_ids = [task.id for task in tasks]
    for task_id in task_ids:
        await enqueue_task_id(task_id)


async def _scheduled_task_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_enqueue_due_scheduled_tasks)
        except Exception as exc:
            TASK_MANAGER_STATE["last_error"] = str(exc)
        await asyncio.sleep(15)


def _enqueue_due_scheduled_tasks() -> None:
    now = datetime.utcnow()
    with SessionLocal() as db:
        tasks = db.scalars(
            select(Task)
            .where(Task.status == "scheduled", Task.scheduled_at.is_not(None), Task.scheduled_at <= now)
            .order_by(Task.scheduled_at)
            .limit(25)
        ).all()
        for task in tasks:
            task.status = "queued"
            task.queued_at = now
        db.commit()
        task_ids = [task.id for task in tasks]

    if _LOOP is not None and task_ids:
        for task_id in task_ids:
            asyncio.run_coroutine_threadsafe(enqueue_task_id(task_id), _LOOP)


async def _worker_loop(worker_number: int) -> None:
    assert _QUEUE is not None
    TASK_MANAGER_STATE["active"] = True
    while True:
        task_id = await _QUEUE.get()
        TASK_MANAGER_STATE["queued"] = _QUEUE.qsize()
        try:
            await asyncio.to_thread(_run_task, task_id, worker_number)
            TASK_MANAGER_STATE["last_error"] = None
        except Exception as exc:
            TASK_MANAGER_STATE["last_error"] = str(exc)
        finally:
            _QUEUE.task_done()


def _run_task(task_id: int, worker_number: int) -> None:
    cancel_event = threading.Event()
    with _RUNNING_LOCK:
        _RUNNING_CANCEL_EVENTS[task_id] = cancel_event
        TASK_MANAGER_STATE["running"] = len(_RUNNING_CANCEL_EVENTS)
    with SessionLocal() as db:
        try:
            task = db.get(Task, task_id)
            if task is None or task.status not in {"queued", "running"}:
                return
            if cancel_event.is_set():
                task.status = "cancelled"
                task.error = "Задача остановлена пользователем до запуска."
                task.finished_at = datetime.utcnow()
                db.commit()
                return
            task.status = "running"
            task.started_at = datetime.utcnow()
            task.error = ""
            task.payload = _payload_with(task.payload, {"worker": worker_number})
            db.commit()

            try:
                if cancel_event.is_set() or task.status == "cancel_requested":
                    raise AnsibleRunCancelled("Задача остановлена пользователем.")
                if task.task_type == "playbook":
                    _run_playbook_task(db, task, cancel_event)
                elif task.task_type == "pipeline":
                    _run_pipeline_task(db, task, cancel_event)
                elif task.task_type == "metrics":
                    _run_metrics_task(db, task, cancel_event)
                else:
                    raise RuntimeError(f"Unsupported task type: {task.task_type}")
                if task.status == "running":
                    task.status = "success"
            except AnsibleRunCancelled as exc:
                task.status = "cancelled"
                task.error = str(exc)
                _log(
                    db,
                    level="warning",
                    event_type="task.cancelled",
                    message=f"Задача {task.title}: остановлена.",
                    project_id=task.project_id,
                    node_id=task.node_id,
                    payload={"task_id": task.id, "task_type": task.task_type},
                )
            except Exception as exc:
                if task.status == "cancel_requested" or cancel_event.is_set():
                    task.status = "cancelled"
                    task.error = "Задача остановлена пользователем."
                else:
                    task.status = "failed"
                    task.error = str(exc)
                    _log(
                        db,
                        level="error",
                        event_type="task.failed",
                        message=f"Задача {task.title}: ошибка.",
                        project_id=task.project_id,
                        node_id=task.node_id,
                        payload={"task_id": task.id, "task_type": task.task_type, "error": str(exc)},
                    )
            finally:
                if task.status == "cancel_requested":
                    task.status = "cancelled"
                    task.error = task.error or "Задача остановлена пользователем."
                task.finished_at = datetime.utcnow()
                db.commit()
        finally:
            with _RUNNING_LOCK:
                _RUNNING_CANCEL_EVENTS.pop(task_id, None)
                TASK_MANAGER_STATE["running"] = len(_RUNNING_CANCEL_EVENTS)


def _run_playbook_task(db, task: Task, cancel_event: threading.Event) -> None:
    playbook = db.scalar(
        select(AnsiblePlaybook)
        .where(AnsiblePlaybook.id == task.playbook_id)
        .options(selectinload(AnsiblePlaybook.files), selectinload(AnsiblePlaybook.project).selectinload(Project.nodes))
    )
    if playbook is None:
        raise RuntimeError("Playbook не найден.")
    project = playbook.project
    try:
        result = run_playbook(playbook, project, list(project.nodes), should_stop=cancel_event.is_set)
    except AnsibleRunCancelled:
        playbook.last_status = "cancelled"
        playbook.last_output = "Запуск playbook остановлен пользователем."
        playbook.last_run_at = datetime.utcnow()
        raise
    except Exception as exc:
        playbook.last_status = "failed"
        playbook.last_output = str(exc)
        playbook.last_run_at = datetime.utcnow()
        _log(
            db,
            level="error",
            event_type="ansible.playbook.failed",
            message=f"Ansible playbook {playbook.name}: ошибка запуска.",
            project_id=project.id,
            payload={"task_id": task.id, "playbook_id": playbook.id, "playbook": playbook.name, "error": str(exc)},
        )
        raise
    playbook.last_status = result.status
    playbook.last_output = result.output
    playbook.last_run_at = datetime.utcnow()
    task.status = "success" if result.status == "success" else "failed"
    task.result = result.output
    task.node_id = result.node_id
    _log(
        db,
        level="info" if result.status == "success" else "error",
        event_type="ansible.playbook.run",
        message=f"Ansible playbook {playbook.name}: {result.status}.",
        project_id=project.id,
        node_id=result.node_id,
        payload={
            "task_id": task.id,
            "playbook_id": playbook.id,
            "playbook": playbook.name,
            "status": result.status,
            "return_code": result.return_code,
            "node_id": result.node_id,
            "node": result.node_name,
            "remote_path": result.remote_path,
        },
    )
    if result.status != "success":
        task.error = result.output[-4000:]


def _run_pipeline_task(db, task: Task, cancel_event: threading.Event) -> None:
    pipeline = db.scalar(
        select(Pipeline)
        .where(Pipeline.id == task.pipeline_id)
        .options(
            selectinload(Pipeline.project_links).selectinload(PipelineProject.project),
            selectinload(Pipeline.steps)
            .selectinload(PipelineStep.playbook)
            .selectinload(AnsiblePlaybook.files),
            selectinload(Pipeline.steps)
            .selectinload(PipelineStep.playbook)
            .selectinload(AnsiblePlaybook.project)
            .selectinload(Project.nodes),
        )
    )
    if pipeline is None:
        raise RuntimeError("Пайплайн не найден.")
    steps = sorted([step for step in pipeline.steps if step.playbook is not None], key=lambda step: step.position)
    if not steps:
        raise RuntimeError("В пайплайне нет playbook-ов для запуска.")

    output_parts: list[str] = []
    total = len(steps)
    task.status = "running"
    task.result = ""
    db.commit()
    for index, step in enumerate(steps, start=1):
        if cancel_event.is_set():
            raise AnsibleRunCancelled("Пайплайн остановлен пользователем.")
        playbook = step.playbook
        project = playbook.project
        if project is None:
            raise RuntimeError(f"У playbook {playbook.name} не найден проект.")

        header = f"\n===== Шаг {index}/{total}: {project.name} / {playbook.name} ====="
        output_parts.append(header)
        task.result = "\n".join(output_parts)[-20000:]
        db.commit()

        try:
            result = run_playbook(playbook, project, list(project.nodes), should_stop=cancel_event.is_set)
        except AnsibleRunCancelled:
            playbook.last_status = "cancelled"
            playbook.last_output = "Запуск playbook остановлен пользователем."
            playbook.last_run_at = datetime.utcnow()
            raise
        except Exception as exc:
            playbook.last_status = "failed"
            playbook.last_output = str(exc)
            playbook.last_run_at = datetime.utcnow()
            output_parts.append(str(exc))
            task.result = "\n".join(output_parts)[-20000:]
            _log(
                db,
                level="error",
                event_type="pipeline.playbook.failed",
                message=f"Пайплайн {pipeline.name}, playbook {playbook.name}: ошибка запуска.",
                project_id=project.id,
                payload={"task_id": task.id, "pipeline_id": pipeline.id, "playbook_id": playbook.id, "error": str(exc)},
            )
            raise

        playbook.last_status = result.status
        playbook.last_output = result.output
        playbook.last_run_at = datetime.utcnow()
        task.node_id = result.node_id
        output_parts.append(result.output or "")
        task.result = "\n".join(output_parts)[-20000:]
        _log(
            db,
            level="info" if result.status == "success" else "error",
            event_type="pipeline.playbook.run",
            message=f"Пайплайн {pipeline.name}, шаг {index}/{total}: {playbook.name} -> {result.status}.",
            project_id=project.id,
            node_id=result.node_id,
            payload={
                "task_id": task.id,
                "pipeline_id": pipeline.id,
                "playbook_id": playbook.id,
                "playbook": playbook.name,
                "status": result.status,
                "return_code": result.return_code,
                "node_id": result.node_id,
                "node": result.node_name,
                "remote_path": result.remote_path,
            },
        )
        db.commit()
        if result.status != "success":
            task.status = "failed"
            task.error = result.output[-4000:]
            raise RuntimeError(f"Шаг {index}/{total} завершился ошибкой: {playbook.name}")

    task.status = "success"
    task.result = "\n".join(output_parts)[-20000:]
    _log(
        db,
        level="info",
        event_type="pipeline.run",
        message=f"Пайплайн {pipeline.name}: все {total} шагов выполнены.",
        project_id=pipeline.project_id,
        payload={"task_id": task.id, "pipeline_id": pipeline.id, "steps": total},
    )


def _run_metrics_task(db, task: Task, cancel_event: threading.Event) -> None:
    project = db.scalar(select(Project).where(Project.id == task.project_id).options(selectinload(Project.nodes)))
    if project is None:
        raise RuntimeError("Проект не найден.")
    nodes = [node for node in project.nodes if task.node_id is None or node.id == task.node_id]
    if not nodes:
        raise RuntimeError("В проекте нет курьеров для сбора метрик.")

    online_nodes = 0
    containers_total = 0
    errors: list[str] = []
    for node in nodes:
        if cancel_event.is_set():
            raise AnsibleRunCancelled("Задача сбора метрик остановлена пользователем.")
        try:
            metrics = collect_node_metrics(node)
            node.status = "up"
            online_nodes += 1
            try:
                containers_total += len(collect_node_containers(node))
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
                    "task_id": task.id,
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
                payload={"task_id": task.id, "project": project.name, "node": node.name, "error": str(exc)},
            )

    task.result = json.dumps(
        {"nodes_total": len(nodes), "nodes_online": online_nodes, "containers_total": containers_total, "errors": errors},
        ensure_ascii=False,
    )
    _log(
        db,
        level="warning" if errors else "info",
        event_type="scheduler.project.poll",
        message=f"Проект {project.name}: онлайн {online_nodes}/{len(nodes)}, контейнеров {containers_total}.",
        project_id=project.id,
        payload={
            "task_id": task.id,
            "project": project.name,
            "nodes_total": len(nodes),
            "nodes_online": online_nodes,
            "containers_total": containers_total,
            "errors": errors,
        },
    )
    if errors and not online_nodes:
        raise RuntimeError("; ".join(errors))


def _log(db, *, level: str, event_type: str, message: str, project_id: int | None = None, node_id: int | None = None, payload: dict | None = None) -> None:
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


def _payload_with(raw_payload: str, updates: dict) -> str:
    try:
        payload = json.loads(raw_payload or "{}")
    except json.JSONDecodeError:
        payload = {}
    payload.update(updates)
    return json.dumps(payload, ensure_ascii=False)
