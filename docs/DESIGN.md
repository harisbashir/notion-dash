# notion-dash visual design

## Idea

This is a hand-off board between one person and the AI tools working for him. The question
every screen answers is "whose move is it?". So the one bold element is **ownership colour**:
every to-do row carries a 4px left edge in the colour of its Who (Haris, Claude, Codex,
Client, Accountant), and the Today screen opens with a large plain sentence saying how
many things are waiting on the owner. Everything else stays quiet: lists, not card grids;
few borders; no shadows except on the open editor sheet.

## Colour

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#E9EFEC` (pale sage-grey) | `#0F1D20` | page |
| `--surface` | `#FFFFFF` | `#172A2E` | lists, editor sheet |
| `--ink` | `#14302F` (deep teal ink) | `#E2ECE8` | text |
| `--muted` | `#5B716E` | `#8FA6A1` | secondary text, meta |
| `--line` | `#D3DDD9` | `#25403F` | row separators |
| `--you` | `#E3A21A` (marigold) | `#F0B43A` | Haris / "needs you", focus ring |
| `--claude` | `#6A5ACD` | `#9C8FF0` | Who = Claude |
| `--codex` | `#2F8F6F` | `#4CC39A` | Who = Codex |
| `--client` | `#3576C4` | `#6FA6E8` | Who = Client |
| `--other` | `#8A8F8C` | `#7E8A87` | Accountant, unknown, My Tasks rows use `--you` |
| `--danger` | `#B5382B` | `#E2675A` | overdue, errors |

Status/option colours from Notion are not reproduced; statuses render as text, not
coloured pills. Priority High = small filled `--danger` dot before the title; Normal/Medium
none; Low/Optional title in `--muted`.

## Type

One family: **Atkinson Hyperlegible Next** (OFL), already vendored as one variable woff2
(Latin subset, weights 200–800) at `app/static/fonts/atkinson-hyperlegible-next-latin.woff2`;
use weights 400, 600, 800. Fallback `system-ui, sans-serif`. Icons are already in
`app/static/icons/` (192, 512, apple-touch-icon 180) and HTMX 2.0.11 at
`app/static/htmx.min.js`.

Scale (rem): 0.8125 meta, 1 body, 1.25 section heading (600), 1.75 page title (800),
2.5 Today headline (800, line-height 1.1, max 18ch). Body line-height 1.5. Sentence case
everywhere; no all-caps labels, no eyebrow labels, no middle-dot meta strings (separate
meta items with spacing), no arrow glyphs appended to links.

## Layout

```
Phone (<768px)                       Laptop (>=768px)
+---------------------------+        +--------+-------------------------------+
| 6 things are waiting      |        | Today  | 6 things are waiting on you.  |
| on you.                   |        | Proj.  |                               |
|                           |        | To-dos | Questions for you             |
| Questions for you         |        | Ideas  | |▌ Pick a payment provider    |
| ▌ Pick payment provider   |        | Notes  | |▌ ...                        |
|   Website · due Fri       |        |        | Due soon       My tasks       |
| Due soon                  |        |        | ...            ...            |
| ▌ ...                     |        |        |                               |
+---------------------------+        +--------+-------------------------------+
| Today Proj To-dos Ideas Notes |
+---------------------------+
```

- Content left-aligned, max width 72rem; lists max 46rem when single column.
- Rows: 12px vertical padding, full-width tap target, title on line 1, meta (project,
  due, phase) on line 2 in `--muted` 0.8125rem. Left edge = Who colour.
- Checkbox at the row's right edge, 28px square, rounded 6px, marigold when checked.
- Projects board: phone = status sections stacked; laptop = one column per open status,
  horizontally scrollable; Live/Done as collapsed `<details>` below.
- Editor: tap a row → it expands in place into a sheet (surface, 12px radius, one soft
  shadow) with native `<select>`, `<input type=date>`, `<textarea>`; buttons "Save" and
  "Cancel". On save the row collapses back and briefly flashes a marigold edge (300ms),
  the only animation; skip it under `prefers-reduced-motion`.
- Radius: 6px controls, 12px sheet; nothing else rounded.
- Bottom tab bar on phone respects `env(safe-area-inset-bottom)`; active tab in `--ink`
  with a 3px marigold top bar, others `--muted`.
- Focus: 3px `--you` outline, 2px offset, always visible on keyboard focus.

## Copy

- Today headline: "N things are waiting on you." / "Nothing is waiting on you." /
  "1 thing is waiting on you."
- Sections: "Questions for you", "Your tasks", "Due soon", "New ideas".
- Empty list: say what to do, e.g. "No open to-dos. Add one above."
- Quick add placeholders: "Add a task", "Add an idea".
- Errors: "Couldn't save to Notion. Your change wasn't saved." with a "Try again" button.
- Stale banner: "Showing data from 14:05. Notion isn't responding."
- Link to Notion: "Open in Notion".
