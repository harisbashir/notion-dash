# notion-dash

A private, phone-friendly dashboard for Notion projects, tasks, ideas and notes.
Notion remains the source of truth.

For local development, install Python 3.12 and uv, run `uv sync --locked`,
copy `.env.example` to `.env` and fill in your settings. Keep tokens private.
Run `uv run uvicorn app.main:create_app --factory --env-file .env --reload`.

Checks: `uv run pytest -q`, `uv run ruff check .`,
`uv run ruff format --check .`.

## Deploy

1. In Notion's integration settings, create an **internal integration** for
   your workspace. Enable read, insert and update content capabilities, then
   copy its integration token directly into your server's environment file.
2. Connect the integration to **each** database used by the dashboard: Projects,
   AI To-do, My Tasks, Ideas, AI Notes and My Notes. Open each database's page
   **••• → Connections** and select the integration.
3. For each database, open **••• → Manage data sources** and copy its **data
   source ID**. Fill the corresponding `DS_*` entry from `.env.example`; these
   are data source IDs, rather than database page IDs.
4. Copy `.env.example` to `/opt/notion-dash/.env` with mode `600`. Fill in
   `NOTION_TOKEN` and all six `DS_*` values, then review the timezone, owner name
   and cache TTL. Keep the token and this file out of version control.
5. Follow [the Proxmox LXC setup guide](scripts/lxc-setup.md) to install Docker
   and Tailscale, clone into `/opt/notion-dash/app`, and configure the env file.
   From that directory, run `docker compose up -d --build` and
   `tailscale serve --bg 8000`. The app listens on `127.0.0.1:8000` in the LXC;
   Tailscale Serve provides private HTTPS access.

For later updates, run `/opt/notion-dash/app/scripts/deploy.sh` inside the LXC.
