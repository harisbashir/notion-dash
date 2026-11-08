from dataclasses import replace
from datetime import UTC, datetime
from html import unescape


def test_toggle_done(web_client, store, hx):
    response = web_client.post("/todos/ai/a1/done", headers=hx)
    assert response.status_code == 200
    assert store.todo_items[0].status == "Done"
    assert 'aria-pressed="true"' in response.text
    web_client.post("/todos/ai/a1/done", headers=hx)
    assert store.todo_items[0].status == "To do"


def test_edit_sends_only_changed(web_client, store, hx):
    response = web_client.post(
        "/todos/ai/a1",
        headers=hx,
        data={
            "status": "Doing",
            "priority": "High",
            "due": "",
            "notes": "Original notes",
            "project": "p1",
        },
    )
    assert response.status_code == 200
    assert store.writes == [("a1", {"status": "Doing"})]
    assert "Doing" in response.text


def test_editor_uses_options(web_client, store, hx):
    response = web_client.get("/todos/ai/a1/edit", headers=hx)
    assert "<html" not in response.text
    assert "<label" in response.text
    assert '<option value="Optional"' in response.text
    assert "Original notes" in response.text
    assert "Cancel" in response.text


def test_write_error_keeps_value(web_client, store, hx):
    store.fail_write = True
    response = web_client.post("/todos/ai/a1/done", headers=hx)
    assert response.status_code == 200
    assert 'aria-pressed="false"' in response.text
    assert "Couldn't save to Notion. Your change wasn't saved." in unescape(
        response.text
    )
    assert "Try again" in response.text
    assert store.todo_items[0].status == "To do"


def test_todo_title_escaped(web_client, store):
    store.todo_items[0] = replace(
        store.todo_items[0], title="<script>alert(1)</script>"
    )
    response = web_client.get("/todos")
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_unknown_project_shown(web_client):
    assert "Unknown project" in web_client.get("/todos").text


def test_filters(web_client):
    text = web_client.get("/todos?who=Codex").text
    assert "Agent task" in text
    assert "Ordinary owner task" not in text
    text = web_client.get("/todos?project=p1&status=To+do").text
    assert "Ordinary owner task" in text
    assert "Personal task" not in text
    assert "Finished task" not in web_client.get("/todos").text
    assert "Finished task" in web_client.get("/todos?done=1").text


def test_stale_banner(web_client, store):
    store.stale = datetime(2026, 11, 8, 19, 5, tzinfo=UTC)
    assert (
        "Showing data from 14:05. Notion isn't responding."
        in web_client.get("/todos").text
    )


def test_create_task(web_client, store, hx):
    response = web_client.post(
        "/todos", data={"title": "New task", "project": "p1"}, headers=hx
    )
    assert response.status_code == 200
    assert "New task" in response.text
    assert store.todo_items[-1].source == "mine"
    assert store.todo_items[-1].project_ids == ["p1"]


def test_invalid_source_and_date(web_client, hx):
    assert web_client.get("/todos/nope/a1/edit").status_code == 422
    assert (
        web_client.post(
            "/todos/ai/a1", data={"due": "bad-date"}, headers=hx
        ).status_code
        == 422
    )


def test_no_change_does_not_write(web_client, store, hx):
    web_client.post("/todos/ai/a1", data={"notes": "Original notes"}, headers=hx)
    assert store.writes == []


def test_create_task_error_targets_original_form(web_client, store, hx):
    store.fail_write = True
    response = web_client.post("/todos", headers=hx, data={"title": "Keep task"})
    assert response.headers.get("HX-Retarget") == "#task-new"
    assert response.headers.get("HX-Reswap") == "outerHTML"
    assert 'value="Keep task"' in response.text


def test_editor_preserves_external_changes(web_client, store, hx):
    import json
    import re
    from html import unescape

    text = web_client.get("/todos/ai/a1/edit", headers=hx).text
    match = re.search(r'name="_original" value="([^"]+)"', text)
    assert match is not None
    original = json.loads(unescape(match[1]))
    store.todo_items[0] = replace(store.todo_items[0], notes="External notes")
    web_client.post(
        "/todos/ai/a1",
        headers=hx,
        data={
            "status": "Doing",
            "priority": "High",
            "due": "",
            "notes": "Original notes",
            "project": "p1",
            "_original": json.dumps(original),
        },
    )
    assert store.writes == [("a1", {"status": "Doing"})]
    assert store.todo_items[0].notes == "External notes"


def test_friendly_due_labels():
    from datetime import date

    from app.web import friendly_due

    today = date(2026, 11, 8)
    tz = None
    assert friendly_due(date(2026, 11, 8), today, tz) == "today"
    assert friendly_due(date(2026, 11, 9), today, tz) == "tomorrow"
    assert friendly_due(date(2026, 11, 7), today, tz) == "yesterday"
    assert friendly_due(date(2026, 11, 11), today, tz) == "Wednesday"
    assert friendly_due(date(2026, 12, 1), today, tz) == "1 Dec"
    assert friendly_due(date(2027, 1, 5), today, tz) == "5 Jan 2027"
