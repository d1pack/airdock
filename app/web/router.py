


from fastapi import APIRouter

from app.web.routes import admin, auth, containers, landing, nodes, pages, pipelines, projects, tasks, users


router = APIRouter()
router.include_router(landing.router)
router.include_router(auth.router, prefix="/dashboard")
router.include_router(admin.router, prefix="/dashboard")
router.include_router(pages.router, prefix="/dashboard")
router.include_router(containers.router, prefix="/dashboard/containers", tags=["containers"])
router.include_router(nodes.router, prefix="/dashboard/runners", tags=["runners"])
router.include_router(projects.router, prefix="/dashboard/projects", tags=["projects"])
router.include_router(pipelines.router, prefix="/dashboard/pipelines", tags=["pipelines"])
router.include_router(tasks.router, prefix="/dashboard/tasks", tags=["tasks"])
router.include_router(users.router, prefix="/dashboard/users", tags=["users"])
