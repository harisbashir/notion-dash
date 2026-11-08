from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

FIELDS: dict[str, dict[str, str]] = {
    "projects": {
        "name": "Project",
        "status": "Status",
        "priority": "Priority",
        "area": "Area",
        "summary": "Summary",
        "code_url": "Code",
        "live_url": "Live site",
        "parent_id": "Parent Project",
        "subproject_ids": "Sub-projects",
    },
    "hq_projects": {
        "name": "Name",
        "status": "Status",
        "priority": "Priority",
        "area": "Area",
        "summary": "Summary",
        "parent_id": "Parent Project",
        "subproject_ids": "Sub-projects",
    },
    "ai_todos": {
        "title": "Task",
        "status": "Status",
        "who": "Who",
        "phase": "Phase",
        "priority": "Priority",
        "due": "Due",
        "notes": "Notes",
        "project_ids": "Project",
        "added_by": "Added by",
        "added": "Added",
    },
    "my_tasks": {
        "title": "Name",
        "status": "Status",
        "priority": "Priority",
        "due": "Due date",
        "notes": "Notes",
        "project_ids": "Project",
        "list": "List",
        "parent_id": "Parent Task",
    },
    "hq_tasks": {
        "title": "Name",
        "status": "Status",
        "priority": "Priority",
        "due": "Due date",
        "notes": "Notes",
        "project_ids": "Project",
        "list": "List",
        "parent_id": "Parent Task",
    },
    "ideas": {
        "title": "Idea",
        "status": "Status",
        "details": "Details",
        "project_ids": "Project",
        "added_by": "Added by",
        "created": "Added",
    },
    "ai_notes": {
        "title": "Note",
        "type": "Type",
        "details": "Details",
        "date": "Date",
        "project_ids": "Project",
        "added_by": "Added by",
    },
    "my_notes": {
        "title": "Name",
        "type": "Type",
        "tags": "Tags",
        "project_ids": "Project",
        "last_edited": "Last edited",
    },
    "hq_notes": {
        "title": "Name",
        "type": "Type",
        "tags": "Tags",
        "project_ids": "Project",
        "last_edited": "Last edited",
    },
}

# Haris HQ (personal space) is optional; "home" marks items that live there.
TODO_DS = {"ai": "ai_todos", "mine": "my_tasks", "home": "hq_tasks"}
NOTE_DS = {"ai": "ai_notes", "mine": "my_notes", "home": "hq_notes"}
PROJECT_DS = {"work": "projects", "home": "hq_projects"}
OPTIONAL_DS = {"hq_projects", "hq_tasks", "hq_notes"}


@dataclass(frozen=True)
class Project:
    id: str
    url: str
    name: str
    status: str | None
    priority: str | None
    area: str | None
    summary: str
    code_url: str | None
    live_url: str | None
    parent_id: str | None
    last_edited: datetime | None
    source: Literal["work", "home"] = "work"


@dataclass(frozen=True)
class Todo:
    id: str
    url: str
    source: Literal["ai", "mine", "home"]
    title: str
    status: str | None
    priority: str | None
    due: date | datetime | None
    notes: str
    project_ids: list[str]
    who: str | None
    phase: str | None
    added_by: str | None
    last_edited: datetime | None


@dataclass(frozen=True)
class Idea:
    id: str
    url: str
    title: str
    status: str | None
    details: str
    project_ids: list[str]
    added_by: str | None
    created: datetime | None


@dataclass(frozen=True)
class Note:
    id: str
    url: str
    source: Literal["ai", "mine", "home"]
    title: str
    type: str | None
    details: str | None
    project_ids: list[str]
    tags: list[str]
    date: date | None
    last_edited: datetime | None


def _value(page, ds, field):
    prop = (page.get("properties") or {}).get(FIELDS[ds].get(field)) or {}
    kind = prop.get("type")
    if kind is None:
        kind = next((key for key in prop if key not in {"id", "name"}), None)
    value = prop.get(kind)
    if kind in {"title", "rich_text"}:
        return "".join(
            part.get("plain_text", (part.get("text") or {}).get("content", ""))
            for part in value or []
        )
    if kind in {"status", "select"}:
        return (value or {}).get("name")
    if kind == "relation":
        return [item["id"] for item in value or []]
    if kind == "multi_select":
        return [item["name"] for item in value or []]
    if kind == "date":
        return (value or {}).get("start")
    return value


def _datetime(value):
    return datetime.fromisoformat(value) if value else None


def _date(value):
    if not value:
        return None
    return datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)


def _base(page):
    return {"id": page.get("id", ""), "url": page.get("url", "")}


def parse_project(page, source="work") -> Project:
    def v(field):
        return _value(page, PROJECT_DS[source], field)

    parents = v("parent_id") or []
    return Project(
        **_base(page),
        name=v("name") or "",
        status=v("status"),
        priority=v("priority"),
        area=v("area"),
        summary=v("summary") or "",
        code_url=v("code_url"),
        live_url=v("live_url"),
        parent_id=parents[0] if parents else None,
        last_edited=_datetime(page.get("last_edited_time")),
        source=source,
    )


def parse_todo(page, source) -> Todo:
    def v(field):
        return _value(page, TODO_DS[source], field)

    return Todo(
        **_base(page),
        source=source,
        title=v("title") or "",
        status=v("status"),
        priority=v("priority"),
        due=_date(v("due")),
        notes=v("notes") or "",
        project_ids=v("project_ids") or [],
        who=v("who"),
        phase=v("phase"),
        added_by=v("added_by"),
        last_edited=_datetime(page.get("last_edited_time")),
    )


def parse_idea(page) -> Idea:
    def v(field):
        return _value(page, "ideas", field)

    return Idea(
        **_base(page),
        title=v("title") or "",
        status=v("status"),
        details=v("details") or "",
        project_ids=v("project_ids") or [],
        added_by=v("added_by"),
        created=_datetime(v("created") or page.get("created_time")),
    )


def parse_note(page, source) -> Note:
    def v(field):
        return _value(page, NOTE_DS[source], field)

    parsed_date = _date(v("date"))
    return Note(
        **_base(page),
        source=source,
        title=v("title") or "",
        type=v("type"),
        details=v("details") or "" if source == "ai" else None,
        project_ids=v("project_ids") or [],
        tags=v("tags") or [],
        date=parsed_date.date() if isinstance(parsed_date, datetime) else parsed_date,
        last_edited=_datetime(page.get("last_edited_time") or v("last_edited")),
    )


def rich_text(text: str) -> list[dict]:
    return [
        {"type": "text", "text": {"content": text[start : start + 2000]}}
        for start in range(0, len(text), 2000)
    ]


def prop_title(text):
    return {"title": rich_text(text)}


def prop_text(text):
    return {"rich_text": rich_text(text)}


def prop_select(name):
    return {"select": {"name": name} if name is not None else None}


def prop_status(name):
    return {"status": {"name": name}}


def prop_date(value: date | None):
    return {"date": {"start": value.isoformat()} if value is not None else None}


def prop_relation(ids):
    return {"relation": [{"id": page_id} for page_id in ids]}


def prop_multi_select(names):
    return {"multi_select": [{"name": name} for name in names]}


def options_from_schema(ds_json) -> dict[str, list[str]]:
    result = {}
    for name, prop in (ds_json.get("properties") or {}).items():
        kind = prop.get("type")
        if kind in {"status", "select", "multi_select"}:
            result[name] = [item["name"] for item in prop[kind].get("options", [])]
    return result


def classify_due(due, today: date, tz: ZoneInfo):
    if due is None:
        return "none"
    if isinstance(due, datetime):
        due = due.astimezone(tz).date()
    if due < today:
        return "overdue"
    return "soon" if due <= today + timedelta(days=7) else "later"


def project_name(ids, projects: dict[str, Project]) -> str:
    for page_id in ids:
        if page_id in projects:
            return projects[page_id].name
    return "Unknown project" if ids else ""
