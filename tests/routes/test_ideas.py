from dataclasses import replace
from html import unescape


def test_ideas_status_chips(web_client, store):
    store.idea_items = [
        replace(store.idea_items[0], id=str(i), title=title, status=status)
        for i, (title, status) in enumerate(
            [
                ("Later idea", "Maybe later"),
                ("Planned idea", "Planned"),
                ("New idea", "New"),
                ("Closed idea", "Dropped"),
            ]
        )
    ]
    for status, title in [
        ("New", "New idea"),
        ("Planned", "Planned idea"),
        ("Maybe later", "Later idea"),
        ("Closed", "Closed idea"),
    ]:
        text = web_client.get("/ideas", params={"status": status}).text
        assert title in text
        for other in {"Later idea", "Planned idea", "New idea", "Closed idea"} - {
            title
        }:
            assert other not in text
    assert "Closed idea" in web_client.get("/ideas?closed=1").text


def test_create_idea(web_client, store, hx):
    response = web_client.post(
        "/ideas",
        headers=hx,
        data={"title": "New thought", "details": "Long details", "project": "p1"},
    )
    assert response.status_code == 200
    assert "New thought" in response.text
    assert store.idea_items[-1].title == "New thought"
    assert store.idea_items[-1].details == "Long details"
    assert store.idea_items[-1].project_ids == ["p1"]
    assert store.idea_items[-1].status == "New"


def test_idea_status_change(web_client, store, hx):
    response = web_client.post(
        "/ideas/i1", headers=hx, data={"status": "Planned", "project": "p1"}
    )
    assert response.status_code == 200
    assert "Planned" in response.text
    assert store.writes == [("i1", {"status": "Planned"})]


def test_idea_error_preserves_value(web_client, store, hx):
    store.fail_write = True
    response = web_client.post("/ideas/i1", headers=hx, data={"status": "Done"})
    assert response.status_code == 200
    assert store.idea_items[0].status == "New"
    assert 'value="New" selected' in response.text
    assert "Couldn't save to Notion." in unescape(response.text)


def test_create_idea_error_keeps_form(web_client, store, hx):
    store.fail_write = True
    response = web_client.post(
        "/ideas",
        headers=hx,
        data={"title": "<script>new</script>", "details": "Keep details"},
    )
    assert response.status_code == 200
    assert response.headers["HX-Retarget"] == "#idea-new"
    assert "Keep details" in response.text
    assert "&lt;script&gt;new&lt;/script&gt;" in response.text
    assert "Try again" in response.text


def test_idea_html_escaped(web_client, store):
    store.idea_items[0] = replace(
        store.idea_items[0], title="<script>title</script>", details="<b>details</b>"
    )
    text = web_client.get("/ideas").text
    assert "<script>title</script>" not in text
    assert "&lt;b&gt;details&lt;/b&gt;" in text


def test_idea_preserves_external_changes(web_client, store, hx):
    import re

    original = re.search(
        r'name="_original" value="([^"]+)"', web_client.get("/ideas").text
    )
    assert original is not None
    store.idea_items[0] = replace(store.idea_items[0], project_ids=["external"])
    web_client.post(
        "/ideas/i1",
        headers=hx,
        data={"status": "Planned", "project": "p1", "_original": unescape(original[1])},
    )
    assert store.writes == [("i1", {"status": "Planned"})]


def test_status_change_refreshes_groups(web_client, hx):
    response = web_client.post("/ideas/i1", headers=hx, data={"status": "Done"})
    assert response.headers.get("HX-Trigger-After-Swap") == "refreshDashboard"
    assert "Fresh idea" not in web_client.get("/ideas", headers=hx).text
