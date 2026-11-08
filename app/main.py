from fastapi import FastAPI

from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings if settings is not None else get_settings()

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    return app
