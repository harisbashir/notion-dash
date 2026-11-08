from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from fastapi.templating import Jinja2Templates

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


def render(request, template, *, status_code=200, **ctx):
    tz = ZoneInfo(request.app.state.settings.timezone)
    today = datetime.now(tz).date()
    stale = ctx.get("stale_since")
    return TEMPLATES.TemplateResponse(
        request=request,
        name=template,
        context={
            "fragment": request.headers.get("HX-Request") == "true",
            "owner_name": request.app.state.settings.owner_name,
            "due_class": lambda due: classify_due(due, today, tz),
            "due_value": lambda due: (
                due.astimezone(tz).date().isoformat()
                if isinstance(due, datetime)
                else due.isoformat()
                if due
                else ""
            ),
            "stale_time": stale.astimezone(tz).strftime("%H:%M") if stale else "",
            **ctx,
        },
        status_code=status_code,
    )


def stale_since(*results):
    dates = [r.stale_since for r in results if r.stale_since is not None]
    return min(dates) if dates else None


def find(items, page_id):
    for item in items:
        if item.id == page_id:
            return item
    raise HTTPException(404, "Item not found")


def changes_for(item, values):
    return {key: value for key, value in values.items() if getattr(item, key) != value}
