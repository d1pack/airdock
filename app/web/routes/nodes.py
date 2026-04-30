from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.core.security import encrypt_secret
from app.db.models import Node, ProjectNode, User
from app.db.session import get_db
from app.web.dependencies import can_manage, get_current_user
from app.web.templates import templates


router = APIRouter()


@router.get("/")
async def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    nodes = db.scalars(
        select(Node).options(selectinload(Node.project_links).selectinload(ProjectNode.project)).order_by(Node.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "pages/runners.html",
        {
            "active_page": "runners",
            "nodes": nodes,
            "current_user": current_user,
            "can_manage": can_manage(current_user),
            "error": request.query_params.get("error"),
        },
    )


@router.post("/")
async def create_node(
    name: str = Form(...),
    description: str = Form(""),
    icon: str = Form("truck"),
    status: str = Form("down"),
    server_ip: str = Form(...),
    server_user: str = Form(...),
    ssh_key: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_manage(current_user):
        return RedirectResponse("/runners/?error=forbidden", status_code=303)

    db.add(
        Node(
            name=name.strip(),
            description=description.strip(),
            icon=(icon.strip() or "truck")[:16],
            status=_normalize_status(status),
            server_ip=server_ip.strip(),
            server_user=server_user.strip(),
            ssh_key=encrypt_secret(ssh_key),
        )
    )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse("/runners/?error=duplicate", status_code=303)

    return RedirectResponse("/runners/", status_code=303)


@router.get("/{node_id}/settings")
async def settings(
    node_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    node = db.get(Node, node_id)
    if node is None:
        return RedirectResponse("/runners/?error=missing", status_code=303)

    return templates.TemplateResponse(
        request,
        "pages/runner_settings.html",
        {
            "active_page": "runners",
            "node": node,
            "current_user": current_user,
            "can_manage": can_manage(current_user),
        },
    )


@router.post("/{node_id}/settings")
async def update_node(
    node_id: int,
    name: str = Form(...),
    description: str = Form(""),
    icon: str = Form("truck"),
    status: str = Form("down"),
    server_ip: str = Form(...),
    server_user: str = Form(...),
    ssh_key: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_manage(current_user):
        return RedirectResponse("/runners/?error=forbidden", status_code=303)

    node = db.get(Node, node_id)
    if node is None:
        return RedirectResponse("/runners/?error=missing", status_code=303)

    node.name = name.strip()
    node.description = description.strip()
    node.icon = (icon.strip() or "truck")[:16]
    node.status = _normalize_status(status)
    node.server_ip = server_ip.strip()
    node.server_user = server_user.strip()
    if ssh_key.strip():
        node.ssh_key = encrypt_secret(ssh_key)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(f"/runners/{node_id}/settings?error=duplicate", status_code=303)

    return RedirectResponse("/runners/", status_code=303)


@router.post("/{node_id}/delete")
async def delete_node(
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_manage(current_user):
        return RedirectResponse("/runners/?error=forbidden", status_code=303)

    node = db.get(Node, node_id)
    if node is not None:
        db.delete(node)
        db.commit()

    return RedirectResponse("/runners/", status_code=303)


def _normalize_status(status: str) -> str:
    return "up" if status.strip().lower() == "up" else "down"
