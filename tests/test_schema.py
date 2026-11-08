import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app.schema import (
    classify_due,
    options_from_schema,
    parse_idea,
    parse_note,
    parse_project,
    parse_todo,
    project_name,
    prop_date,
    prop_multi_select,
    prop_relation,
    prop_select,
    prop_status,
    prop_text,
    prop_title,
)


def fixture(name):
    return json.loads((Path(__file__).parent / "fixtures" / f"{name}.json").read_text())


EDITED = datetime.fromisoformat("2026-11-08T12:00:00+00:00")
CREATED = datetime.fromisoformat("2026-11-01T12:00:00+00:00")


def test_parse_project():
    assert asdict(parse_project(fixture("project"))) == {
        "id": "fake-project",
        "url": "https://www.notion.so/fake-project",
        "name": "Example project",
        "status": "Active",
        "priority": "High",
        "area": "Personal",
        "summary": "A sample summary",
        "code_url": "https://example.com/code",
        "live_url": "https://example.com/live",
        "parent_id": "fake-parent",
        "last_edited": EDITED,
        "source": "work",
    }


@pytest.mark.parametrize(
    "source,name,expected",
    [
        (
            "ai",
            "ai_todo",
            {
                "id": "fake-ai-todo",
                "url": "https://www.notion.so/fake-ai_todo",
                "source": "ai",
                "title": "Review sample",
                "status": "To do",
                "priority": "High",
                "due": datetime.fromisoformat("2026-11-09T02:00:00+00:00"),
                "notes": "Ask about examples",
                "project_ids": ["fake-project"],
                "who": "Example Owner",
                "phase": "Question",
                "added_by": "Example Agent",
                "last_edited": EDITED,
            },
        ),
        (
            "mine",
            "my_task",
            {
                "id": "fake-my-task",
                "url": "https://www.notion.so/fake-my_task",
                "source": "mine",
                "title": "Write sample",
                "status": "In progress",
                "priority": "Low",
                "due": date(2026, 11, 10),
                "notes": "Some notes",
                "project_ids": ["fake-project"],
                "who": None,
                "phase": None,
                "added_by": None,
                "last_edited": EDITED,
            },
        ),
    ],
)
def test_parse_todo(source, name, expected):
    assert asdict(parse_todo(fixture(name), source)) == expected


def test_parse_idea():
    assert asdict(parse_idea(fixture("idea"))) == {
        "id": "fake-idea",
        "url": "https://www.notion.so/fake-idea",
        "title": "Sample idea",
        "status": "New",
        "details": "Try something new",
        "project_ids": ["fake-project"],
        "added_by": "Example Owner",
        "created": CREATED,
    }


@pytest.mark.parametrize(
    "source,name,expected",
    [
        (
            "ai",
            "ai_note",
            {
                "id": "fake-ai-note",
                "url": "https://www.notion.so/fake-ai_note",
                "source": "ai",
                "title": "Sample decision",
                "type": "Decision",
                "details": "Sample details",
                "project_ids": ["fake-project"],
                "tags": [],
                "date": date(2026, 11, 2),
                "last_edited": EDITED,
            },
        ),
        (
            "mine",
            "my_note",
            {
                "id": "fake-my-note",
                "url": "https://www.notion.so/fake-my_note",
                "source": "mine",
                "title": "Sample note",
                "type": "Note",
                "details": None,
                "project_ids": ["fake-project"],
                "tags": ["Example", "Work"],
                "date": None,
                "last_edited": EDITED,
            },
        ),
    ],
)
def test_parse_note(source, name, expected):
    assert asdict(parse_note(fixture(name), source)) == expected


@pytest.mark.parametrize(
    "builder,key", [(prop_text, "rich_text"), (prop_title, "title")]
)
def test_rich_text_splits_long_text(builder, key):
    result = builder("x" * 4500)[key]
    assert [len(item["text"]["content"]) for item in result] == [2000, 2000, 500]
    assert "".join(item["text"]["content"] for item in result) == "x" * 4500
    assert builder("") == {key: []}


def test_prop_select_none():
    assert prop_select(None) == {"select": None}


def test_other_payload_builders():
    assert prop_select("High") == {"select": {"name": "High"}}
    assert prop_status("Done") == {"status": {"name": "Done"}}
    assert prop_date(date(2026, 11, 8)) == {"date": {"start": "2026-11-08"}}
    assert prop_date(None) == {"date": None}
    assert prop_relation(["fake-project"]) == {"relation": [{"id": "fake-project"}]}
    assert prop_multi_select(["Example"]) == {"multi_select": [{"name": "Example"}]}


def test_options_from_schema():
    assert options_from_schema(fixture("data_source_schema")) == {
        "Status": ["New", "Custom status"],
        "Priority": ["High", "Custom priority"],
        "Tags": ["Example"],
    }


@pytest.mark.parametrize(
    "due,expected",
    [
        (date(2026, 11, 7), "overdue"),
        (date(2026, 11, 8), "soon"),
        (date(2026, 11, 15), "soon"),
        (date(2026, 11, 16), "later"),
        (None, "none"),
        (datetime.fromisoformat("2026-11-09T02:00:00Z"), "soon"),
        (datetime.fromisoformat("2026-11-08T02:00:00Z"), "overdue"),
    ],
)
def test_due_classification(due, expected):
    assert classify_due(due, date(2026, 11, 8), ZoneInfo("America/Toronto")) == expected


def test_unknown_project_relation():
    projects = {"fake-project": parse_project(fixture("project"))}
    assert project_name(["fake-unknown"], projects) == "Unknown project"
    assert project_name([], projects) == ""
    assert project_name(["fake-unknown", "fake-project"], projects) == "Example project"


@pytest.mark.parametrize(
    "parser",
    [
        parse_project,
        parse_idea,
        lambda p: parse_todo(p, "ai"),
        lambda p: parse_todo(p, "mine"),
        lambda p: parse_note(p, "ai"),
        lambda p: parse_note(p, "mine"),
    ],
)
@pytest.mark.parametrize(
    "props",
    [
        {},
        {
            "Status": {"type": "status", "status": None},
            "Project": {"type": "relation", "relation": []},
            "Name": {"type": "title", "title": []},
        },
    ],
)
def test_missing_and_empty_properties(parser, props):
    parsed = asdict(parser({"id": "fake-empty", "properties": props}))
    assert parsed.get("title", parsed.get("name")) == ""
    assert parsed.get("status") is None
    assert parsed.get("project_ids", []) == []
