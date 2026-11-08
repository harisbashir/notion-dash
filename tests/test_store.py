import json
from datetime import datetime
from pathlib import Path

import httpx
import pytest
from conftest import client_event_loop
from fastapi.testclient import TestClient

from app.main import create_app
from app.notion.client import NotionClient, NotionError, NotionUnavailable
from app.store import Store

BASE = "https://api.notion.com/v1"


def page(name):
    return json.loads((Path(__file__).parent / "fixtures" / f"{name}.json").read_text())


def response(items):
    return httpx.Response(200, json={"results": items, "has_more": False})


@pytest.fixture
def clock():
    class Clock:
        now = 0.0

        def __call__(self):
            return self.now

    return Clock()


@pytest.fixture
def store(settings, clock):
    async def sleep(_):
        pass

    return Store(NotionClient("fake-token", sleep=sleep), settings, clock=clock)


async def test_cache_hit_within_ttl(respx_mock, store):
    route = respx_mock.post(f"{BASE}/data_sources/fake-projects/query").mock(
        return_value=response([page("project")])
    )
    assert (await store.projects()).items[0].name == "Example project"
    assert (await store.projects()).items[0].name == "Example project"
    assert route.call_count == 1


async def test_cache_expires(respx_mock, store, clock):
    changed = page("project")
    changed["properties"]["Project"]["title"][0]["plain_text"] = "Updated project"
    route = respx_mock.post(f"{BASE}/data_sources/fake-projects/query").mock(
        side_effect=[response([page("project")]), response([changed])]
    )
    await store.projects()
    clock.now = 30
    assert (await store.projects()).items[0].name == "Updated project"
    assert route.call_count == 2


async def test_stale_fallback(respx_mock, store, clock):
    route = respx_mock.post(f"{BASE}/data_sources/fake-projects/query").mock(
        return_value=response([page("project")])
    )
    original = await store.projects()
    route.respond(502)
    clock.now = 31
    stale = await store.projects()
    assert stale.items == original.items
    assert isinstance(stale.stale_since, datetime)
    assert stale.stale_since.tzinfo is not None
    clock.now = 60
    assert (await store.projects()).stale_since == stale.stale_since


async def test_no_cache_raises(respx_mock, store):
    respx_mock.post(f"{BASE}/data_sources/fake-projects/query").respond(502)
    with pytest.raises(NotionUnavailable):
        await store.projects()


def todo_routes(respx_mock):
    ai = respx_mock.post(f"{BASE}/data_sources/fake-ai-todos/query").mock(
        return_value=response([page("ai_todo")])
    )
    mine = respx_mock.post(f"{BASE}/data_sources/fake-my-tasks/query").mock(
        return_value=response([page("my_task")])
    )
    return ai, mine


async def test_update_sends_only_changed(respx_mock, store):
    updated = page("ai_todo")
    updated["properties"]["Status"]["status"]["name"] = "Done"
    route = respx_mock.patch(f"{BASE}/pages/fake-ai-todo").respond(200, json=updated)
    result = await store.update_todo("ai", "fake-ai-todo", {"status": "Done"})
    assert result.status == "Done"
    assert json.loads(route.calls[0].request.content) == {
        "properties": {"Status": {"status": {"name": "Done"}}}
    }


async def test_update_refreshes_cache(respx_mock, store):
    ai, mine = todo_routes(respx_mock)
    await store.todos()
    updated = page("ai_todo")
    updated["properties"]["Priority"]["select"]["name"] = "Server priority"
    respx_mock.patch(f"{BASE}/pages/fake-ai-todo").respond(200, json=updated)
    result = await store.update_todo("ai", "fake-ai-todo", {"priority": "High"})
    assert result.priority == "Server priority"
    assert (await store.todos()).items[0].priority == "Server priority"
    assert ai.call_count == mine.call_count == 1


async def test_write_failure_keeps_cache(respx_mock, store):
    todo_routes(respx_mock)
    original = await store.todos()
    respx_mock.patch(f"{BASE}/pages/fake-ai-todo").respond(
        400, json={"code": "validation_error"}
    )
    with pytest.raises(NotionError):
        await store.update_todo("ai", "fake-ai-todo", {"status": "Done"})
    assert (await store.todos()).items == original.items


async def test_done_write_removes_open_row(respx_mock, store):
    todo_routes(respx_mock)
    await store.todos()
    updated = page("ai_todo")
    updated["properties"]["Status"]["status"]["name"] = "Done"
    respx_mock.patch(f"{BASE}/pages/fake-ai-todo").respond(200, json=updated)
    await store.update_todo("ai", "fake-ai-todo", {"status": "Done"})
    assert [todo.id for todo in (await store.todos()).items] == ["fake-my-task"]


async def test_create_idea_defaults(respx_mock, store, settings):
    settings.owner_name = "Example Owner"
    respx_mock.post(f"{BASE}/data_sources/fake-ideas/query").mock(
        return_value=response([])
    )
    await store.ideas()
    route = respx_mock.post(f"{BASE}/pages").respond(200, json=page("idea"))
    created = await store.create_idea(
        "Sample idea", "Try something new", "fake-project"
    )
    payload = json.loads(route.calls[0].request.content)
    assert payload == {
        "parent": {"type": "data_source_id", "data_source_id": "fake-ideas"},
        "properties": {
            "Idea": {"title": [{"type": "text", "text": {"content": "Sample idea"}}]},
            "Details": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Try something new"}}
                ]
            },
            "Project": {"relation": [{"id": "fake-project"}]},
            "Added by": {"select": {"name": "Example Owner"}},
            "Status": {"status": {"name": "New"}},
        },
    }
    assert created.title == "Sample idea"
    assert (await store.ideas()).items == [created]


async def test_open_filter_sent(respx_mock, store):
    ai, mine = todo_routes(respx_mock)
    assert len((await store.todos()).items) == 2
    for route in (ai, mine):
        assert json.loads(route.calls[0].request.content)["filter"] == {
            "property": "Status",
            "status": {"does_not_equal": "Done"},
        }


async def test_done_loaded_on_demand(respx_mock, store):
    calls = []

    def query(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if payload["filter"]["status"].get("equals") == "Done":
            done = page("ai_todo" if "ai-todos" in str(request.url) else "my_task")
            done["id"] = "fake-done-" + done["id"]
            done["properties"]["Status"]["status"]["name"] = "Done"
            return response([done])
        return response([])

    respx_mock.post(f"{BASE}/data_sources/fake-ai-todos/query").mock(side_effect=query)
    respx_mock.post(f"{BASE}/data_sources/fake-my-tasks/query").mock(side_effect=query)
    assert (await store.todos()).items == []
    assert len(calls) == 2
    assert len((await store.todos(include_done=True)).items) == 2
    assert len(calls) == 4
    for payload in calls[2:]:
        assert payload["sorts"] == [
            {"timestamp": "last_edited_time", "direction": "descending"}
        ]
        assert payload["filter"] == {"property": "Status", "status": {"equals": "Done"}}


async def test_options_are_loaded_from_schema(respx_mock, store):
    schema = page("data_source_schema")
    for ds in ["projects", "ai-todos", "my-tasks", "ideas", "ai-notes", "my-notes"]:
        respx_mock.get(f"{BASE}/data_sources/fake-{ds}").respond(200, json=schema)
    await store.load_options()
    assert store.options("ai_todos", "status") == ["New", "Custom status"]
    assert store.options("projects", "priority") == ["High", "Custom priority"]
    assert store.options("my_notes", "tags") == ["Example"]


def test_healthz_degraded(respx_mock, settings):
    for ds in ["projects", "ai-todos", "my-tasks", "ideas", "ai-notes", "my-notes"]:
        respx_mock.get(f"{BASE}/data_sources/fake-{ds}").respond(
            200, json={"properties": {}}
        )
    respx_mock.get(f"{BASE}/data_sources/fake-ideas").respond(
        404, json={"code": "object_not_found"}
    )
    with TestClient(
        create_app(settings), backend_options={"loop_factory": client_event_loop}
    ) as client:
        assert isinstance(client.app.state.store, Store)
        assert client.get("/healthz").json() == {
            "status": "degraded",
            "missing": ["ideas"],
        }


async def test_project_idea_and_note_updates(respx_mock, store):
    cases = [
        (
            "project",
            store.update_project,
            ["fake-project"],
            {"summary": "New"},
            "Summary",
            {"rich_text": [{"type": "text", "text": {"content": "New"}}]},
        ),
        (
            "idea",
            store.update_idea,
            ["fake-idea"],
            {"project_ids": []},
            "Project",
            {"relation": []},
        ),
        (
            "ai_note",
            store.update_note,
            ["ai", "fake-ai-note"],
            {"type": "Decision"},
            "Type",
            {"select": {"name": "Decision"}},
        ),
        (
            "my_note",
            store.update_note,
            ["mine", "fake-my-note"],
            {"tags": ["Work"]},
            "Tags",
            {"multi_select": [{"name": "Work"}]},
        ),
    ]
    for fixture, method, args, changes, name, value in cases:
        data = page(fixture)
        route = respx_mock.patch(f"{BASE}/pages/{data['id']}").respond(200, json=data)
        assert (await method(*args, changes)).id == data["id"]
        assert json.loads(route.calls[0].request.content) == {
            "properties": {name: value}
        }


async def test_notes_and_bodies(respx_mock, store):
    for ds, fixture in [("ai-notes", "ai_note"), ("my-notes", "my_note")]:
        respx_mock.post(f"{BASE}/data_sources/fake-{ds}/query").mock(
            return_value=response([page(fixture)])
        )
    assert (await store.notes("ai")).items[0].details == "Sample details"
    assert (await store.notes("mine")).items[0].tags == ["Example", "Work"]
    route = respx_mock.get(f"{BASE}/blocks/fake-my-note/children").mock(
        side_effect=[response([{"id": "first"}]), response([{"id": "second"}])]
    )
    assert await store.note_body("fake-my-note") == [{"id": "first"}]
    assert await store.note_body("fake-my-note") == [{"id": "second"}]
    assert route.call_count == 2


async def test_create_task_and_note_and_append(respx_mock, store):
    task = respx_mock.post(f"{BASE}/pages").respond(200, json=page("my_task"))
    assert (await store.create_my_task("Write sample", "fake-project")).source == "mine"
    assert json.loads(task.calls[0].request.content)["properties"]["Project"] == {
        "relation": [{"id": "fake-project"}]
    }
    task.respond(200, json=page("my_note"))
    note = await store.create_my_note("Sample note", "Note", None, "first\n\nsecond")
    payload = json.loads(task.calls[-1].request.content)
    assert payload["parent"]["data_source_id"] == "fake-my-notes"
    assert [
        b["paragraph"]["rich_text"][0]["text"]["content"] for b in payload["children"]
    ] == ["first", "second"]
    append = respx_mock.patch(f"{BASE}/blocks/fake-my-note/children").respond(
        200, json={}
    )
    await store.append_note(note.id, "x" * 4500)
    texts = json.loads(append.calls[0].request.content)["children"][0]["paragraph"][
        "rich_text"
    ]
    assert [len(t["text"]["content"]) for t in texts] == [2000, 2000, 500]


async def test_ideas_closed_filter(respx_mock, store):
    route = respx_mock.post(f"{BASE}/data_sources/fake-ideas/query").mock(
        return_value=response([])
    )
    await store.ideas()
    assert json.loads(route.calls[0].request.content)["filter"] == {
        "and": [
            {"property": "Status", "status": {"does_not_equal": "Done"}},
            {"property": "Status", "status": {"does_not_equal": "Dropped"}},
        ]
    }
    await store.ideas(include_closed=True)
    assert json.loads(route.calls[1].request.content)["filter"] == {
        "or": [
            {"property": "Status", "status": {"equals": "Done"}},
            {"property": "Status", "status": {"equals": "Dropped"}},
        ]
    }


@pytest.mark.parametrize("status", [403, 404])
async def test_cached_read_falls_back_on_notion_error(respx_mock, store, clock, status):
    route = respx_mock.post(f"{BASE}/data_sources/fake-projects/query").mock(
        return_value=response([page("project")])
    )
    original = await store.projects()
    clock.now = 31
    route.respond(status, json={"code": "object_not_found"})
    stale = await store.projects()
    assert stale.items == original.items
    assert stale.stale_since is not None
    clock.now = 60
    assert (await store.projects()).stale_since == stale.stale_since


async def test_refresh_cannot_overwrite_successful_write(respx_mock, store, clock):
    import asyncio

    query = respx_mock.post(f"{BASE}/data_sources/fake-projects/query").mock(
        return_value=response([page("project")])
    )
    await store.projects()
    clock.now = 31
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()

    async def delayed_query(request):
        refresh_started.set()
        await release_refresh.wait()
        return response([page("project")])

    query.mock(side_effect=delayed_query)
    updated = page("project")
    updated["properties"]["Summary"]["rich_text"][0]["plain_text"] = "User update"
    respx_mock.patch(f"{BASE}/pages/fake-project").respond(200, json=updated)
    refresh = asyncio.create_task(store.projects())
    await refresh_started.wait()
    write = asyncio.create_task(
        store.update_project("fake-project", {"summary": "User update"})
    )
    await asyncio.sleep(0)
    release_refresh.set()
    _, saved = await asyncio.gather(refresh, write)
    assert saved.summary == "User update"
    assert (await store.projects()).items[0].summary == "User update"


async def test_options_retried_after_startup_failure(respx_mock, store, clock):
    schema = page("data_source_schema")
    routes = {
        ds: respx_mock.get(f"{BASE}/data_sources/fake-{ds}")
        for ds in ["projects", "ai-todos", "my-tasks", "ideas", "ai-notes", "my-notes"]
    }
    for route in routes.values():
        route.respond(404, json={"code": "object_not_found"})
    await store.load_options()
    assert len(store.missing) == 6
    for route in routes.values():
        route.respond(200, json=schema)
    respx_mock.post(f"{BASE}/data_sources/fake-projects/query").respond(
        200, json={"results": [], "has_more": False}
    )
    await store.projects()
    assert len(store.missing) == 6  # too soon to retry
    clock.now = 61
    await store.projects()
    assert store.missing == []
    assert store.options("ai_todos", "status") == ["New", "Custom status"]


@pytest.fixture
def hq_store(settings, clock):
    async def sleep(_):
        pass

    hq = settings.model_copy(
        update={
            "ds_hq_projects": "fake-hq-projects",
            "ds_hq_tasks": "fake-hq-tasks",
            "ds_hq_notes": "fake-hq-notes",
        }
    )
    return Store(NotionClient("fake-token", sleep=sleep), hq, clock=clock)


def hq_project():
    data = page("project")
    data["id"] = "fake-hq-project"
    data["properties"]["Name"] = data["properties"].pop("Project")
    return data


async def test_hq_projects_and_tasks_merge(respx_mock, hq_store):
    respx_mock.post(f"{BASE}/data_sources/fake-projects/query").mock(
        return_value=response([page("project")])
    )
    respx_mock.post(f"{BASE}/data_sources/fake-hq-projects/query").mock(
        return_value=response([hq_project()])
    )
    projects = (await hq_store.projects()).items
    assert [(p.id, p.source, p.name) for p in projects] == [
        ("fake-project", "work", "Example project"),
        ("fake-hq-project", "home", "Example project"),
    ]
    for ds in ("ai-todos", "my-tasks"):
        respx_mock.post(f"{BASE}/data_sources/fake-{ds}/query").mock(
            return_value=response([])
        )
    respx_mock.post(f"{BASE}/data_sources/fake-hq-tasks/query").mock(
        return_value=response([page("my_task")])
    )
    todos = (await hq_store.todos()).items
    assert [t.source for t in todos] == ["home"]


async def test_hq_skipped_when_integration_lacks_access(respx_mock, hq_store):
    hq_store.missing = ["hq_projects", "hq_tasks", "hq_notes"]
    hq_store._options_tried = 0
    respx_mock.post(f"{BASE}/data_sources/fake-projects/query").mock(
        return_value=response([page("project")])
    )
    hq = respx_mock.post(f"{BASE}/data_sources/fake-hq-projects/query")
    assert len((await hq_store.projects()).items) == 1
    assert not hq.called
    created = respx_mock.post(f"{BASE}/pages").respond(200, json=page("my_task"))
    await hq_store.create_my_task("Sample", None)
    payload = json.loads(created.calls[0].request.content)
    assert payload["parent"]["data_source_id"] == "fake-my-tasks"


async def test_new_items_route_to_haris_hq(respx_mock, hq_store):
    respx_mock.post(f"{BASE}/data_sources/fake-projects/query").mock(
        return_value=response([page("project")])
    )
    respx_mock.post(f"{BASE}/data_sources/fake-hq-projects/query").mock(
        return_value=response([hq_project()])
    )
    created = respx_mock.post(f"{BASE}/pages").respond(200, json=page("my_task"))
    await hq_store.create_my_task("No project", None)
    await hq_store.create_my_task("Personal", "fake-hq-project")
    await hq_store.create_my_task("Work", "fake-project")
    parents = [
        json.loads(c.request.content)["parent"]["data_source_id"] for c in created.calls
    ]
    assert parents == ["fake-hq-tasks", "fake-hq-tasks", "fake-my-tasks"]
