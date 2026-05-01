from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import AnsiblePlaybook, Pipeline, PipelineProject, PipelineStep, Project, ProjectUser, Task, User
from app.db.session import get_db
from app.services.task_manager import create_pipeline_task, enqueue_task_id
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
        select(Pipeline)
        .options(
            selectinload(Pipeline.project),
            selectinload(Pipeline.project_links).selectinload(PipelineProject.project),
            selectinload(Pipeline.steps).selectinload(PipelineStep.playbook),
        )
        .order_by(Pipeline.created_at.desc())
    )
    pipelines = db.scalars(query).unique().all()
    if not can_manage(current_user):
        pipelines = [pipeline for pipeline in pipelines if _can_view_pipeline(current_user, pipeline)]
    pipeline_tasks = _latest_pipeline_tasks(db, [pipeline.id for pipeline in pipelines])
    return templates.TemplateResponse(
        request,
        "pages/pipelines.html",
        {
            "active_page": "pipelines",
            "current_user": current_user,
            "pipelines": pipelines,
            "pipeline_tasks": pipeline_tasks,
            "error": request.query_params.get("error"),
        },
    )


@router.get("/new")
async def create_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    projects = _editable_projects(db, current_user)
    playbooks = _playbooks_for_projects(db, projects)
    selected_project_ids = _default_project_ids(projects, playbooks)
    return templates.TemplateResponse(
        request,
        "pages/pipeline_form.html",
        {
            "active_page": "pipelines",
            "current_user": current_user,
            "pipeline": None,
            "projects": projects,
            "playbooks": playbooks,
            "selected_project_ids": selected_project_ids,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/")
async def create_pipeline(
    name: str = Form(...),
    project_ids: list[int] = Form(...),
    description: str = Form(""),
    principles: str = Form(""),
    playbook_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    selected_projects = _validated_projects(db, current_user, project_ids)
    if not selected_projects:
        return RedirectResponse("/dashboard/pipelines/new?error=missing_project", status_code=303)

    pipeline = Pipeline(
        project_id=selected_projects[0].id,
        name=name.strip() or "Новый пайплайн",
        description=description.strip(),
        principles=principles.strip(),
    )
    db.add(pipeline)
    db.flush()
    _replace_projects(db, pipeline, selected_projects)
    _replace_steps(db, pipeline, playbook_ids, [project.id for project in selected_projects])
    db.commit()
    return RedirectResponse(f"/dashboard/pipelines/{pipeline.id}", status_code=303)


@router.get("/{pipeline_id}")
async def detail(
    pipeline_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pipeline = _get_pipeline(db, pipeline_id)
    if pipeline is None:
        return RedirectResponse("/dashboard/pipelines/?error=missing", status_code=303)
    if not _can_view_pipeline(current_user, pipeline):
        return RedirectResponse("/dashboard/pipelines/?error=forbidden", status_code=303)

    projects = _editable_projects(db, current_user)
    playbooks = _playbooks_for_projects(db, projects)
    latest_task = _latest_pipeline_task(db, pipeline.id)
    return templates.TemplateResponse(
        request,
        "pages/pipeline_form.html",
        {
            "active_page": "pipelines",
            "current_user": current_user,
            "pipeline": pipeline,
            "projects": projects,
            "playbooks": playbooks,
            "selected_project_ids": _pipeline_project_ids(pipeline),
            "latest_task": latest_task,
            "error": request.query_params.get("error"),
        },
    )


@router.post("/{pipeline_id}")
async def update_pipeline(
    pipeline_id: int,
    name: str = Form(...),
    project_ids: list[int] = Form(...),
    description: str = Form(""),
    principles: str = Form(""),
    playbook_ids: list[int] = Form(default=[]),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pipeline = _get_pipeline(db, pipeline_id)
    if pipeline is None:
        return RedirectResponse("/dashboard/pipelines/?error=missing", status_code=303)
    if not _can_edit_pipeline(current_user, pipeline):
        return RedirectResponse(f"/dashboard/pipelines/{pipeline_id}?error=forbidden", status_code=303)
    selected_projects = _validated_projects(db, current_user, project_ids)
    if not selected_projects:
        return RedirectResponse(f"/dashboard/pipelines/{pipeline_id}?error=missing_project", status_code=303)

    pipeline.project_id = selected_projects[0].id
    pipeline.name = name.strip() or pipeline.name
    pipeline.description = description.strip()
    pipeline.principles = principles.strip()
    _replace_projects(db, pipeline, selected_projects)
    _replace_steps(db, pipeline, playbook_ids, [project.id for project in selected_projects])
    db.commit()
    return RedirectResponse(f"/dashboard/pipelines/{pipeline.id}", status_code=303)


@router.post("/{pipeline_id}/run")
async def run_pipeline(
    pipeline_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pipeline = _get_pipeline(db, pipeline_id)
    if pipeline is None:
        return RedirectResponse("/dashboard/pipelines/?error=missing", status_code=303)
    if not _can_edit_pipeline(current_user, pipeline):
        return RedirectResponse(f"/dashboard/pipelines/{pipeline_id}?error=forbidden", status_code=303)
    if not pipeline.steps:
        return RedirectResponse(f"/dashboard/pipelines/{pipeline_id}?error=empty_pipeline", status_code=303)
    task = create_pipeline_task(db, pipeline=pipeline, user=current_user)
    await enqueue_task_id(task.id)
    return RedirectResponse(f"/dashboard/tasks/{task.id}", status_code=303)


def _get_pipeline(db: Session, pipeline_id: int) -> Pipeline | None:
    return db.scalar(
        select(Pipeline)
        .where(Pipeline.id == pipeline_id)
        .options(
            selectinload(Pipeline.project).selectinload(Project.users),
            selectinload(Pipeline.project_links).selectinload(PipelineProject.project).selectinload(Project.users),
            selectinload(Pipeline.steps).selectinload(PipelineStep.playbook).selectinload(AnsiblePlaybook.project),
        )
    )


def _latest_pipeline_tasks(db: Session, pipeline_ids: list[int]) -> dict[int, Task]:
    if not pipeline_ids:
        return {}
    tasks = db.scalars(
        select(Task)
        .where(Task.task_type == "pipeline", Task.pipeline_id.in_(pipeline_ids))
        .order_by(Task.created_at.desc())
        .limit(len(pipeline_ids) * 4)
    ).all()
    latest: dict[int, Task] = {}
    for task in tasks:
        if task.pipeline_id is not None and task.pipeline_id not in latest:
            latest[task.pipeline_id] = task
    return latest


def _latest_pipeline_task(db: Session, pipeline_id: int) -> Task | None:
    return db.scalar(
        select(Task)
        .where(Task.task_type == "pipeline", Task.pipeline_id == pipeline_id)
        .order_by(Task.created_at.desc())
        .limit(1)
    )


def _editable_projects(db: Session, user: User) -> list[Project]:
    query = select(Project).order_by(Project.name.asc())
    if not can_manage(user):
        query = query.where(Project.owner_id == user.id)
    return list(db.scalars(query).all())


def _playbooks_for_projects(db: Session, projects: list[Project]) -> list[AnsiblePlaybook]:
    project_ids = [project.id for project in projects]
    if not project_ids:
        return []
    return list(
        db.scalars(
            select(AnsiblePlaybook)
            .where(AnsiblePlaybook.project_id.in_(project_ids))
            .options(selectinload(AnsiblePlaybook.project))
            .order_by(AnsiblePlaybook.name.asc())
        ).all()
    )


def _default_project_ids(projects: list[Project], playbooks: list[AnsiblePlaybook]) -> list[int]:
    playbook_project_ids = {playbook.project_id for playbook in playbooks}
    for project in projects:
        if project.id in playbook_project_ids:
            return [project.id]
    return [projects[0].id] if projects else []


def _validated_projects(db: Session, user: User, project_ids: list[int]) -> list[Project]:
    clean_ids = list(dict.fromkeys(project_ids))
    if not clean_ids or len(clean_ids) > 5:
        return []
    projects = list(db.scalars(select(Project).where(Project.id.in_(clean_ids)).order_by(Project.name.asc())).all())
    projects_by_id = {project.id: project for project in projects}
    ordered_projects = [projects_by_id[project_id] for project_id in clean_ids if project_id in projects_by_id]
    if len(ordered_projects) != len(clean_ids):
        return []
    if any(not _can_edit_project(user, project) for project in ordered_projects):
        return []
    return ordered_projects


def _pipeline_projects(pipeline: Pipeline) -> list[Project]:
    linked_projects = [link.project for link in pipeline.project_links if link.project is not None]
    return linked_projects or ([pipeline.project] if pipeline.project else [])


def _pipeline_project_ids(pipeline: Pipeline) -> list[int]:
    return [project.id for project in _pipeline_projects(pipeline)]


def _replace_projects(db: Session, pipeline: Pipeline, projects: list[Project]) -> None:
    desired_ids = list(dict.fromkeys(project.id for project in projects[:5]))
    existing_links = {link.project_id: link for link in list(pipeline.project_links)}

    for project_id, link in existing_links.items():
        if project_id not in desired_ids:
            db.delete(link)

    for project_id in desired_ids:
        if project_id not in existing_links:
            db.add(PipelineProject(pipeline_id=pipeline.id, project_id=project_id))


def _replace_steps(db: Session, pipeline: Pipeline, playbook_ids: list[int], project_ids: list[int] | None = None) -> None:
    project_ids = project_ids or _pipeline_project_ids(pipeline)
    allowed_ids = set(
        db.scalars(select(AnsiblePlaybook.id).where(AnsiblePlaybook.project_id.in_(project_ids), AnsiblePlaybook.id.in_(playbook_ids))).all()
    )
    for step in list(pipeline.steps):
        db.delete(step)
    position = 1
    for playbook_id in playbook_ids:
        if playbook_id not in allowed_ids:
            continue
        db.add(PipelineStep(pipeline_id=pipeline.id, playbook_id=playbook_id, position=position))
        position += 1


def _can_edit_project(user: User, project: Project) -> bool:
    return can_manage(user) or project.owner_id == user.id


def _can_view_project(user: User, project: Project) -> bool:
    if _can_edit_project(user, project):
        return True
    return any(access.user_id == user.id for access in project.users)


def _can_edit_pipeline(user: User, pipeline: Pipeline) -> bool:
    return all(_can_edit_project(user, project) for project in _pipeline_projects(pipeline))


def _can_view_pipeline(user: User, pipeline: Pipeline) -> bool:
    return all(_can_view_project(user, project) for project in _pipeline_projects(pipeline))
