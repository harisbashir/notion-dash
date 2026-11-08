import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.blocks import render_blocks, text_to_blocks
from app.notion.client import NotionError
from app.routes.todos import SAVE_ERROR, Source
from app.web import changes_for, find, render, stale_since

router = APIRouter()


async def context(request, source):
    store = request.app.state.store
    notes = await store.notes(source)
    projects = await store.projects()
    return dict(
        notes=notes.items,
        projects={p.id: p for p in projects.items},
        type_options=store.options(
            "ai_notes" if source == "ai" else "my_notes", "type"
        ),
        stale_since=stale_since(notes, projects),
    )


@router.get("/notes")
async def notes(
    request: Request,
    tab: Literal["mine", "ai"] = "mine",
    type: str = "",
    project: str = "",
):
    ctx = await context(request, tab)
    ctx["notes"] = [
        n
        for n in ctx["notes"]
        if (not type or n.type == type) and (not project or project in n.project_ids)
    ]
    return render(request, "notes.html", **ctx, tab=tab, type=type, project=project)


@router.get("/notes/new")
async def new(request: Request):
    return render(request, "_note_new.html", **await context(request, "mine"))


@router.get("/notes/{source}/{page_id}")
async def detail(request: Request, source: Source, page_id: str):
    ctx = await context(request, source)
    ctx["note"] = find(ctx["notes"], page_id)
    body = await request.app.state.store.note_body(page_id)
    return render(
        request, "note.html", **ctx, body=render_blocks(body), body_blocks=body
    )


@router.post("/notes")
async def create(request: Request):
    form = await request.form()
    title = str(form.get("title", "")).strip()
    if not title:
        raise HTTPException(422, "Title is required")
    try:
        note = await request.app.state.store.create_my_note(
            title,
            form.get("type") or None,
            form.get("project") or None,
            form.get("body", ""),
        )
    except NotionError:
        return render(
            request,
            "_note_new.html",
            **await context(request, "mine"),
            title=title,
            type=form.get("type", ""),
            project=form.get("project", ""),
            body=form.get("body", ""),
            error=SAVE_ERROR,
        )
    return Response(status_code=200, headers={"HX-Redirect": f"/notes/mine/{note.id}"})


@router.post("/notes/{page_id}/append")
async def append(request: Request, page_id: str):
    store = request.app.state.store
    mine = await store.notes("mine")
    ai = await store.notes("ai")
    note = find(mine.items + ai.items, page_id)
    form = await request.form()
    text = str(form.get("text", ""))
    if not text.strip():
        raise HTTPException(422, "Text is required")
    try:
        body = await store.note_body(page_id)
    except NotionError:
        if "_body" not in form:
            raise
        try:
            body = json.loads(form["_body"])
        except (ValueError, TypeError):
            raise HTTPException(422, "Invalid note body") from None
        if not isinstance(body, list) or any(not isinstance(b, dict) for b in body):
            raise HTTPException(422, "Invalid note body")
    error = None
    notice = None
    try:
        await store.append_note(page_id, text)
    except NotionError:
        error = SAVE_ERROR
    else:
        try:
            body = await store.note_body(page_id)
        except NotionError:
            body = body + text_to_blocks(text)
            notice = "Saved to Notion. The full note couldn't be refreshed."
    return render(
        request,
        "_note_body.html",
        note=note,
        body=render_blocks(body),
        body_blocks=body,
        error=error,
        notice=notice,
        append_text=text if error else "",
        stale_since=stale_since(mine, ai),
    )


@router.post("/notes/{source}/{page_id}")
async def update(request: Request, source: Source, page_id: str):
    ctx = await context(request, source)
    ctx["note"] = find(ctx["notes"], page_id)
    form = await request.form()
    values = {}
    if "type" in form:
        values["type"] = form["type"] or None
    if "project" in form and form["project"] != next(iter(ctx["note"].project_ids), ""):
        values["project_ids"] = [form["project"]] if form["project"] else []
    changes = changes_for(ctx["note"], values, form.get("_original"))
    try:
        if changes:
            ctx["note"] = await request.app.state.store.update_note(
                source, page_id, changes
            )
        ctx["saved"] = True
    except NotionError:
        ctx["error"] = SAVE_ERROR
    return render(request, "_note_fields.html", **ctx)
