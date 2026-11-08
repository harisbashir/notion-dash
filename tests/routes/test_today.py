from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def test_today_sections(web_client):
    text = web_client.get("/").text
    for heading in [
        "3 things are waiting on you.",
        "Questions for you",
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
    store.todo_items = []
    assert "Nothing is waiting on you." in web_client.get("/").text
    # A task for someone else doesn't increase the owner's count.


def test_today_row_ids_unique(web_client):
    import re

    ids = re.findall(r'\bid="([^"]+)"', web_client.get("/").text)
    assert len(ids) == len(set(ids))
