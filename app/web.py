import json
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from fastapi.templating import Jinja2Templates

from app.notion.client import NotionError
from app.schema import classify_due, project_name

ROOT = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=ROOT / "templates")


def safe_url(value):
    try:
        return (
            value
            if urlsplit(value or "").scheme.lower() in {"http", "https", "mailto"}
            else ""
        )
    except ValueError:
        return ""


TEMPLATES.env.filters["safe_url"] = safe_url
TEMPLATES.env.globals["project_name"] = project_name


def friendly_due(due, today, tz):
    if not due:
        return ""
    day = due.astimezone(tz).date() if isinstance(due, datetime) else due
    delta = (day - today).days
    if delta == 0:
        return "today"
    if delta == 1:
        return "tomorrow"
    if delta == -1:
        return "yesterday"
    if 1 < delta < 7:
        return day.strftime("%A")
    label = f"{day.day} {day.strftime('%b')}"
    return label if day.year == today.year else f"{label} {day.year}"


async def navigation_context(request: Request):
    # Badge reads use the store cache and must not prevent other screens opening.
    if request.method != "GET":
        return
    try:
        result = await request.app.state.store.todos()
    except NotionError:
        return
    request.state.questions_count = sum(
        t.source == "ai"
        and t.who == request.app.state.settings.owner_name
        and t.phase == "Question"
        and t.status != "Done"
        for t in result.items
    )


def todo_meta(todo, projects, owner, project_page=False):
    facts = []
    if todo.project_ids and not project_page:
        facts.append(("project", project_name(todo.project_ids, projects)))
    if todo.due:
        facts.append(("due", todo.due))
    if todo.source == "ai" and todo.who and todo.who != owner:
        facts.append(("owner", todo.who))
    if todo.status in {"In progress", "Waiting"}:
        facts.append(("status", todo.status))
    return facts[:2]


def render(request, template, *, status_code=200, refresh=False, **ctx):
    tz = ZoneInfo(request.app.state.settings.timezone)
    today = datetime.now(tz).date()
    stale = ctx.get("stale_since")
    response = TEMPLATES.TemplateResponse(
        request=request,
        name=template,
        context={
            "todo_meta": todo_meta,
            "project_page": request.query_params.get("project_page", ""),
            "questions_count": getattr(request.state, "questions_count", 0),
            "fragment": request.headers.get("HX-Request") == "true",
            "occurrence": request.query_params.get("occurrence", ""),
            "owner_name": request.app.state.settings.owner_name,
            "today_label": f"{today:%A} {today.day} {today:%B}",
            "due_class": lambda due: classify_due(due, today, tz),
            "due_value": lambda due: (
                due.astimezone(tz).date().isoformat()
                if isinstance(due, datetime)
                else due.isoformat()
                if due
                else ""
            ),
            "due_label": lambda due: friendly_due(due, today, tz),
            "stale_time": stale.astimezone(tz).strftime("%H:%M") if stale else "",
            **ctx,
        },
        status_code=status_code,
    )

    if refresh:
        response.headers["HX-Trigger-After-Swap"] = "refreshDashboard"
    return response


def stale_since(*results):
    dates = [r.stale_since for r in results if r.stale_since is not None]
    return min(dates) if dates else None


def find(items, page_id):
    for item in items:
        if item.id == page_id:
            return item
    raise HTTPException(404, "Item not found")


def changes_for(item, values, original=None):
    baseline = {}
    if original:
        try:
            baseline = json.loads(original)
        except (ValueError, TypeError):
            raise HTTPException(422, "Invalid original values") from None
        if not isinstance(baseline, dict):
            raise HTTPException(422, "Invalid original values")

    def normalized(value):
        return value.isoformat() if isinstance(value, date) else value

    return {
        key: value
        for key, value in values.items()
        if getattr(item, key) != value
        and (key not in baseline or normalized(value) != baseline[key])
    }
