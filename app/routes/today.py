from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request

from app.schema import classify_due
from app.web import render, stale_since

router = APIRouter()


@router.get("/")
async def today(request: Request):
    store = request.app.state.store
    todos = await store.todos()
    projects = await store.projects()
    ideas = await store.ideas()
    owner = request.app.state.settings.owner_name
    owned = sorted(
        [t for t in todos.items if t.source == "ai" and t.who == owner],
        key=lambda t: t.phase != "Question",
    )
    mine = [t for t in todos.items if t.source == "mine"]
    tz = ZoneInfo(request.app.state.settings.timezone)
    day = datetime.now(tz).date()
    due = [
        t for t in todos.items if classify_due(t.due, day, tz) in {"overdue", "soon"}
    ]
    due.sort(
        key=lambda t: (
            t.due.astimezone(tz).date() if isinstance(t.due, datetime) else t.due
        )
    )
    return render(
        request,
        "today.html",
        owned=owned,
        mine=mine,
        due=due,
        waiting=len(owned) + len(mine),
        new_ideas=sum(i.status == "New" for i in ideas.items),
        projects={p.id: p for p in projects.items},
        stale_since=stale_since(todos, projects, ideas),
    )
