from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.db.init_db import init_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.task_manager import start_task_manager, stop_task_manager
from app.web.router import router as web_router


BASE_DIR = Path(__file__).resolve().parent


class ProxyHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Handle X-Forwarded-Proto for scheme
        forwarded_proto = request.headers.get('x-forwarded-proto')
        if forwarded_proto:
            request.scope['scheme'] = forwarded_proto

        # Handle X-Forwarded-Host for host
        forwarded_host = request.headers.get('x-forwarded-host')
        if forwarded_host:
            request.scope['server'] = (forwarded_host, request.scope['server'][1])

        response = await call_next(request)
        return response


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
    )

    # Add middleware to handle proxy headers (for GitHub Codespaces)
    application.add_middleware(ProxyHeadersMiddleware)

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
