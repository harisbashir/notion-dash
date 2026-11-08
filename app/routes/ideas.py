from fastapi import APIRouter, HTTPException, Request

from app.notion.client import NotionError
from app.routes.todos import SAVE_ERROR
from app.web import changes_for, find, render, stale_since

router = APIRouter()


async def context(request, include_closed=False):
    store = request.app.state.store
    ideas = await store.ideas(include_closed=include_closed)
    projects = await store.projects()
    return dict(
        ideas=ideas.items,
        projects={p.id: p for p in projects.items},
        status_options=store.options("ideas", "status"),
        stale_since=stale_since(ideas, projects),
    )


@router.get("/ideas")
async def ideas(request: Request, closed: bool = False, status: str = "New"):
    closed = closed or status == "Closed"
    ctx = await context(request, closed)
    selected = "Closed" if closed else status
    ctx["ideas"] = [
        i
        for i in ctx["ideas"]
        if (i.status in {"Done", "Dropped"} if closed else i.status == selected)
    ]
    return render(request, "ideas.html", **ctx, selected=selected)


@router.post("/ideas")
async def create(request: Request):
    form = await request.form()
    title = str(form.get("title", "")).strip()
    if not title:
        raise HTTPException(422, "Title is required")
    ctx = await context(request)
    try:
        ctx["idea"] = await request.app.state.store.create_idea(
            title, form.get("details", ""), form.get("project") or None
        )
    except NotionError:
        response = render(
            request,
            "_idea_new.html",
            **ctx,
            title=title,
            details=form.get("details", ""),
            project=form.get("project", ""),
            error=SAVE_ERROR,
        )
        response.headers["HX-Retarget"] = "#idea-new"
        response.headers["HX-Reswap"] = "outerHTML"
        return response
    return render(request, "_idea_row.html", **ctx, saved=True, refresh=True)


@router.post("/ideas/{page_id}")
async def update(request: Request, page_id: str):
    ctx = await context(request, True)
    ctx["idea"] = find(ctx["ideas"], page_id)
    form = await request.form()
    values = {}
    if "status" in form:
        values["status"] = form["status"] or None
    if "project" in form and form["project"] != next(iter(ctx["idea"].project_ids), ""):
        values["project_ids"] = [form["project"]] if form["project"] else []
    changes = changes_for(ctx["idea"], values, form.get("_original"))
    try:
        if changes:
            ctx["idea"] = await request.app.state.store.update_idea(page_id, changes)
        ctx["saved"] = True
    except NotionError:
        ctx["error"] = SAVE_ERROR
    return render(request, "_idea_row.html", refresh=ctx.get("saved", False), **ctx)
