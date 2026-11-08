from dataclasses import replace
from html import unescape


def test_notes_tabs(web_client):
    mine = web_client.get("/notes").text
    assert "Working note" in mine and "Design decision" not in mine
    ai = web_client.get("/notes?tab=ai").text
    assert "Design decision" in ai and "Working note" not in ai
    assert "Working note" not in web_client.get("/notes?type=Decision").text
    assert "Working note" not in web_client.get("/notes?project=missing").text


def test_note_body_rendered(web_client):
    text = web_client.get("/notes/mine/n1").text
    assert "<p>Body paragraph</p>" in text
    assert 'value="Reference"' in text
    text = web_client.get("/notes/ai/n2").text
    assert "Decision details" in text


def test_create_note_redirect(web_client, store, hx):
    response = web_client.post(
        "/notes",
        headers=hx,
        data={
            "title": "New note",
            "type": "Reference",
            "project": "p1",
            "body": "First line\nSecond line",
        },
    )
    assert response.headers["HX-Redirect"] == "/notes/mine/new-note"
    note = store.note_items[-1]
    assert (
        note.title == "New note"
        and note.type == "Reference"
        and note.project_ids == ["p1"]
    )
    body = web_client.get("/notes/mine/new-note").text
    assert "<p>First line</p><p>Second line</p>" in body


def test_append_note(web_client, hx):
    response = web_client.post(
        "/notes/n1/append", headers=hx, data={"text": "More text"}
    )
    assert response.status_code == 200
    assert "<p>Body paragraph</p><p>More text</p>" in response.text
    assert "<html" not in response.text


def test_note_type_change(web_client, store, hx):
    response = web_client.post(
        "/notes/mine/n1", headers=hx, data={"type": "Reference", "project": "p1"}
    )
    assert response.status_code == 200
    assert store.writes == [("n1", {"type": "Reference"})]
    assert 'value="Reference" selected' in response.text


def test_note_write_errors(web_client, store, hx):
    store.fail_write = True
    response = web_client.post("/notes/mine/n1", headers=hx, data={"type": "Reference"})
    assert 'value="General" selected' in response.text
    assert "Couldn't save to Notion." in unescape(response.text)
    response = web_client.post(
        "/notes/n1/append", headers=hx, data={"text": "Unsaved text"}
    )
    assert "<p>Unsaved text</p>" not in response.text
    assert "<p>Body paragraph</p>" in response.text
    assert "Unsaved text" in response.text
    assert "Couldn't save to Notion." in unescape(response.text)
    response = web_client.post(
        "/notes", headers=hx, data={"title": "Keep title", "body": "Keep body"}
    )
    assert "HX-Redirect" not in response.headers
    assert "Keep title" in response.text and "Keep body" in response.text
    assert "Try again" in response.text


def test_note_details_escaped_and_unsafe_link_removed(web_client, store):
    store.note_items[1] = replace(
        store.note_items[1],
        title="<script>title</script>",
        details="<script>details</script>",
        url="javascript:alert(1)",
    )
    text = web_client.get("/notes/ai/n2").text
    assert "&lt;script&gt;details&lt;/script&gt;" in text
    assert "<script>title</script>" not in text
    assert "javascript:" not in text


def test_new_note_form_labelled(web_client):
    response = web_client.get("/notes/new")
    assert response.status_code == 200
    assert "<label>Title" in response.text
    assert '<textarea name="body"' in response.text


def test_note_invalid_source_and_missing_id(web_client):
    assert web_client.get("/notes/nope/n1").status_code == 422
    assert web_client.get("/notes/mine/missing").status_code == 404


def test_note_preserves_external_changes(web_client, store, hx):
    import re

    original = re.search(
        r'name="_original" value="([^"]+)"', web_client.get("/notes/mine/n1").text
    )
    assert original is not None
    store.note_items[0] = replace(store.note_items[0], project_ids=["external"])
    web_client.post(
        "/notes/mine/n1",
        headers=hx,
        data={"type": "Reference", "project": "p1", "_original": unescape(original[1])},
    )
    assert store.writes == [("n1", {"type": "Reference"})]


def test_append_outage_preserves_text_and_original_body(web_client, store, hx):
    from app.notion.client import NotionUnavailable

    async def failing_append(page_id, text):
        async def failing_body(page_id):
            raise NotionUnavailable("offline")

        store.note_body = failing_body
        raise NotionUnavailable("offline")

    store.append_note = failing_append
    response = web_client.post(
        "/notes/n1/append", headers=hx, data={"text": "Keep this text"}
    )
    assert response.status_code == 200
    assert "<p>Body paragraph</p>" in response.text
    assert "Keep this text" in response.text
    assert "Couldn't save to Notion." in unescape(response.text)


def test_append_success_refresh_failure_does_not_invite_duplicate(
    web_client, store, hx
):
    from app.notion.client import NotionUnavailable

    original_append = store.append_note

    async def append_then_outage(page_id, text):
        await original_append(page_id, text)

        async def failing_body(page_id):
            raise NotionUnavailable("offline")

        store.note_body = failing_body

    store.append_note = append_then_outage
    response = web_client.post(
        "/notes/n1/append", headers=hx, data={"text": "Saved text"}
    )
    assert response.status_code == 200
    assert "<p>Saved text</p>" in response.text
    assert "<p>Body paragraph</p>" in response.text
    assert "wasn't saved" not in unescape(response.text)
    assert "Saved to Notion." in response.text
    assert '<textarea name="text" required></textarea>' in response.text


def test_append_full_outage_uses_rendered_body(web_client, store, hx):
    import re

    from app.notion.client import NotionUnavailable

    text = web_client.get("/notes/mine/n1").text
    snapshot = re.search(r'name="_body" value="([^"]+)"', text)
    assert snapshot is not None

    async def unavailable(page_id):
        raise NotionUnavailable("offline")

    store.note_body = unavailable
    store.fail_write = True
    response = web_client.post(
        "/notes/n1/append",
        headers=hx,
        data={"text": "Preserve me", "_body": unescape(snapshot[1])},
    )
    assert response.status_code == 200
    assert "<p>Body paragraph</p>" in response.text
    assert "Preserve me" in response.text
    assert "Couldn't save to Notion." in unescape(response.text)


def test_failed_new_note_stays_protected_from_polling(web_client, store, hx):
    store.fail_write = True
    text = web_client.post(
        "/notes", headers=hx, data={"title": "Keep note", "body": "Unsaved body"}
    ).text
    assert 'data-dirty="true"' in text
