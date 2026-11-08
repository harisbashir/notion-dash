from fastapi import APIRouter, Request

from app.notion.client import NotionError
from app.routes.todos import SAVE_ERROR
from app.web import changes_for, find, render, stale_since

router = APIRouter()
OPEN_STATUSES = ["Active", "Before launch", "Not started", "On hold"]


def project_forest(projects):
    by_id = {p.id: p for p in projects}
    children = {p.id: [] for p in projects}
    roots = []
    for p in projects:
        if p.parent_id in by_id and p.parent_id != p.id:
            children[p.parent_id].append(p)
        else:
            roots.append(p)
    seen = set()

    def branch(p):
        seen.add(p.id)
        return {
            "project": p,
            "children": [branch(c) for c in children[p.id] if c.id not in seen],
        }

    trees = [branch(p) for p in roots]
    # Malformed/cyclic relations still appear once, rather than disappearing.
    for p in projects:
        if p.id not in seen:
            trees.append(branch(p))
    return trees


@router.get("/projects")
async def board(request: Request, area: str = ""):
    store = request.app.state.store
    result = await store.projects()
    todos = await store.todos()
    items = [p for p in result.items if not area or p.area == area]
    trees = project_forest(items)
    statuses = OPEN_STATUSES + list(
        dict.fromkeys(
            p.status or "No status"
            for p in items
            if p.status not in OPEN_STATUSES + ["Live", "Done"]
        )
    )
    counts = {
        p.id: sum(p.id in t.project_ids and t.status != "Done" for t in todos.items)
        for p in items
    }
    return render(
        request,
        "projects.html",
        groups=[
            (s, [t for t in trees if (t["project"].status or "No status") == s])
            for s in statuses
        ],
        closed_groups=[
            (s, [t for t in trees if t["project"].status == s])
            for s in ["Live", "Done"]
        ],
        counts=counts,
        area=area,
        area_options=store.options("projects", "area"),
        stale_since=stale_since(result, todos),
    )


async def fields_context(request, page_id):
    store = request.app.state.store
    projects = await store.projects()
    return dict(
        project=find(projects.items, page_id),
        stale_since=projects.stale_since,
        status_options=store.options("projects", "status"),
        priority_options=store.options("projects", "priority"),
    )


@router.get("/projects/{page_id}")
async def detail(request: Request, page_id: str):
    store = request.app.state.store
    ctx = await fields_context(request, page_id)
    projects = await store.projects()
    todos = await store.todos()
    ideas = await store.ideas()
    ai = await store.notes("ai")
    mine = await store.notes("mine")
    return render(
        request,
        "project.html",
        **{**ctx, "stale_since": stale_since(projects, todos, ideas, ai, mine)},
        projects={p.id: p for p in projects.items},
        todos=[t for t in todos.items if page_id in t.project_ids],
        ideas=[i for i in ideas.items if page_id in i.project_ids],
        ai_notes=[n for n in ai.items if page_id in n.project_ids],
        my_notes=[n for n in mine.items if page_id in n.project_ids],
    )


@router.post("/projects/{page_id}")
async def update(request: Request, page_id: str):
    ctx = await fields_context(request, page_id)
    form = await request.form()
    values = {k: (form[k] or None) for k in ("status", "priority") if k in form}
    if "summary" in form:
        values["summary"] = form["summary"]
    changes = changes_for(ctx["project"], values)
    try:
        if changes:
            ctx["project"] = await request.app.state.store.update_project(
                page_id, changes
            )
        ctx["saved"] = True
    except NotionError:
        ctx["error"] = SAVE_ERROR
    return render(request, "_project_fields.html", **ctx)
