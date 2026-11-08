# notion-dash visual design (v3)

v3 replaces the v2 look (by Codex) after an Apple HIG review. Same features, fewer pixels per
idea, and familiar iOS patterns so nothing needs explaining: large titles, inset grouped
lists, a floating tab bar, grouped forms with the label on the left and the value on the right.

## Idea

The one bold moment is the Today headline: a dateline in marigold, then "14 things are
waiting on you." in a large rounded face. Everything else is quiet and lets titles do the work.
Marigold is spent only on the checked circle, primary buttons, links and the selected tab.

## Tokens

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F2F4F3` | `#0B1214` | grouped background |
| `--surface` | `#FFFFFF` | `#172224` | lists, cards |
| `--ink` | `#13201F` | `#E8EFED` | titles, body |
| `--muted` | `#5E6E6B` (5.4:1 on white) | `#9AAAA6` (6.7:1) | meta, counts |
| `--accent` | `#E8A317` | same | fills; ink tick on it 7.7:1 |
| `--accent-ink` | `#8F6100` (5.4:1) | `#F2B53A` (8.9:1) | accent text |
| `--danger` | `#C4331F` (5.5:1) | `#E8705E` (5.4:1) | overdue, errors, badge |

Type: system UI (SF Pro on Apple devices) for everything; `ui-rounded` (SF Pro Rounded) for
large titles, the headline and section headers. Sizes follow iOS: large title 34/41 bold,
section header 20/25 bold, row title 17/22, meta 15/20, tab label 11. No custom web font.

## Components

- **Rows**: 24px round checkbox inside a 44px target; title; one meta line with at most two
  facts (project, due, owner when not you, status when In progress or Waiting). Hairline
  separators inset to where the text starts. Rows that drill in end in a chevron.
- **Show N more**: after 3 rows on Today; when open it moves to the end and reads "Show less".
- **Filters**: capsule chips (scroll sideways on phone); Notes uses a two-part segmented
  control; the project filter is a capsule select.
- **Editors**: expand in place; grouped fields, Cancel and a marigold Save; "Open in Notion" last.
- **Project and note pages**: back link, large title, capsule selects that carry their label
  ("Status Active") and save on change.
- **Tab bar**: floating capsule with a translucent material over a scroll-edge fade; solid when
  reduced transparency or increased contrast is on. At 900px and wider it becomes a sidebar.

## Haris HQ

Personal Tasks, Notes and Projects (the `DS_HQ_*` settings) merge into the same screens:
projects appear under their Area chips (Personal, Learning), tasks and notes sit with the rest.
New tasks and notes go to Haris HQ when they have no project or a Haris HQ project, and to
Projects HQ otherwise. If the integration can't reach Haris HQ, the app runs without it.

## Motion

Only the saved flash (700ms) and disclosure chevrons. Both stop under reduced motion.
