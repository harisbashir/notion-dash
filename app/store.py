import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.blocks import text_to_blocks
from app.config import Settings
from app.notion.client import NotionError
from app.schema import (
    FIELDS,
    options_from_schema,
    parse_idea,
    parse_note,
    parse_project,
    parse_todo,
    prop_date,
    prop_multi_select,
    prop_relation,
    prop_select,
    prop_status,
    prop_text,
    prop_title,
)


@dataclass
class Result[T]:
    items: list[T]
    stale_since: datetime | None = None


@dataclass
class _Entry:
    pages: list[dict]
    fetched: float
    loaded_at: datetime


class Store:
    def __init__(self, client, settings: Settings, *, clock=time.monotonic):
        self.client = client
        self.settings = settings
        self.clock = clock
        self._locks = {ds: asyncio.Lock() for ds in FIELDS}
        self._cache: dict[tuple[str, str], _Entry] = {}
        self._options: dict[str, dict[str, list[str]]] = {}
        self.missing: list[str] = []

    async def load_options(self) -> None:
        self.missing = []
        for ds in FIELDS:
            try:
                schema = await self.client.get_data_source(
                    getattr(self.settings, f"ds_{ds}")
                )
            except NotionError:
                self.missing.append(ds)
            else:
                self._options[ds] = options_from_schema(schema)

    def options(self, ds_key: str, field: str) -> list[str]:
        name = FIELDS[ds_key].get(field, field)
        return list(self._options.get(ds_key, {}).get(name, []))

    def _filter(self, ds, mode):
        name = FIELDS[ds].get("status")
        if mode == "all" or name is None:
            return None
        op = "equals" if mode == "closed" else "does_not_equal"
        values = ["Done", "Dropped"] if ds == "ideas" else ["Done"]
        conditions = [{"property": name, "status": {op: value}} for value in values]
        if len(conditions) == 1:
            return conditions[0]
        return {"or" if mode == "closed" else "and": conditions}

    def _parse(self, ds, page):
        if ds == "projects":
            return parse_project(page)
        if ds == "ideas":
            return parse_idea(page)
        source = "ai" if ds.startswith("ai_") else "mine"
        return (
            parse_todo(page, source)
            if ds in {"ai_todos", "my_tasks"}
            else parse_note(page, source)
        )

    async def _read(self, ds, mode="all"):
        # Keep a refresh response from replacing a newer successful write.
        async with self._locks[ds]:
            return await self._fetch(ds, mode)

    async def _fetch(self, ds, mode):
        key = (ds, mode)
        entry = self._cache.get(key)
        stale = None
        if (
            entry is None
            or self.clock() - entry.fetched >= self.settings.cache_ttl_seconds
        ):
            kwargs = {"filter": self._filter(ds, mode)}
            if mode == "closed" and ds in {"ai_todos", "my_tasks"}:
                kwargs.update(
                    sorts=[
                        {"timestamp": "last_edited_time", "direction": "descending"}
                    ],
                    limit=50,
                )
            try:
                pages = await self.client.query(
                    getattr(self.settings, f"ds_{ds}"), **kwargs
                )
            except NotionError:
                if entry is None:
                    raise
                stale = entry.loaded_at
            else:
                entry = _Entry(pages, self.clock(), datetime.now(UTC))
                self._cache[key] = entry
        return Result([self._parse(ds, page) for page in entry.pages], stale)

    async def _merge(self, keys):
        items = []
        stale = []
        for ds, mode in keys:
            result = await self._read(ds, mode)
            items.extend(result.items)
            if result.stale_since is not None:
                stale.append(result.stale_since)
        return Result(items, min(stale) if stale else None)

    async def projects(self):
        return await self._read("projects")

    async def todos(self, include_done: bool = False):
        keys = [(ds, "open") for ds in ("ai_todos", "my_tasks")]
        if include_done:
            keys.extend((ds, "closed") for ds in ("ai_todos", "my_tasks"))
        return await self._merge(keys)

    async def ideas(self, include_closed: bool = False):
        keys = [("ideas", "open")]
        if include_closed:
            keys.append(("ideas", "closed"))
        return await self._merge(keys)

    async def notes(self, source):
        return await self._read("ai_notes" if source == "ai" else "my_notes")

    async def note_body(self, page_id):
        return await self.client.list_children(page_id)

    def _properties(self, ds, changes):
        payload = {}
        for field, value in changes.items():
            name = FIELDS[ds][field]
            if field in {"title", "name"}:
                prop = prop_title(value)
            elif field in {"summary", "notes", "details"}:
                prop = prop_text(value)
            elif field == "status":
                prop = prop_status(value)
            elif field in {"due", "date"}:
                prop = prop_date(value)
            elif field in {"project_ids", "subproject_ids"}:
                prop = prop_relation(value)
            elif field == "parent_id":
                prop = prop_relation([value] if value else [])
            elif field == "tags":
                prop = prop_multi_select(value)
            elif field in {"code_url", "live_url"}:
                prop = {"url": value}
            elif field in {"added", "created", "last_edited"}:
                raise ValueError(f"Read-only field: {field}")
            else:
                prop = prop_select(value)
            payload[name] = prop
        return payload

    def _write_through(self, ds, page):
        model = self._parse(ds, page)
        for (cached_ds, mode), entry in self._cache.items():
            if cached_ds != ds:
                continue
            old_index = next(
                (i for i, old in enumerate(entry.pages) if old["id"] == page["id"]),
                None,
            )
            closed = getattr(model, "status", None) in (
                {"Done", "Dropped"} if ds == "ideas" else {"Done"}
            )
            belongs = mode == "all" or (mode == "closed") == closed
            if old_index is not None:
                if belongs:
                    entry.pages[old_index] = page
                else:
                    entry.pages.pop(old_index)
            elif belongs:
                entry.pages.append(page)
            if mode == "closed" and ds in {"ai_todos", "my_tasks"}:
                entry.pages.sort(
                    key=lambda p: p.get("last_edited_time", ""), reverse=True
                )
                del entry.pages[50:]
        return model

    async def _update(self, ds, page_id, changes):
        async with self._locks[ds]:
            page = await self.client.update_page(page_id, self._properties(ds, changes))
            return self._write_through(ds, page)

    async def _create(self, ds, values, children=None):
        async with self._locks[ds]:
            page = await self.client.create_page(
                getattr(self.settings, f"ds_{ds}"),
                self._properties(ds, values),
                children,
            )
            return self._write_through(ds, page)

    async def update_todo(self, source, page_id, changes: dict[str, Any]):
        return await self._update(
            "ai_todos" if source == "ai" else "my_tasks", page_id, changes
        )

    async def create_my_task(self, title, project_id=None):
        return await self._create(
            "my_tasks",
            {"title": title, "project_ids": [project_id] if project_id else []},
        )

    async def update_project(self, page_id, changes):
        return await self._update("projects", page_id, changes)

    async def update_idea(self, page_id, changes):
        return await self._update("ideas", page_id, changes)

    async def create_idea(self, title, details="", project_id=None):
        return await self._create(
            "ideas",
            {
                "title": title,
                "details": details,
                "status": "New",
                "added_by": self.settings.owner_name,
                "project_ids": [project_id] if project_id else [],
            },
        )

    async def update_note(self, source, page_id, changes):
        return await self._update(
            "ai_notes" if source == "ai" else "my_notes", page_id, changes
        )

    async def create_my_note(
        self, title, type: str | None, project_id: str | None, body: str
    ):
        return await self._create(
            "my_notes",
            {
                "title": title,
                "type": type,
                "project_ids": [project_id] if project_id else [],
            },
            text_to_blocks(body),
        )

    async def append_note(self, page_id, text):
        await self.client.append_children(page_id, text_to_blocks(text))
