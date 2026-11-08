from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request

from app.notion.client import NotionError
from app.web import changes_for, find, render, stale_since

router = APIRouter()
Source = Literal["ai", "mine"]
SAVE_ERROR = "Couldn't save to Notion. Your change wasn't saved."


async def todo_context(request, source, page_id):
    store = request.app.state.store
    todos = await store.todos(include_done=True)
    projects = await store.projects()
    todo = find([t for t in todos.items if t.source == source], page_id)
    ds = "ai_todos" if source == "ai" else "my_tasks"
    return dict(
        todo=todo,
        projects={p.id: p for p in projects.items},
        stale_since=stale_since(todos, projects),
        status_options=store.options(ds, "status"),
        priority_options=store.options(ds, "priority"),
    )


@router.get("/todos")
async def todos(
    request: Request,
    who: str = "",
    project: str = "",
    status: str = "",
    done: bool = False,
):
    store = request.app.state.store
    result = await store.todos(include_done=done)
    projects = await store.projects()
    items = [
        t
        for t in result.items
        if (
            not who
            or (request.app.state.settings.owner_name if t.source == "mine" else t.who)
            == who
        )
        and (not project or project in t.project_ids)
        and (not status or t.status == status)
    ]
    return render(
        request,
        "todos.html",
        todos=items,
        projects={p.id: p for p in projects.items},
        stale_since=stale_since(result, projects),
        who=who,
        project=project,
        status=status,
        done=done,
        who_options=store.options("ai_todos", "who"),
        status_options=list(
            dict.fromkeys(
                store.options("ai_todos", "status")
                + store.options("my_tasks", "status")
            )
        ),
    )


@router.get("/todos/{source}/{page_id}/edit")
async def edit(request: Request, source: Source, page_id: str):
    return render(
        request, "_todo_editor.html", **await todo_context(request, source, page_id)
    )


@router.get("/todos/{source}/{page_id}")
async def row(request: Request, source: Source, page_id: str):
    return render(
        request, "_todo_row.html", **await todo_context(request, source, page_id)
    )


@router.post("/todos/{source}/{page_id}/done")
async def toggle(request: Request, source: Source, page_id: str):
    ctx = await todo_context(request, source, page_id)
    todo = ctx["todo"]
    try:
        ctx["todo"] = await request.app.state.store.update_todo(
            source, page_id, {"status": "To do" if todo.status == "Done" else "Done"}
        )
        ctx["saved"] = True
    except NotionError:
        ctx["error"] = SAVE_ERROR
    return render(request, "_todo_row.html", refresh=ctx.get("saved", False), **ctx)


@router.post("/todos/{source}/{page_id}")
async def update(request: Request, source: Source, page_id: str):
    ctx = await todo_context(request, source, page_id)
    todo = ctx["todo"]
    form = await request.form()
    values = {k: (form[k] or None) for k in ("status", "priority") if k in form}
    if "notes" in form:
        values["notes"] = form["notes"]
    if "project" in form and form["project"] != next(iter(todo.project_ids), ""):
        values["project_ids"] = [form["project"]] if form["project"] else []
    if "due" in form:
        old = todo.due
        if isinstance(old, datetime):
            old = old.astimezone(ZoneInfo(request.app.state.settings.timezone)).date()
        try:
            due = date.fromisoformat(form["due"]) if form["due"] else None
        except ValueError:
            raise HTTPException(422, "Invalid due date") from None
        if due != old:
            values["due"] = due
    changes = changes_for(todo, values, form.get("_original"))
    try:
        if changes:
            ctx["todo"] = await request.app.state.store.update_todo(
                source, page_id, changes
            )
        ctx["saved"] = True
    except NotionError:
        ctx["error"] = SAVE_ERROR
    return render(request, "_todo_row.html", refresh=ctx.get("saved", False), **ctx)


@router.post("/todos")
async def create(request: Request):
    form = await request.form()
    title = str(form.get("title", "")).strip()
    if not title:
        raise HTTPException(422, "Title is required")
    projects = await request.app.state.store.projects()
    ctx = dict(
        projects={p.id: p for p in projects.items},
        title=title,
        project=form.get("project", ""),
        stale_since=projects.stale_since,
    )
    try:
        ctx["todo"] = await request.app.state.store.create_my_task(
            title, form.get("project") or None
        )
    except NotionError:
        response = render(request, "_task_new.html", error=SAVE_ERROR, **ctx)
        response.headers["HX-Retarget"] = "#task-new"
        response.headers["HX-Reswap"] = "outerHTML"
        return response
    return render(request, "_todo_row.html", saved=True, refresh=True, **ctx)
