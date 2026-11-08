# notion-dash: design

Date: 2026-11-08
Status: Draft, awaiting review

## Purpose

A fast, phone-and-laptop friendly web dashboard for the Notion "Projects HQ" workspace,
so the owner rarely needs Notion's own UI. Notion stays the source of truth: Claude,
Codex and other AI tools keep reading and writing Notion directly, and notion-dash shows
their changes within about a minute. Changes made in notion-dash are written straight to
Notion.

Single user. Reached only over a private Tailscale network. Public GitHub repo, so no
secrets, database IDs or hostnames are committed.

## Success criteria

- One URL works on phone and laptop and can be installed to the phone home screen (PWA).
- The Today screen shows everything waiting on the owner without extra taps.
- Common edits (tick a to-do, change a status, add an idea or note) take one or two taps
  and appear in Notion immediately.
- Edits by AI tools in Notion appear in the dashboard within ~60 seconds.
- An edit never overwrites fields the user did not touch.

## Data sources

All are Notion data sources shared with one internal integration. IDs come from config.

| Key | Database | Title field | Fields used |
|---|---|---|---|
| `projects` | Projects | Project | Status, Priority, Area, Summary, Code, Live site, Parent Project, Sub-projects |
| `ai_todos` | AI To-do | Task | Status, Who, Phase, Priority, Due, Notes, Project, Added by, Added |
| `my_tasks` | My Tasks | Name | Status, Priority, Due date, Notes, Project, List, Parent Task |
| `ideas` | Ideas | Idea | Status, Details, Project, Added by, Added |
| `ai_notes` | AI Decisions & Notes | Note | Type, Details, Date, Project, Added by |
| `my_notes` | My Notes | Name | Type, Tags, Project, Last edited; content is the page body |

Option values (statuses, priorities, types) are read from the data source schema at
startup, not hard-coded, so new options added in Notion appear automatically. Field
names are hard-coded in one mapping module (`app/schema.py`); if a field is renamed in
Notion, that module is the only place to change.

## Screens

Bottom tab bar on narrow screens, sidebar on wide screens.

1. **Today** (home)
   - Open AI To-dos where Who = Haris; items with Phase = Question pinned first.
   - Open My Tasks.
   - Anything overdue or due within 7 days, from both to-do databases.
   - Count of Ideas with Status = New, linking to Ideas.
2. **Projects**: grouped by Status in this order: Active, Before launch, Not started,
   On hold; Live and Done collapsed. Card: name, Area, Priority, Summary, open to-do
   count. Sub-projects nested under their parent. Filter by Area.
3. **Project page**: editable Status, Priority, Summary; Code and Live site links;
   sections for To-dos (AI + mine), Ideas, Decisions & notes, My notes for that project.
4. **To-dos**: AI To-do and My Tasks in one list with a source badge. Filters: Who,
   Project, Status (open by default; "show done" loads the 50 most recently edited Done
   items). Checkbox sets Status = Done. Tap opens an inline editor for Status, Priority,
   Due, Notes (and Project). Quick add creates a My Tasks row.
5. **Ideas**: New first, then Planned, Maybe later; Done/Dropped collapsed. Edit Status
   and Project. Quick add with Added by = Haris.
6. **Notes**: tabs for My Notes and AI Decisions & Notes, filter by Type and Project.
   - Detail view renders the page body (paragraphs, headings, bulleted/numbered lists,
     to-do checkboxes, quotes, callouts, code, dividers, links). Unsupported blocks show a
     placeholder with "Open in Notion".
   - New My Note: name, Type, Project, plain-text body (each line becomes a paragraph).
   - Append text to the end of an existing note.
   - Edit Type and Project on both databases.

Everywhere: "Open in Notion" link per item, client-side text filter per list, light/dark
theme following the system.

Out of scope for v1: drag-and-drop, full body editing, offline use, notifications,
deleting or archiving items, multiple users, auth beyond Tailscale.

## Architecture

```
Browser ──HTMX──► FastAPI + Jinja2 ──► NotionStore (cache) ──► NotionClient ──► Notion API
```

Python 3.12, FastAPI, Jinja2, HTMX (vendored, no CDN), httpx, pydantic-settings. No
JavaScript build step. Plain CSS designed per the frontend-design skill.

### Units

- `app/config.py`: settings from environment (`NOTION_TOKEN`, six data source IDs,
  `CACHE_TTL_SECONDS` default 30, `TIMEZONE`, `OWNER_NAME` used for "Who" and "Added by" values, default `Haris`).
- `app/notion/client.py`: thin async httpx wrapper over the Notion REST API
  (version header `2025-09-03`, data-source endpoints). Handles pagination, a global
  rate limiter (max 3 requests/second), and retry with `Retry-After` on 429 and on 5xx
  (3 attempts, backoff). Knows nothing about our databases.
- `app/schema.py`: maps Notion pages to typed models (`Project`, `Todo`, `Idea`,
  `Note`) and builds property payloads for updates. Pure functions; most unit tests live
  here.
- `app/store.py`: per-data-source cache with TTL. Reads go through the cache; any write
  updates the cached row in place from the API response and invalidates dependent views.
  Open items are fetched with filters (not Done); Done items only on demand.
- `app/blocks.py`: renders Notion blocks to safe HTML (escaped text, allow-listed link
  schemes) and converts plain text to paragraph blocks for append/create.
- `app/routes/`: one module per screen. Full page on normal requests; HTML fragments on
  HTMX requests.
- `app/templates/`, `app/static/`: templates, CSS, htmx.min.js, manifest, icons,
  minimal service worker (required for install; no offline caching).

### Writes and conflicts

Every update is a PATCH of only the properties the user changed, so AI edits to other
fields are never overwritten. If two edits touch the same field, the last write wins.
After a write the response fragment is rendered from Notion's returned page, so the
screen shows what Notion actually stored.

### Errors

- Notion unreachable or erroring on read: serve the last cached data with a banner
  "Showing data from HH:MM; Notion unavailable". No cache yet: an error page with retry.
- Write failure: the fragment shows an inline error and the original value; nothing is
  assumed saved.
- Missing integration access (404/403 on a data source): startup health check lists
  which databases are not shared with the integration; `/healthz` reports it.

### Security

- Notion token only on the server, in an env file with mode 600, outside the repo.
- Listens on 127.0.0.1 in the container host; exposed only via `tailscale serve` (HTTPS,
  tailnet only). Never Tailscale Funnel.
- Mutating requests require the `HX-Request` header and a same-origin `Origin`/`Referer`
  check, blocking cross-site form posts.
- All Notion content is HTML-escaped in templates; rendered blocks go through the
  allow-list renderer.

## Deployment (proxmox1)

- New unprivileged Debian 13 LXC on proxmox1 (`local-lvm`, 1 vCPU, 512 MB RAM, 4 GB
  disk), features `nesting=1,keyctl=1`, `/dev/net/tun` passed through for Tailscale.
- Docker + compose inside the LXC. `compose.yml` runs the app image built from the repo,
  bound to `127.0.0.1:8000`, `restart: unless-stopped`, env file at
  `/opt/notion-dash/.env`.
- Tailscale in the LXC as machine `notion-dash`; `tailscale serve --bg 8000` gives
  `https://notion-dash.<tailnet>.ts.net`. The owner approves the Tailscale login.
- Updates: `scripts/deploy.sh` on the LXC does `git pull && docker compose up -d --build`.
- The owner creates the Notion internal integration, connects it to Projects HQ, and
  pastes the token into the env file on the server; the token never passes through chat
  or the repo.

## Testing

- Unit tests (pytest): schema mapping and payload building against recorded sample page
  JSON (sanitised fixtures), block rendering including escaping, rate limiter and retry.
- Route tests: FastAPI TestClient with the Notion client mocked via respx; covers each
  screen, each edit, error banner and the Origin check.
- GitHub Actions: ruff + pytest on push.
- Manual smoke test after deploy against the real workspace: load every screen, tick and
  untick one to-do, add and then mark Dropped one test idea, append to a test note.

## Build process

Implementation plan written with the writing-plans skill. Codex implements tasks from
the plan; Claude reviews each change (correctness, security, matches spec) before it is
committed. Claude applies the frontend-design skill for the visual design. The repo is
published public on GitHub (`harisbashir/notion-dash`) after a secret scan.
