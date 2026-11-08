from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.guard import RequestGuard
from app.notion.client import NotionClient, NotionUnavailable
from app.routes import projects, today, todos
from app.store import Store
from app.web import ROOT, render


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(app):
        client = NotionClient(settings.notion_token.get_secret_value())
        try:
            app.state.store = Store(client, settings)
            await app.state.store.load_options()
            yield
        finally:
            await client.aclose()

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings
    app.include_router(projects.router)
    app.include_router(today.router)
    app.include_router(todos.router)
    app.add_middleware(RequestGuard)
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/sw.js")
    async def service_worker():
        return FileResponse(ROOT / "static" / "sw.js", media_type="text/javascript")

    @app.exception_handler(NotionUnavailable)
    async def unavailable(request: Request, exc: NotionUnavailable):
        return render(request, "error.html", status_code=503)

    @app.get("/healthz")
    async def healthz():
        missing = app.state.store.missing
        return {"status": "degraded" if missing else "ok", "missing": missing}

    return app
