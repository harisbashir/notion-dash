import re
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def test_today_groups_unique_and_badge(web_client, store):
    day = datetime.now(ZoneInfo("America/Toronto")).date()
    store.todo_items[3] = replace(store.todo_items[3], due=day)
    text = web_client.get("/").text
    assert "3 things are waiting on you." in text  # Codex-owned due item not counted
    assert "<h2>Questions <span>1</span></h2>" in text
    assert "<h2>Due soon <span>1</span></h2>" in text
    assert "<h2>Sample project <span>1</span></h2>" in text
    assert "<h2>No project <span>1</span></h2>" in text
    assert text.count('id="todo-ai-a2"') == 1
    assert text.count('id="todo-ai-c1"') == 1
    assert 'id="questions-badge"' in text
    assert 'aria-label="1 question"' in text
    assert 'type="search"' not in text
    assert "1 new idea" in text


def test_today_disclosure_and_project_order(web_client, store):
    base = store.todo_items[0]
    store.todo_items = [replace(base, id=str(i), title=f"Task {i}") for i in range(5)]
    store.todo_items += [replace(base, id="none", project_ids=[])]
    text = web_client.get("/").text
    assert "<h2>Sample project <span>5</span></h2>" in text
    assert "<summary>Show 2 more</summary>" in text
    before, after = text.split("<summary>Show 2 more</summary>")
    assert before.count('class="check"') == 3
    assert after.count('class="check"') == 3
    assert text.index("<h2>Sample project") < text.index("<h2>No project")


def test_today_due_boundary_and_empty(web_client, store):
    day = datetime.now(ZoneInfo("America/Toronto")).date()
    base = store.todo_items[3]
    store.todo_items = [
        replace(base, id=str(i), due=day + timedelta(days=i)) for i in (7, 8)
    ]
    text = web_client.get("/").text
    assert 'id="todo-ai-7"' in text and 'id="todo-ai-8"' not in text
    store.todo_items = []
    text = web_client.get("/").text
    assert "Nothing is waiting on you." in text
    assert "<h2>" not in text and "new idea" not in text


def test_trimmed_meta(web_client, store):
    day = datetime.now(ZoneInfo("America/Toronto")).date()
    store.todo_items[0] = replace(
        store.todo_items[0], due=day, who="Claude", status="Waiting"
    )
    text = web_client.get("/todos/ai/a1").text
    meta = re.search(r'<div class="meta">(.*?)</div>', text, re.S)[1]
    assert meta.count("<span") == 2
    assert "Sample project" in meta and "Due today" in meta
    assert "Claude" not in meta and "Waiting" not in meta
    assert "AI to-do" not in text and "To do" not in text
    assert "Open in Notion" not in text
    assert "High priority</span>" in text
    assert text.index('class="check"') < text.index('class="row-main"')
    store.todo_items[0] = replace(
        store.todo_items[0], due=None, project_ids=[], who="Haris"
    )
    text = web_client.get("/todos/ai/a1").text
    assert "Haris" not in re.search(r'<div class="meta">(.*?)</div>', text, re.S)[1]
    assert "Open in Notion" in web_client.get("/todos/ai/a1/edit").text


def test_chips_and_search(web_client):
    text = web_client.get("/todos?who=Codex").text
    assert re.search(r'<a[^>]+aria-current="page"[^>]*>Codex</a>', text)
    assert "Apply filter" not in text and "Search to-dos" in text
    assert "data-auto-submit" in text
    assert text.index('id="todo-ai-c1"') < text.index("Add a task</summary>")
    for path in ("/ideas", "/projects", "/projects/p1"):
        text = web_client.get(path).text
        assert 'type="search"' not in text
        assert "Apply filter" not in text
    text = web_client.get("/notes").text
    assert ">Mine</a>" in text and ">AI</a>" in text
    assert "Search notes" in text and "New note</a>" in text


def test_done_and_idea_chips_filter(web_client, store):
    text = web_client.get("/todos?done=1").text
    assert "Finished task" in text and "Personal task" not in text
    store.idea_items.append(
        replace(store.idea_items[0], id="planned", title="Plan this", status="Planned")
    )
    text = web_client.get("/ideas?status=Planned").text
    assert "Plan this" in text and "Fresh idea" not in text
    assert 'aria-current="page">Planned</a>' in text


def test_project_controls_and_context_meta(web_client):
    text = web_client.get("/projects/p1").text
    assert 'hx-trigger="change target:select, submit"' in text
    assert "<summary>Edit</summary>" in text
    meta = re.search(r'id="todo-ai-a1".*?<div class="meta">(.*?)</div>', text, re.S)[1]
    assert "Sample project" not in meta
    text = web_client.get("/projects").text
    assert "Open in Notion" not in text
    assert "<svg" in text and 'stroke-width="1.75"' in text


def test_badge_across_screens_and_after_completion(web_client, hx):
    for path in ("/todos", "/ideas", "/notes", "/projects", "/projects/p1"):
        text = web_client.get(path).text
        assert re.search(r'id="questions-badge"[^>]+aria-label="1 question"', text)
    web_client.post("/todos/ai/a2/done", headers=hx)
    text = web_client.get("/todos", headers=hx).text
    assert re.search(
        r'id="questions-badge"[^>]+hx-swap-oob="outerHTML"[^>]+hidden', text
    )
    assert 'aria-label="0 questions"' in text


def test_meta_priority_and_project_context_round_trip(web_client, store, hx):
    store.todo_items[0] = replace(
        store.todo_items[0], project_ids=[], who="Claude", status="In progress"
    )
    text = web_client.get("/todos/ai/a1").text
    meta = re.search(r'<div class="meta">(.*?)</div>', text, re.S)[1]
    assert "owner-claude" in meta and "Claude" in meta and "In progress" in meta
    store.todo_items[0] = replace(store.todo_items[0], project_ids=["p1"])
    text = web_client.get("/todos/ai/a1/edit?project_page=p1").text
    assert 'hx-post="/todos/ai/a1?project_page=p1"' in text
    text = web_client.post(
        "/todos/ai/a1?project_page=p1", headers=hx, data={"status": "Waiting"}
    ).text
    meta = re.search(r'<div class="meta">(.*?)</div>', text, re.S)[1]
    assert "Sample project" not in meta and "Waiting" in meta and "Claude" in meta


def test_subproject_counts_match_visible_rows(web_client, store):
    store.project_items.append(
        replace(store.project_items[0], id="child", parent_id="p1")
    )
    text = web_client.get("/projects").text
    assert "<h2>Active <span>2</span></h2>" in text


def test_today_project_sizes_and_multi_project_dedup(web_client, store):
    base = store.todo_items[0]
    store.project_items.append(
        replace(store.project_items[0], id="p2", name="Larger project")
    )
    store.todo_items = [
        replace(base, id="multi", project_ids=["p1", "p2"]),
        replace(base, id="larger1", project_ids=["p2"]),
        replace(base, id="larger2", project_ids=["p2"]),
        replace(base, id="none", project_ids=[]),
    ]
    text = web_client.get("/").text
    assert (
        text.index("<h2>Larger project")
        < text.index("<h2>Sample project")
        < text.index("<h2>No project")
    )
    assert text.count('id="todo-ai-multi"') == 1


def test_project_autosave_only_listens_to_its_own_selects(web_client):
    text = web_client.get("/projects/p1").text
    assert 'hx-trigger="change target:select, submit"' in text


def test_today_three_rows_need_no_disclosure(web_client, store):
    base = store.todo_items[0]
    store.todo_items = [replace(base, id=str(i)) for i in range(3)]
    text = web_client.get("/").text
    assert "<summary>Show" not in text
    store.todo_items.append(replace(base, id="four"))
    text = web_client.get("/").text
    assert "<summary>Show 1 more</summary>" in text


def test_questions_badge_only_counts_open_questions_for_you(web_client, store):
    base = store.todo_items[1]
    store.todo_items += [
        replace(base, id="second-question"),
        replace(base, id="agent-question", who="Claude"),
        replace(base, id="done-question", status="Done"),
        replace(base, id="personal-question", source="mine"),
    ]
    text = web_client.get("/notes").text
    assert 'aria-label="2 questions">2</span>' in text
    text = web_client.get("/").text
    assert "<h2>Questions <span>2</span></h2>" in text


def test_note_rows_have_only_type_and_project(web_client, store):
    from datetime import date

    store.note_items[0] = replace(store.note_items[0], date=date(2026, 1, 1))
    text = web_client.get("/notes").text
    meta = re.search(r'<span class="meta">(.*?)</span></span>', text, re.S)[1]
    assert meta.count("<span") == 2
    assert "General" in meta and "Sample project" in meta
    assert "2026-01-01" not in text and "Open in Notion" not in text


def test_project_autosave_disables_controls_during_save(web_client):
    text = web_client.get("/projects/p1").text
    form = re.search(r'<form id="project-fields"[^>]*>', text)[0]
    assert (
        'hx-disabled-elt="#project-fields select, #project-fields textarea, '
        '#project-fields button"' in form
    )
