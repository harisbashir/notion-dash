# notion-dash Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI + HTMX web dashboard that reads and edits the Notion "Projects HQ" databases, deployed on proxmox1 behind Tailscale.

**Architecture:** Server-rendered Jinja2 pages with HTMX fragments. A `NotionClient` (raw HTTP, rate limit, retry) feeds a `Store` (TTL cache, stale fallback, write-through), which `schema.py` maps to typed models. Routes render full pages or fragments.

**Tech Stack:** Python 3.12, uv, FastAPI, Jinja2, httpx, pydantic-settings, HTMX 2 (vendored), pytest, pytest-asyncio, respx, ruff. Docker + compose.

**Spec:** `docs/superpowers/specs/2026-11-08-notion-dash-design.md` (read it first; it is authoritative for screen behaviour).

## Execution model

Codex implements tasks in three batches (A: Tasks 1–5, B: Tasks 6–9, C: Task 10). Claude reviews and tests each batch before the next starts, and does Task 11 (deploy) itself. Before batch B, Claude adds `docs/DESIGN.md` (visual design brief); Task 6 implements it.

## Global Constraints

- Python 3.12; dependencies managed with `uv` (`pyproject.toml` + `uv.lock`).
- No secrets, Notion IDs, tailnet names or real workspace content in the repo. Test fixtures use made-up IDs and text.
- Notion API: base `https://api.notion.com/v1`, headers `Authorization: Bearer <token>`, `Notion-Version: 2025-09-03`. Use data-source endpoints: `GET /data_sources/{id}`, `POST /data_sources/{id}/query`, `POST /pages` with `parent: {"type": "data_source_id", "data_source_id": id}`, `PATCH /pages/{id}`, `GET /blocks/{id}/children`, `PATCH /blocks/{id}/children`.
- Max 3 Notion requests/second globally; max 100 blocks per append request; max 2000 characters per rich-text text object.
- Updates send only changed properties.
- Settings (env): `NOTION_TOKEN`, `DS_PROJECTS`, `DS_AI_TODOS`, `DS_MY_TASKS`, `DS_IDEAS`, `DS_AI_NOTES`, `DS_MY_NOTES`, `CACHE_TTL_SECONDS=30`, `TIMEZONE=America/Toronto`, `OWNER_NAME=Haris`.
- HTMX vendored at `app/static/htmx.min.js`; no CDN, no JS build step.
- All tests run offline (Notion mocked with respx).
- Commands: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` must all pass at the end of every task.

## Review Focus

1. Text over 2000 characters (note append, long Notes field) must be split into multiple rich-text objects, not rejected by Notion. → Task 3 (`test_rich_text_splits_long_text`), Task 5 (`test_text_to_blocks_splits_long_line`).
2. A row related to a project that isn't in the Projects cache (archived, not shared) shows "Unknown project" and doesn't crash. → Task 3 (`test_unknown_project_relation`), Task 7 route test.
3. Titles/notes containing `<script>` or HTML render escaped everywhere; links in blocks only allow http/https/mailto. → Task 5, Task 7 (`test_todo_title_escaped`).
4. Due dates: date-only vs datetime with offset; "overdue" and "due within 7 days" computed in `TIMEZONE`, today counts as due-soon not overdue. → Task 3 (`test_due_classification`).
5. Notion 429/5xx bursts and outages: retry honours `Retry-After`; reads fall back to stale cache with banner; writes show error and keep original value. → Task 2, Task 4, Task 7.

---

### Task 1: Project scaffold, config, health endpoint, CI

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `LICENSE` (MIT, Haris Bashir, 2026), `README.md` (short: what it is, local dev, link to deploy section added in Task 10), `app/__init__.py`, `app/config.py`, `app/main.py`, `tests/conftest.py`, `tests/test_config.py`, `.github/workflows/ci.yml`

**Interfaces:**
- Produces: `class Settings(BaseSettings)` with the fields in Global Constraints (`notion_token: SecretStr`, `ds_projects: str`, … , `cache_ttl_seconds: int = 30`, `timezone: str = "America/Toronto"`, `owner_name: str = "Haris"`); `get_settings() -> Settings` (lru_cached); `create_app(settings: Settings | None = None) -> FastAPI`; `GET /healthz` returns `{"status": "ok"}` for now (Task 4 extends it). `tests/conftest.py` provides fixture `settings` with fake values and `client` (TestClient over `create_app(settings)`).

- [ ] **Step 1: Write failing tests** `test_settings_from_env` (monkeypatched env → fields set, token is SecretStr and not in `repr`), `test_healthz_ok` (GET /healthz → 200, `{"status":"ok"}`).
- [ ] **Step 2: Run** `uv run pytest -q` → FAIL (module missing).
- [ ] **Step 3: Implement** config and app factory. `.gitignore` covers `.env`, `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`. `.env.example` lists every setting with placeholder values. CI: ubuntu-latest, `astral-sh/setup-uv`, run ruff check, ruff format --check, pytest.
- [ ] **Step 4: Run** pytest + ruff → PASS.
- [ ] **Step 5: Commit** `feat: scaffold app, settings and CI`.

### Task 2: Notion HTTP client

**Files:**
- Create: `app/notion/__init__.py`, `app/notion/client.py`, `tests/notion/test_client.py`

**Interfaces:**
- Consumes: `Settings.notion_token`.
- Produces:
  - `class NotionError(Exception)` with `status: int | None`, `code: str | None`; subclass `NotionUnavailable` (network errors, 5xx after retries, 429 after retries).
  - `class NotionClient`: `__init__(token: str, *, http: httpx.AsyncClient | None = None, rate_per_sec: float = 3.0, max_attempts: int = 3, sleep=asyncio.sleep)`; `async get_data_source(ds_id) -> dict`; `async query(ds_id, *, filter: dict | None = None, sorts: list | None = None, limit: int | None = None) -> list[dict]` (follows `next_cursor`, page_size 100, stops at `limit`); `async create_page(ds_id, properties: dict, children: list[dict] | None = None) -> dict`; `async update_page(page_id, properties: dict) -> dict`; `async list_children(block_id) -> list[dict]` (paginated); `async append_children(block_id, children: list[dict]) -> None` (chunks of 100); `async aclose()`.

- [ ] **Step 1: Write failing tests** (respx):
  - `test_headers` – Authorization and `Notion-Version: 2025-09-03` sent.
  - `test_query_paginates` – two pages via `has_more/next_cursor` → 150 results; `limit=120` → 120 and no third call.
  - `test_retry_after_429` – 429 with `Retry-After: 2` then 200 → result returned, injected `sleep` called with 2.
  - `test_retry_5xx_then_unavailable` – three 502s → `NotionUnavailable`.
  - `test_4xx_raises_notion_error` – 404 body `{"code":"object_not_found"}` → `NotionError(status=404, code="object_not_found")`, no retry.
  - `test_append_chunks_100` – 250 children → 3 PATCH calls of 100/100/50.
  - `test_rate_limit` – with fake clock, 6 calls take ≥ ~1.67 s of virtual time (limiter uses injected `sleep` and `time.monotonic`).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Rate limiter: simple async lock + minimum interval `1/rate_per_sec` between request starts. Backoff for 5xx without Retry-After: 1 s, 2 s.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat: Notion HTTP client with rate limit and retry`.

### Task 3: Schema mapping and property payloads

**Files:**
- Create: `app/schema.py`, `tests/fixtures/` (sanitised sample page JSON per database: `project.json`, `ai_todo.json`, `my_task.json`, `idea.json`, `ai_note.json`, `my_note.json`, `data_source_schema.json`), `tests/test_schema.py`

**Interfaces:**
- Produces (pydantic models or frozen dataclasses):
  - `Project(id, url, name, status, priority, area, summary, code_url, live_url, parent_id: str | None, last_edited: datetime)`
  - `Todo(id, url, source: Literal["ai","mine"], title, status, priority, due: date | datetime | None, notes, project_ids: list[str], who: str | None, phase: str | None, added_by: str | None, last_edited)`
  - `Idea(id, url, title, status, details, project_ids, added_by, created)`
  - `Note(id, url, source: Literal["ai","mine"], title, type, details: str | None, project_ids, tags: list[str], date: date | None, last_edited)`
  - `FIELDS: dict[str, dict[str, str]]` – logical field → Notion property name per data source key (`"projects"`, `"ai_todos"`, `"my_tasks"`, `"ideas"`, `"ai_notes"`, `"my_notes"`). Names exactly as in the spec table (e.g. My Tasks due field is `"Due date"`, AI To-do due field is `"Due"`; title fields `Project`, `Task`, `Name`, `Idea`, `Note`, `Name`).
  - Parsers: `parse_project(page) -> Project`, `parse_todo(page, source) -> Todo`, `parse_idea(page) -> Idea`, `parse_note(page, source) -> Note`.
  - Payload builders: `prop_title(text)`, `prop_text(text)` (rich_text, split into ≤2000-char chunks; empty → `[]`), `prop_select(name | None)`, `prop_status(name)`, `prop_date(value: date | None)`, `prop_relation(ids)`, `prop_multi_select(names)`. Each returns the Notion property value dict.
  - `options_from_schema(ds_json) -> dict[str, list[str]]` – property name → option names for select/status/multi_select.
  - `classify_due(due, today: date, tz: ZoneInfo) -> Literal["overdue","soon","later","none"]` – overdue if before today; soon if today..today+7; datetimes converted to `tz` first.
  - `project_name(ids, projects: dict[str, Project]) -> str` – first known name, `"Unknown project"` if ids present but none known, `""` if no ids.
- [ ] **Step 1: Write failing tests:** one parse test per model against fixtures (all fields asserted); `test_rich_text_splits_long_text` (4500 chars → 3 objects, lengths 2000/2000/500); `test_prop_select_none` → `{"select": None}`; `test_options_from_schema`; `test_due_classification` (yesterday→overdue, today→soon, +7→soon, +8→later, None→none, datetime `2026-11-09T02:00:00Z` with tz America/Toronto and today 2026-11-08 → soon); `test_unknown_project_relation`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** Missing/empty properties map to `None`/`""`/`[]`, never raise.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat: map Notion pages to models`.

### Task 4: Store (cache, stale fallback, write-through, health)

**Files:**
- Create: `app/store.py`, `tests/test_store.py`
- Modify: `app/main.py` (create client + store in lifespan; store on `app.state.store`; `/healthz` → `{"status": "ok" | "degraded", "missing": [ds keys not accessible]}` using a startup check of `get_data_source` per data source)

**Interfaces:**
- Consumes: `NotionClient`, schema parsers/builders, `Settings`.
- Produces: `class Store`:
  - `__init__(client, settings, *, clock=time.monotonic)`
  - `async load_options() -> None`; `options(ds_key: str, field: str) -> list[str]`
  - Reads (open items only unless stated; each returns `Result[T]` = `@dataclass Result(items: list[T], stale_since: datetime | None)`): `projects()`, `todos(include_done: bool = False)` (AI + mine merged; done = 50 most recently edited Done per source), `ideas(include_closed: bool = False)` (closed = Done/Dropped), `notes(source: Literal["ai","mine"])`, `note_body(page_id) -> list[dict]` (blocks; not cached).
  - Writes (return the updated model, update cache in place): `update_todo(source, page_id, changes: dict[str, Any])`, `create_my_task(title, project_id: str | None = None)`, `update_project(page_id, changes)`, `update_idea(page_id, changes)`, `create_idea(title, details="", project_id=None)` (Added by = `owner_name`, Status New), `update_note(source, page_id, changes)`, `create_my_note(title, type: str | None, project_id: str | None, body: str)`, `append_note(page_id, text)`.
  - `changes` keys are logical field names from `FIELDS`; values are Python values; Store builds payloads with the right builder per field type.
- [ ] **Step 1: Write failing tests:** `test_cache_hit_within_ttl` (two reads, one HTTP call), `test_cache_expires`, `test_stale_fallback` (expired cache + NotionUnavailable → old items, `stale_since` set), `test_no_cache_raises` (first read fails → NotionUnavailable propagates), `test_update_sends_only_changed` (update_todo status → PATCH body has only `Status`), `test_update_refreshes_cache`, `test_create_idea_defaults`, `test_open_filter_sent` (query filter `{"property":"Status","status":{"does_not_equal":"Done"}}`), `test_healthz_degraded` (one ds 404 → missing lists its key).
- [ ] **Step 2–4:** run FAIL, implement, run PASS.
- [ ] **Step 5: Commit** `feat: cached store with write-through`.

### Task 5: Block rendering and text-to-blocks

**Files:**
- Create: `app/blocks.py`, `tests/test_blocks.py`

**Interfaces:**
- Produces: `render_blocks(blocks: list[dict]) -> markupsafe.Markup`; `text_to_blocks(text: str) -> list[dict]` (one paragraph per non-empty line, lines >2000 chars split across rich-text objects).
- Supported: paragraph, heading_1/2/3, bulleted_list_item, numbered_list_item (consecutive items grouped into `<ul>`/`<ol>`), to_do (disabled checkbox), quote, callout, code (`<pre><code>`), divider; rich-text annotations bold/italic/code/strikethrough and links. Anything else → `<div class="unsupported">Unsupported block · open in Notion</div>`. Nested children are not fetched in v1.
- [ ] **Step 1: Write failing tests:** one per block type; `test_escapes_html` (`<script>` text → escaped); `test_link_scheme_allowlist` (`javascript:` link rendered as plain text); `test_list_grouping`; `test_text_to_blocks_splits_long_line`; `test_unsupported_block`.
- [ ] **Step 2–4:** FAIL, implement, PASS.
- [ ] **Step 5: Commit** `feat: render Notion blocks safely`.

### Task 6: Web shell, design system, PWA, request guard

**Files:**
- Create: `app/web.py` (templates setup, `render(request, template, **ctx)` helper returning full page or fragment based on `HX-Request`), `app/guard.py`, `app/templates/base.html`, `app/templates/_nav.html`, `app/templates/_banner.html`, `app/templates/error.html`, `app/static/app.css`, `app/static/htmx.min.js` (HTMX 2.x release file), `app/static/app.js` (≤ 60 lines: client-side list text filter, theme-color meta), `app/static/manifest.webmanifest`, `app/static/sw.js` (install + fetch passthrough, no caching), `app/static/icons/icon-192.png`, `icon-512.png`, `tests/test_guard.py`, `tests/test_shell.py`
- Modify: `app/main.py` (mount static, add guard middleware, register exception handler for `NotionUnavailable` → `error.html` with retry, status 503)

**Interfaces:**
- Produces: `render(...)`; base template blocks `title`, `content`; context var `stale_since` drives `_banner.html` ("Showing data from HH:MM; Notion unavailable"); nav items Today `/`, Projects `/projects`, To-dos `/todos`, Ideas `/ideas`, Notes `/notes` (bottom tab bar < 768px, sidebar ≥ 768px). Layout, colour, type and component styles follow `docs/DESIGN.md`. Light/dark via `prefers-color-scheme`.
- Guard: for POST/PATCH/PUT/DELETE require header `HX-Request: true` and `Origin` (or `Referer` if Origin absent) whose host equals the request `Host`; otherwise 403.
- [ ] **Step 1: Write failing tests:** `test_guard_rejects_cross_origin`, `test_guard_rejects_missing_hx`, `test_guard_allows_same_origin_htmx`, `test_get_not_guarded`, `test_manifest_served`, `test_unavailable_page_503`.
- [ ] **Step 2–4:** FAIL, implement, PASS.
- [ ] **Step 5: Commit** `feat: web shell, styles, PWA and request guard`.

### Task 7: Today and To-dos screens

**Files:**
- Create: `app/routes/__init__.py`, `app/routes/todos.py`, `app/routes/today.py`, templates `today.html`, `todos.html`, `_todo_row.html`, `_todo_editor.html`, `tests/routes/test_todos.py`, `tests/routes/test_today.py`

**Interfaces:**
- Consumes: `Store.todos/projects/ideas/update_todo/create_my_task`, `classify_due`, `project_name`, `render`.
- Routes:
  - `GET /` – Today per spec (Who == `owner_name` open AI to-dos with Phase "Question" first, open My Tasks, overdue/soon list from both, New ideas count linking `/ideas`).
  - `GET /todos?who=&project=&status=&done=1` – merged list with source badge; filters as query params.
  - `POST /todos/{source}/{id}/done` (toggle: Done ↔ "To do") → `_todo_row.html`.
  - `GET /todos/{source}/{id}/edit` → `_todo_editor.html`; `POST /todos/{source}/{id}` (form: status, priority, due, notes, project) → row. Only fields that differ from the cached value go to `update_todo`.
  - `POST /todos` (form: title, project) → creates My Task, returns new row.
  - On `NotionError` during a write: return the row with original values and an inline error message, HTTP 200 (so HTMX swaps it).
- [ ] **Step 1: Write failing tests** (Store faked via a simple in-memory fake implementing the Store interface): `test_today_sections`, `test_question_first`, `test_toggle_done`, `test_edit_sends_only_changed`, `test_write_error_keeps_value`, `test_todo_title_escaped`, `test_unknown_project_shown`, `test_filters`, `test_stale_banner`.
- [ ] **Step 2–4:** FAIL, implement, PASS.
- [ ] **Step 5: Commit** `feat: Today and To-dos screens`.

### Task 8: Projects board and project page

**Files:**
- Create: `app/routes/projects.py`, templates `projects.html`, `_project_card.html`, `project.html`, `_project_fields.html`, `tests/routes/test_projects.py`

**Interfaces:**
- Routes: `GET /projects?area=` (groups in order Active, Before launch, Not started, On hold, then collapsed `<details>` Live and Done; sub-projects nested under parent; open to-do count per card); `GET /projects/{id}` (fields + sections To-dos, Ideas, Decisions & notes, My notes filtered by project id, reusing `_todo_row.html` and Task 9 partials if present, otherwise simple lists); `POST /projects/{id}` (status, priority, summary) → `_project_fields.html`.
- [ ] **Step 1: Write failing tests:** `test_group_order`, `test_subprojects_nested`, `test_area_filter`, `test_open_todo_count`, `test_project_page_sections`, `test_update_project_fields`.
- [ ] **Step 2–4:** FAIL, implement, PASS.
- [ ] **Step 5: Commit** `feat: Projects board and project page`.

### Task 9: Ideas and Notes screens

**Files:**
- Create: `app/routes/ideas.py`, `app/routes/notes.py`, templates `ideas.html`, `_idea_row.html`, `notes.html`, `_note_row.html`, `note.html`, `_note_new.html`, `tests/routes/test_ideas.py`, `tests/routes/test_notes.py`

**Interfaces:**
- Ideas: `GET /ideas` (New, Planned, Maybe later; Done/Dropped in collapsed section loaded via `?closed=1`); `POST /ideas` (title, details, project) → row; `POST /ideas/{id}` (status, project) → row.
- Notes: `GET /notes?tab=mine|ai&type=&project=`; `GET /notes/{source}/{id}` (fields + body via `render_blocks` for mine; Details text for ai, plus body if present); `POST /notes` (title, type, project, body) → redirect header `HX-Redirect` to the new note; `POST /notes/{id}/append` (text) → re-rendered body; `POST /notes/{source}/{id}` (type, project) → fields fragment.
- [ ] **Step 1: Write failing tests:** `test_ideas_order`, `test_create_idea`, `test_idea_status_change`, `test_notes_tabs`, `test_note_body_rendered`, `test_create_note_redirect`, `test_append_note`, `test_note_type_change`.
- [ ] **Step 2–4:** FAIL, implement, PASS.
- [ ] **Step 5: Commit** `feat: Ideas and Notes screens`.

### Task 10: Container and deploy scripts

**Files:**
- Create: `Dockerfile` (python:3.12-slim, uv sync --frozen --no-dev, non-root user, `uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers`), `.dockerignore`, `compose.yml` (service `app`, build `.`, `env_file: /opt/notion-dash/.env`, ports `127.0.0.1:8000:8000`, `restart: unless-stopped`, healthcheck on `/healthz`), `scripts/deploy.sh` (`git pull --ff-only && docker compose up -d --build && docker compose ps`), `scripts/lxc-setup.md` (manual steps from the spec's Deployment section, with placeholders for host/IDs)
- Modify: `README.md` (Deploy section: create Notion integration, connect to databases, find data source IDs, fill `.env`, run compose, `tailscale serve --bg 8000`)

- [ ] **Step 1:** `docker build -t notion-dash .` succeeds (skip if Docker unavailable locally; note it in the report).
- [ ] **Step 2:** `docker run --rm -e NOTION_TOKEN=x ... notion-dash python -c "import app.main"` exits 0.
- [ ] **Step 3: Commit** `feat: Dockerfile, compose and deploy docs`.

### Task 11: Deploy to proxmox1 (Claude, not Codex)

- [ ] Download Debian 13 template; create unprivileged LXC per spec (`nesting=1,keyctl=1`, tun passthrough), install Docker + Tailscale + git.
- [ ] Clone repo to `/opt/notion-dash/app`; create `/opt/notion-dash/.env` (mode 600) with IDs and token placeholder; owner pastes token.
- [ ] `tailscale up --hostname notion-dash` (owner approves); `tailscale serve --bg 8000`.
- [ ] `docker compose up -d --build`; `/healthz` reports ok with no missing databases.
- [ ] Manual smoke test from the spec's Testing section; undo test edits.
- [ ] Publish repo: secret scan (`git log -p | grep -iE "secret_|ntn_|tailfe|[0-9a-f]{32}"` reviewed), `gh repo create harisbashir/notion-dash --public --source . --push`.
