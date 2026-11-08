# notion-dash visual design (v2)

v1 showed too much: every row carried six or seven meta items plus a link, controls sat above
content on every screen, and Today was one flat list of 18 rows. v2 keeps every feature but
shows less at once (progressive disclosure), and borrows familiar iOS patterns: inset grouped
lists, a Reminders-style round checkbox on the left, an icon tab bar.

## Idea

One signature: the Today headline sentence ("18 things are waiting on you."). Everything else
is quiet, familiar, and lets the titles do the work.

## Colour

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F1F4F3` | `#0E1A1C` | page (grouped background) |
| `--surface` | `#FFFFFF` | `#18282B` | list sections, sheets |
| `--ink` | `#14302F` | `#E6EEEB` | all titles and body text |
| `--muted` | `#566B68` (5.6:1 on surface, 5.2:1 on bg) | `#93A9A4` | meta line, section headers |
| `--line` | `#E1E7E5` | `#26393C` | inset separators |
| `--accent` | `#B97F0B` (3.3:1 on white; marigold, darkened for contrast) | `#F0B43A` | checked circle, active tab, focus ring, links in sheets |
| `--danger` | `#B5382B` | `#E2675A` | overdue text, errors, High priority dot |
| owner dots | Claude `#6A5ACD`, Codex `#2F8F6F`, Client `#3576C4`, other `#7A807D` (dark: lighter variants from v1) | | 8px dot before the owner name |

Titles always use `--ink`; never grey a title to show low priority.

## Type

Atkinson Hyperlegible Next (vendored). Scale (rem): 0.8125 meta, 1.0625 row title (17px,
weight 500), 0.875 section header (weight 600, `--muted`, sentence case), 1.75 page title (800),
2.125 Today headline (800, line-height 1.1). Body 1rem/1.5.

## Rows (to-dos, ideas, notes)

```
╭──────────────────────────────────────╮
│ ○  Raise Brevo daily limit            │   title: 1 or 2 lines, then clamp
│    Sairon CRM · Due Friday            │   meta: max 2 facts
│──────────────────────────────────────│   separator inset to text start
```

- Round checkbox on the left: 24px visible circle (2px `--muted` border), 44px hit area;
  checked = filled `--accent` with a white tick, title gets `--muted` + strikethrough.
- Meta line, max two facts, joined by spaces only (no separator glyphs): in priority order
  project name, due label (red when overdue), owner (dot + name) only when owner is not you,
  status only when it is "In progress" or "Waiting". Never show "AI to-do"/"My task", "To do",
  or the owner's own name. On a project page drop the project name.
- High priority: 6px `--danger` dot before the title plus visually hidden text "High priority".
- Tap the row title → inline editor expands in place (as now). "Open in Notion" lives only in
  the editor/detail, as a quiet link at the bottom.
- Row padding 12px 16px; min height 52px.

## Sections

- Inset grouped lists: `--surface`, 12px radius, no shadow, 16px side margin on phone.
- Section header above each group: `--muted` 0.875rem 600, with the count in the same style
  ("Questions 2"). No other headings inside groups.
- Groups longer than 3 rows (Today only) show 3 and a "Show N more" row (a `<details>`-based
  disclosure; no JS needed).

## Screens

**Today**: headline; then groups, each shown only if non-empty, an item appears once only:
1. "Questions": AI to-dos for you with Phase = Question.
2. "Due soon": anything overdue or due within 7 days (yours or AI's) not already shown.
3. One group per project (project name as header), for the remaining open items that are
   yours (AI to-dos where Who = you, and My Tasks), ordered by number of items descending;
   "No project" last.
4. A quiet final row: "3 new ideas" linking to Ideas (hidden when 0).
No search box and no filters on Today.

**To-dos**: page title, then a horizontal chip row (scrollable on phone): `All` `You`
`Claude` `Codex` `Done`, single-select, links (no form, no Apply). Project filter as a compact
native `<select>` in the same row that submits on change (tiny JS). Search field below chips,
only here and on Notes, placeholder "Search to-dos". Quick add moves to the bottom of the list
as a row "＋ Add a task" that expands into the field.

**Projects**: chips for Area (`All` `Work` `Personal` `Learning`). Status groups as inset
sections ("Active 3"); each project row: name (17px 600), two-line clamped summary in `--muted`,
then "4 open" on the right of the name. Sub-projects: indented rows (24px) inside the same
section with a small "↳"-free indent, no nested boxes. Live/Done collapsed as before.

**Project page**: title; status and priority as two compact native selects in one row that
save on change; summary as a quiet paragraph with an "Edit" link that reveals the textarea;
links row (Code, Live site, Open in Notion) as small text links. Then sections To-dos, Ideas,
Decisions & notes, My notes using the same rows.

**Ideas**: chips `New` `Planned` `Maybe later` `Closed`; rows show title + project; tapping
expands details, status select and project select. Quick add as on To-dos ("＋ Add an idea").

**Notes**: segmented control (two equal buttons) `Mine` | `AI`; chip row of Types (scrollable);
search field; rows show title + type + project. "＋ New note" as the last row.

## Tab bar and sidebar

Five tabs with inline SVG line icons (24px, 1.75px stroke, currentColor) above 0.6875rem labels:
Today (sun), Projects (stacked squares), To-dos (checkmark circle), Ideas (lightbulb),
Notes (page). Active: `--ink` + accent icon; inactive `--muted`. Today shows a small badge with
the Questions count when > 0 (`--danger` background, white text, min 18px). Tab bar background
`--surface` with a top hairline `--line`, respects safe-area inset. On ≥768px it becomes a left
sidebar with the same icons beside labels.

## Motion

Only: the row saved flash (accent background fade 300ms) and `<details>` disclosure. Respect
`prefers-reduced-motion`.

## Copy

Sentence case everywhere. Buttons say what they do: "Save", "Cancel", "Add task", "Add idea",
"Add note", "Show 4 more". Empty states: Today "Nothing is waiting on you." with no further
sections; lists "No to-dos here." + the add row. Errors as in v1.
