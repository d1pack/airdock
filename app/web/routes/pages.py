from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import ActivityLog, Node, Pipeline, Project, ProjectUser, Task, User
from app.db.session import get_db
from app.services.server_metrics import MetricsUnavailableError, ServerMetrics, collect_node_metrics
from app.web.dependencies import can_manage, get_current_user
from app.web.templates import templates


router = APIRouter()
MEDIA_DIR = Path(__file__).resolve().parents[3] / "media"


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
    visible_task_types = ("pipeline", "playbook")

    tasks_query = select(Task).where(Task.task_type.in_(visible_task_types)).order_by(Task.created_at.desc()).limit(6)
    if not can_manage(current_user):
        tasks_query = tasks_query.where(Task.project_id.in_(project_ids) if project_ids else Task.owner_id == current_user.id)
    latest_tasks = db.scalars(tasks_query).all()

    task_total_query = select(func.count(Task.id)).where(Task.task_type.in_(visible_task_types))
    task_running_query = select(func.count(Task.id)).where(Task.task_type.in_(visible_task_types), Task.status == "running")
    task_failed_query = select(func.count(Task.id)).where(Task.task_type.in_(visible_task_types), Task.status == "failed")
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


@router.get("/files")
async def file_manager(request: Request, current_user: User = Depends(get_current_user)):
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return templates.TemplateResponse(
        request,
        "pages/file_manager.html",
        {
            "active_page": "files",
            "current_user": current_user,
        },
    )


@router.get("/files/media/list")
async def media_list(path: str = "", current_user: User = Depends(get_current_user)):
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    directory = _media_path(path, allow_root=True)
    if not directory.exists():
        directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Это не папка.")

    entries = []
    for item in sorted(directory.iterdir(), key=lambda child: (child.is_file(), child.name.lower())):
        if item.name == ".gitkeep":
            continue
        stat = item.stat()
        relative_path = _relative_media_path(item)
        entries.append(
            {
                "name": item.name,
                "path": relative_path,
                "type": "folder" if item.is_dir() else "file",
                "size": stat.st_size,
                "modified_at": stat.st_mtime,
                "download_url": f"/dashboard/files/media/download?path={quote(relative_path)}",
            }
        )
    return JSONResponse(
        {
            "root": str(MEDIA_DIR),
            "path": _normalize_media_relative(path),
            "entries": entries,
            "files": entries,
        }
    )


@router.post("/files/media/upload")
async def media_upload(
    path: str = Form(""),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    directory = _media_path(path, allow_root=True)
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise HTTPException(status_code=400, detail="Это не папка.")
    filename = _safe_media_name(file.filename or "upload.bin")
    destination = _unique_media_path(directory, filename)
    await run_in_threadpool(_save_upload, file, destination)
    return JSONResponse({"name": destination.name, "path": _relative_media_path(destination), "size": destination.stat().st_size})


@router.post("/files/media/folder")
async def media_create_folder(request: Request, current_user: User = Depends(get_current_user)):
    payload = await request.json()
    parent = _media_path(str(payload.get("path") or ""), allow_root=True)
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.is_dir():
        raise HTTPException(status_code=400, detail="Это не папка.")
    folder_name = _safe_media_name(str(payload.get("name") or "Новая папка"))
    folder = _unique_media_path(parent, folder_name)
    folder.mkdir()
    return JSONResponse({"name": folder.name, "path": _relative_media_path(folder)})


@router.get("/files/media/content")
async def media_content(path: str, current_user: User = Depends(get_current_user)):
    file_path = _media_path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден.")
    if file_path.stat().st_size > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Файл слишком большой для редактора.")
    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=415, detail="Файл не похож на UTF-8 текст.") from exc
    return JSONResponse({"path": _relative_media_path(file_path), "content": content})


@router.post("/files/media/content")
async def media_update_content(request: Request, current_user: User = Depends(get_current_user)):
    payload = await request.json()
    file_path = _media_path(str(payload.get("path") or ""))
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден.")
    content = str(payload.get("content") or "")
    if len(content.encode("utf-8")) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Содержимое слишком большое для редактора.")
    file_path.write_text(content, encoding="utf-8")
    return JSONResponse({"status": "saved", "path": _relative_media_path(file_path), "size": file_path.stat().st_size})


@router.get("/files/media/download")
async def media_download_by_path(path: str, current_user: User = Depends(get_current_user)):
    file_path = _media_path(path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден.")
    return FileResponse(file_path, filename=file_path.name)


@router.get("/files/media/download/{filename}")
async def media_download(filename: str, current_user: User = Depends(get_current_user)):
    path = _media_path(filename)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден.")
    return FileResponse(path, filename=path.name)


@router.post("/files/media/delete/{filename}")
async def media_delete(filename: str, current_user: User = Depends(get_current_user)):
    path = _media_path(filename)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Файл не найден.")
    path.unlink()
    return JSONResponse({"status": "deleted", "name": path.name})


@router.post("/files/media/delete")
async def media_delete_by_path(request: Request, current_user: User = Depends(get_current_user)):
    payload = await request.json()
    path = _media_path(str(payload.get("path") or ""))
    if not path.exists():
        raise HTTPException(status_code=404, detail="Объект не найден.")
    if path.is_dir():
        try:
            path.rmdir()
        except OSError as exc:
            raise HTTPException(status_code=409, detail="Папка не пуста.") from exc
        return JSONResponse({"status": "deleted", "name": path.name, "type": "folder"})
    path.unlink()
    return JSONResponse({"status": "deleted", "name": path.name, "type": "file"})


@router.post("/files/media/move")
async def media_move(request: Request, current_user: User = Depends(get_current_user)):
    payload = await request.json()
    source = _media_path(str(payload.get("source") or ""))
    target_dir = _media_path(str(payload.get("target_dir") or ""), allow_root=True)
    if not source.exists():
        raise HTTPException(status_code=404, detail="Объект не найден.")
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Папка назначения не найдена.")
    if source == target_dir or (source.is_dir() and target_dir in source.resolve().parents):
        raise HTTPException(status_code=400, detail="Нельзя переместить папку внутрь самой себя.")
    destination = _unique_media_path(target_dir, source.name)
    shutil.move(str(source), str(destination))
    return JSONResponse({"status": "moved", "path": _relative_media_path(destination)})


def _safe_media_name(filename: str) -> str:
    name = Path(filename).name.strip().replace("\\", "_").replace("/", "_")
    cleaned = "".join(char if char.isalnum() or char in " ._-()" else "_" for char in name).strip(" .")
    return cleaned or "upload.bin"


def _normalize_media_relative(value: str) -> str:
    raw = str(value or "").replace("\\", "/").strip("/")
    parts = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if part == "..":
            raise HTTPException(status_code=400, detail="Нельзя выйти за пределы media.")
        parts.append(_safe_media_name(part))
    return "/".join(parts)


def _media_path(relative_path: str, allow_root: bool = False) -> Path:
    normalized = _normalize_media_relative(relative_path)
    if not normalized and not allow_root:
        raise HTTPException(status_code=400, detail="Некорректный путь.")
    path = (MEDIA_DIR / normalized).resolve()
    media_root = MEDIA_DIR.resolve()
    if media_root not in path.parents and path != media_root:
        raise HTTPException(status_code=400, detail="Некорректный путь.")
    return path


def _relative_media_path(path: Path) -> str:
    return path.resolve().relative_to(MEDIA_DIR.resolve()).as_posix()


def _unique_media_path(directory: Path, filename: str) -> Path:
    path = (directory / _safe_media_name(filename)).resolve()
    media_root = MEDIA_DIR.resolve()
    if media_root not in path.parents:
        raise HTTPException(status_code=400, detail="Некорректный путь.")
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise HTTPException(status_code=409, detail="Не удалось подобрать имя файла.")


def _save_upload(file: UploadFile, destination: Path) -> None:
    with destination.open("wb") as target:
        shutil.copyfileobj(file.file, target)


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
