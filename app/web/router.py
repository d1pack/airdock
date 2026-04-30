


from fastapi import APIRouter

from app.web.routes import admin, auth, containers, nodes, pages, pipelines, projects, tasks, users


router = APIRouter()
router.include_router(auth.router)
router.include_router(admin.router)
router.include_router(pages.router)
router.include_router(containers.router, prefix="/containers", tags=["containers"])
router.include_router(nodes.router, prefix="/runners", tags=["runners"])
router.include_router(projects.router, prefix="/projects", tags=["projects"])
router.include_router(pipelines.router, prefix="/pipelines", tags=["pipelines"])
router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
router.include_router(users.router, prefix="/users", tags=["users"])
