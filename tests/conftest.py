import asyncio
import socket

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings():
    return Settings(
        notion_token="fake-token",
        ds_projects="fake-projects",
        ds_ai_todos="fake-ai-todos",
        ds_my_tasks="fake-my-tasks",
        ds_ideas="fake-ideas",
        ds_ai_notes="fake-ai-notes",
        ds_my_notes="fake-my-notes",
    )


@pytest.fixture
def client(settings, respx_mock):
    for ds in ("projects", "ai-todos", "my-tasks", "ideas", "ai-notes", "my-notes"):
        respx_mock.get(f"https://api.notion.com/v1/data_sources/fake-{ds}").respond(
            200, json={"properties": {}}
        )
    with TestClient(
        create_app(settings), backend_options={"loop_factory": client_event_loop}
    ) as client:
        yield client


def client_event_loop():
    """Keep TestClient usable where the sandbox blocks socketpair wakeups."""
    loop = asyncio.new_event_loop()
    reader, writer = socket.socketpair()
    try:
        writer.send(b"probe")
    except PermissionError:

        def tick():
            loop.call_later(0.01, tick)

        loop.call_soon(tick)
    finally:
        reader.close()
        writer.close()
    return loop
