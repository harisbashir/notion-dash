from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import Settings, get_settings
from app.notion.client import NotionClient
from app.store import Store


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

    @app.get("/healthz")
    async def healthz():
        missing = app.state.store.missing
        return {"status": "degraded" if missing else "ok", "missing": missing}

    return app
