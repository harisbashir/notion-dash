from dataclasses import replace
from html import unescape


def test_group_order(web_client, store):
    store.project_items = [
        replace(
            store.project_items[0], id=str(i), name="Project " + str(i), status=status
        )
        for i, status in enumerate(
            ["Done", "On hold", "Not started", "Live", "Before launch", "Active"]
        )
    ]
    text = web_client.get("/projects").text
    positions = [
        text.index("<h2>" + s + " <span>1</span></h2>")
        for s in ["Active", "Before launch", "Not started", "On hold"]
    ]
    assert positions == sorted(positions)
    assert "<details" in text and "<summary>Live <span>1</span></summary>" in text
    assert "<summary>Done <span>1</span></summary>" in text


def test_subprojects_indented_siblings(web_client, store):
    store.project_items.append(
        replace(
            store.project_items[0], id="child", name="Child project", parent_id="p1"
        )
    )
    text = web_client.get("/projects").text
    start = text.index('id="project-p1"')
    child = text.index('id="project-child"')
    assert child > start
    assert "</a>" in text[start:child]
    assert 'class="project-row subproject"' in text[start:child]
    assert 'style="--depth:1"' in text[child:]
    assert text.count('id="project-child"') == 1


def test_area_filter(web_client, store):
    store.project_items.append(
        replace(
            store.project_items[0], id="p2", name="Private project", area="Personal"
        )
    )
    text = web_client.get("/projects?area=Work").text
    assert "Sample project" in text
    assert "Private project" not in text


def test_open_todo_count(web_client, store):
    store.todo_items[-1] = replace(store.todo_items[-1], project_ids=["p1"])
    text = web_client.get("/projects").text
    assert '>1<span class="visually-hidden"> open</span>' in text


def test_project_page_sections(web_client):
    response = web_client.get("/projects/p1")
    assert response.status_code == 200
    for text in [
        "To-dos",
        "Ideas",
        "Decisions &amp; notes",
        "My notes",
        "Ordinary owner task",
        "Fresh idea",
        "Design decision",
        "Working note",
    ]:
        assert text in response.text
    assert "Personal task" not in response.text


def test_update_project_fields(web_client, store, hx):
    response = web_client.post(
        "/projects/p1",
        headers=hx,
        data={"status": "On hold", "priority": "High", "summary": "A summary"},
    )
    assert response.status_code == 200
    assert store.writes == [("p1", {"status": "On hold"})]
    assert "On hold" in response.text


def test_project_write_error_keeps_original(web_client, store, hx):
    store.fail_write = True
    response = web_client.post("/projects/p1", headers=hx, data={"summary": "Changed"})
    assert response.status_code == 200
    assert "A summary" in response.text
    assert "Changed" not in response.text
    assert "Couldn't save to Notion." in unescape(response.text)


def test_project_links_allowlist(web_client, store):
    store.project_items[0] = replace(
        store.project_items[0],
        code_url="javascript:alert(1)",
        live_url="https://example.com/live",
    )
    text = web_client.get("/projects/p1").text
    assert "javascript:" not in text
    assert "https://example.com/live" in text


def test_project_cycle_does_not_recurse_forever(web_client, store):
    store.project_items[0] = replace(store.project_items[0], parent_id="p1")
    assert web_client.get("/projects").text.count('id="project-p1"') == 1


def test_project_preserves_external_changes(web_client, store, hx):
    import re

    original = re.search(
        r'name="_original" value="([^"]+)"', web_client.get("/projects/p1").text
    )
    assert original is not None
    store.project_items[0] = replace(store.project_items[0], summary="External summary")
    web_client.post(
        "/projects/p1",
        headers=hx,
        data={
            "status": "On hold",
            "priority": "High",
            "summary": "A summary",
            "_original": unescape(original[1]),
        },
    )
    assert store.writes == [("p1", {"status": "On hold"})]


def test_empty_status_groups_hidden(web_client, store):
    text = web_client.get("/projects").text
    assert "<h2>On hold</h2>" not in text
    assert "<summary>Done" not in text
