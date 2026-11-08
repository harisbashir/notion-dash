from dataclasses import replace
from datetime import date

import pytest
from conftest import client_event_loop
from fastapi.testclient import TestClient

from app.blocks import text_to_blocks
from app.main import create_app
from app.notion.client import NotionError
from app.schema import Idea, Note, Project, Todo
from app.store import Result


class FakeStore:
    def __init__(self):
        self.project_items = [
            Project(
                "p1",
                "https://example.com/p1",
                "Sample project",
                "Active",
                "High",
                "Work",
                "A summary",
                None,
                None,
                None,
                None,
            )
        ]
        self.todo_items = [
            Todo(
                "a1",
                "https://example.com/a1",
                "ai",
                "Ordinary owner task",
                "To do",
                "High",
                None,
                "Original notes",
                ["p1"],
                "Haris",
                "Build",
                None,
                None,
            ),
            Todo(
                "a2",
                "https://example.com/a2",
                "ai",
                "Choose a provider",
                "To do",
                "Normal",
                date.today(),
                "",
                ["missing"],
                "Haris",
                "Question",
                None,
                None,
            ),
            Todo(
                "m1",
                "https://example.com/m1",
                "mine",
                "Personal task",
                "To do",
                None,
                None,
                "",
                [],
                None,
                None,
                None,
                None,
            ),
            Todo(
                "c1",
                "https://example.com/c1",
                "ai",
                "Agent task",
                "To do",
                None,
                None,
                "",
                [],
                "Codex",
                None,
                None,
                None,
            ),
            Todo(
                "d1",
                "https://example.com/d1",
                "mine",
                "Finished task",
                "Done",
                None,
                None,
                "",
                [],
                None,
                None,
                None,
                None,
            ),
        ]
        self.idea_items = [
            Idea(
                "i1",
                "https://example.com/i1",
                "Fresh idea",
                "New",
                "Idea details",
                ["p1"],
                "Haris",
                None,
            )
        ]
        self.note_items = [
            Note(
                "n1",
                "https://example.com/n1",
                "mine",
                "Working note",
                "General",
                None,
                ["p1"],
                [],
                None,
                None,
            ),
            Note(
                "n2",
                "https://example.com/n2",
                "ai",
                "Design decision",
                "Decision",
                "Decision details",
                ["p1"],
                [],
                None,
                None,
            ),
        ]
        self.bodies = {"n1": text_to_blocks("Body paragraph"), "n2": []}
        self.writes = []
        self.fail_write = False
        self.stale = None
        self.missing = []

    def options(self, ds_key, field):
        values = {
            "status": ["To do", "Doing", "Done"],
            "priority": ["High", "Normal", "Low", "Optional"],
            "type": ["General", "Decision", "Reference"],
            "who": ["Haris", "Claude", "Codex", "Client", "Accountant"],
            "area": ["Work", "Personal"],
        }
        if field == "status" and ds_key == "projects":
            return ["Active", "Before launch", "Not started", "On hold", "Live", "Done"]
        if field == "status" and ds_key == "ideas":
            return ["New", "Planned", "Maybe later", "Done", "Dropped"]
        return values.get(field, [])

    async def projects(self):
        return Result(list(self.project_items), self.stale)

    async def todos(self, include_done=False):
        return Result(
            [t for t in self.todo_items if include_done or t.status != "Done"],
            self.stale,
        )

    async def ideas(self, include_closed=False):
        return Result(
            [
                i
                for i in self.idea_items
                if include_closed or i.status not in {"Done", "Dropped"}
            ],
            self.stale,
        )

    async def notes(self, source):
        return Result([n for n in self.note_items if n.source == source], self.stale)

    async def note_body(self, page_id):
        return self.bodies.get(page_id, [])

    def update(self, collection, page_id, changes, source=None):
        self.writes.append((page_id, changes))
        if self.fail_write:
            raise NotionError("failed")
        index = next(
            i
            for i, item in enumerate(collection)
            if item.id == page_id and (source is None or item.source == source)
        )
        collection[index] = replace(collection[index], **changes)
        return collection[index]

    async def update_todo(self, source, page_id, changes):
        return self.update(self.todo_items, page_id, changes, source)

    async def create_my_task(self, title, project_id=None):
        if self.fail_write:
            raise NotionError("failed")
        item = replace(
            self.todo_items[2],
            id="new-task",
            title=title,
            project_ids=[project_id] if project_id else [],
        )
        self.todo_items.append(item)
        return item

    async def update_project(self, page_id, changes):
        return self.update(self.project_items, page_id, changes)

    async def update_idea(self, page_id, changes):
        return self.update(self.idea_items, page_id, changes)

    async def create_idea(self, title, details="", project_id=None):
        if self.fail_write:
            raise NotionError("failed")
        item = replace(
            self.idea_items[0],
            id="new-idea",
            title=title,
            details=details,
            project_ids=[project_id] if project_id else [],
        )
        self.idea_items.append(item)
        return item

    async def update_note(self, source, page_id, changes):
        return self.update(self.note_items, page_id, changes, source)

    async def create_my_note(self, title, type, project_id, body):
        if self.fail_write:
            raise NotionError("failed")
        item = replace(
            self.note_items[0],
            id="new-note",
            title=title,
            type=type,
            project_ids=[project_id] if project_id else [],
        )
        self.note_items.append(item)
        self.bodies[item.id] = text_to_blocks(body)
        return item

    async def append_note(self, page_id, text):
        if self.fail_write:
            raise NotionError("failed")
        self.bodies.setdefault(page_id, []).extend(text_to_blocks(text))


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def web_client(settings, store):
    app = create_app(settings)
    app.state.store = store
    # Avoid lifespan: every route uses the in-memory Store, never Notion.
    return TestClient(app, backend_options={"loop_factory": client_event_loop})


@pytest.fixture
def hx():
    return {"HX-Request": "true", "Origin": "http://testserver"}
