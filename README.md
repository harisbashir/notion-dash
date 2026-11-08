# notion-dash

A private, phone-friendly dashboard for Notion projects, tasks, ideas and notes.
Notion remains the source of truth.

For local development, install Python 3.12 and uv, run `uv sync --locked`,
copy `.env.example` to `.env` and fill in your settings. Keep tokens private.
Run `uv run uvicorn app.main:create_app --factory --env-file .env --reload`.

Checks: `uv run pytest -q`, `uv run ruff check .`,
`uv run ruff format --check .`.

[Deployment](#deploy) instructions will be added in Task 10.
