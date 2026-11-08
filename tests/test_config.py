from pydantic import SecretStr

from app.config import Settings, get_settings


def test_settings_from_env(monkeypatch):
    values = {
        "NOTION_TOKEN": "fake-env-token",
        "DS_PROJECTS": "fake-projects",
        "DS_AI_TODOS": "fake-ai-todos",
        "DS_MY_TASKS": "fake-my-tasks",
        "DS_IDEAS": "fake-ideas",
        "DS_AI_NOTES": "fake-ai-notes",
        "DS_MY_NOTES": "fake-my-notes",
        "CACHE_TTL_SECONDS": "42",
        "TIMEZONE": "UTC",
        "OWNER_NAME": "Example Owner",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    settings = Settings()
    assert isinstance(settings.notion_token, SecretStr)
    assert settings.notion_token.get_secret_value() == values["NOTION_TOKEN"]
    assert values["NOTION_TOKEN"] not in repr(settings)
    for key, value in values.items():
        if key != "NOTION_TOKEN":
            assert str(getattr(settings, key.lower())) == value
    get_settings.cache_clear()
    assert get_settings() is get_settings()
    get_settings.cache_clear()


def test_healthz_ok(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
