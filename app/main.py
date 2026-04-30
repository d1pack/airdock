from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.db.init_db import init_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.task_manager import start_task_manager, stop_task_manager
from app.web.router import router as web_router


BASE_DIR = Path(__file__).resolve().parent


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )

    application.mount(
        "/static",
        StaticFiles(directory=BASE_DIR / "static"),
        name="static",
    )
    application.include_router(web_router)

    @application.on_event("startup")
    async def on_startup() -> None:
        init_db()
        application.state.metrics_scheduler = start_scheduler()
        application.state.task_manager = start_task_manager()

    @application.on_event("shutdown")
    async def on_shutdown() -> None:
        await stop_scheduler(getattr(application.state, "metrics_scheduler", None))
        await stop_task_manager()

    return application


app = create_app()
