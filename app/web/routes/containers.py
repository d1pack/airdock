from fastapi import APIRouter, Depends, Request

from app.db.models import User
from app.services.docker_service import DockerService, DockerUnavailableError
from app.web.dependencies import get_current_user
from app.web.templates import templates


router = APIRouter()


@router.get("/")
async def index(request: Request, current_user: User = Depends(get_current_user)):
    containers = []
    error = None

    try:
        containers = DockerService().list_containers()
    except DockerUnavailableError as exc:
        error = str(exc)

    return templates.TemplateResponse(
        request,
        "pages/containers.html",
        {
            "active_page": "containers",
            "containers": containers,
            "error": error,
            "current_user": current_user,
        },
    )
