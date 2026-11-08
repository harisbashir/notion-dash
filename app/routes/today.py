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
    open_items = [t for t in todos.items if t.status != "Done"]
    questions = [
        t
        for t in open_items
        if t.source == "ai" and t.who == owner and t.phase == "Question"
    ]
    seen = {(t.source, t.id) for t in questions}
    tz = ZoneInfo(request.app.state.settings.timezone)
    day = datetime.now(tz).date()
    due = [
        t
        for t in open_items
        if (t.source, t.id) not in seen
        and classify_due(t.due, day, tz) in {"overdue", "soon"}
    ]
    due.sort(
        key=lambda t: (
            t.due.astimezone(tz).date() if isinstance(t.due, datetime) else t.due
        )
    )
    seen.update((t.source, t.id) for t in due)
    by_project = {}
    project_map = {p.id: p for p in projects.items}
    for t in open_items:
        key = (t.source, t.id)
        if key in seen or not (t.source == "mine" or t.who == owner):
            continue
        seen.add(key)
        project_id = next((pid for pid in t.project_ids if pid in project_map), "")
        by_project.setdefault(project_id, []).append(t)
    project_groups = [
        (project_map[pid].name if pid else "No project", items)
        for pid, items in sorted(
            by_project.items(), key=lambda pair: (not pair[0], -len(pair[1]))
        )
    ]
    groups = [("Questions", questions), ("Due soon", due)] + project_groups
    # Due-soon can include AI-owned items; only count what is waiting on the owner.
    waiting = sum(
        1 for _, items in groups for t in items if t.source == "mine" or t.who == owner
    )
    return render(
        request,
        "today.html",
        groups=groups,
        questions_count=len(questions),
        waiting=waiting,
        new_ideas=sum(i.status == "New" for i in ideas.items),
        projects={p.id: p for p in projects.items},
        stale_since=stale_since(todos, projects, ideas),
    )
