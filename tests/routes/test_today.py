from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def test_today_sections(web_client):
    text = web_client.get("/").text
    for heading in [
        "3 things are waiting on you.",
        "Waiting on you",
        "Your tasks",
        "Due soon",
        "New ideas",
    ]:
        assert heading in text
    assert "Ordinary owner task" in text
    assert "Personal task" in text
    assert "Agent task" not in text
    assert "Finished task" not in text


def test_question_first(web_client):
    text = web_client.get("/").text
    assert text.index("Choose a provider") < text.index("Ordinary owner task")


def test_due_in_configured_timezone(web_client, store):
    today = datetime.now(ZoneInfo("America/Toronto")).date()
    store.todo_items[3] = replace(store.todo_items[3], due=today - timedelta(days=1))
    text = web_client.get("/").text
    assert "Agent task" in text
    assert "overdue" in text


def test_today_zero_and_one(web_client, store):
    store.todo_items = [store.todo_items[2], store.todo_items[3]]
    assert "1 thing is waiting on you." in web_client.get("/").text
    store.todo_items = []
    assert "Nothing is waiting on you." in web_client.get("/").text


def test_today_row_ids_unique(web_client):
    import re

    ids = re.findall(r'\bid="([^"]+)"', web_client.get("/").text)
    assert len(ids) == len(set(ids))


def test_today_toggle_refreshes_other_occurrence_and_count(web_client, hx):
    text = web_client.get("/").text
    assert "refreshDashboard from:body" in text
    response = web_client.post("/todos/ai/a2/done?occurrence=due", headers=hx)
    assert response.headers.get("HX-Trigger-After-Swap") == "refreshDashboard"
    refreshed = web_client.get("/", headers=hx).text
    assert "2 things are waiting on you." in refreshed
    assert "Choose a provider" not in refreshed
