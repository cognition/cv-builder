# Multiple layouts × content sets

**Date:** 2026-08-03  
**Repo:** `cv-builder`  
**Status:** Draft for review  

## Problem

Today the editor has a single hard-wired visual pipeline (`cv/web/template.html.j2` + `style.css` + `data.yaml`). Users need to:

1. Switch between different visual layouts while editing.
2. Keep independent content forks (each with its own `data.yaml` copy).
3. Lock a layout onto each composed variant so re-render stays faithful.

## Goals

- Separate **layout packs** (HTML/CSS) from **content sets** (`data.yaml`).
- Mix-and-match: any content set can be viewed/exported through any layout.
- Creating a new content set **clones** the active content once; afterwards edits are independent.
- Creating a new layout **clones** the active layout’s HTML/CSS once as a starting point.
- Composed variants record which layout they used and freeze composed data.
- Ship three layouts in v1: `sidebar` (current design), `single-column`, `compact`.
- Undo/redo history keyed **per content set**.

## Non-goals (this pass)

- WYSIWYG / drag-drop template designer.
- Per-layout schema divergence (all layouts consume the same `data.yaml` shape; a layout may simply ignore unused sections such as side panels).
- Syncing or merging content sets after fork.
- Multi-user / auth.

## Questionnaire decisions

| Topic | Choice |
| --- | --- |
| Main unlock | Switch layouts in the editor **and** lock a layout onto each saved variant |
| Starter set | Plumbing + current sidebar + **two** more layouts |
| Content vs layout | Layout packs + **separate** content stores (mix-and-match) |
| New content | Clone current data once on create; switching thereafter is independent |
| Target repo | `cv-builder` |

## Data model

### Layout pack

Path: `cv/layouts/<layout_id>/`

| File | Purpose |
| --- | --- |
| `template.html.j2` | Jinja2 document template (same data contract as today’s template) |
| `style.css` | Print/screen styles for that layout |
| `meta.yaml` | `{ id, name, description, created_at }` |

Layout IDs are filesystem-safe names (`sidebar`, `single-column`, `compact`, …).

### Content set

Path: `cv/content-sets/<content_id>/`

| File | Purpose |
| --- | --- |
| `data.yaml` | Full CV structured content (same schema as today’s file) |
| `meta.yaml` | `{ id, name, description, created_at, cloned_from? }` |

### Active pair

Path: `data/active.json`

```json
{
  "layout_id": "sidebar",
  "content_id": "default"
}
```

The editor, Save & Preview, structure ops, and history all resolve through this pair.

### Undo history

Path: `data/history/<content_id>.json`  
(stacks of YAML text snapshots; same semantics as today’s `EditHistory`, but one file per content set).

### Composed variants

Path: `cv/variants/<name>/`

| File | Purpose |
| --- | --- |
| `data.yaml` | Frozen composed document (as today) |
| `meta.yaml` | `{ layout_id, content_id?, created_at, … }` — **layout_id required** for re-render |
| `<name>.pdf` | Rendered PDF using the locked layout |

Re-render always uses `meta.yaml.layout_id` + the frozen `data.yaml` (not the live active pair).

## Directory migration

| Before | After |
| --- | --- |
| `cv/web/template.html.j2` | `cv/layouts/sidebar/template.html.j2` |
| `cv/web/style.css` | `cv/layouts/sidebar/style.css` |
| `cv/web/data.yaml` | `cv/content-sets/default/data.yaml` |
| (none) | `cv/layouts/single-column/…`, `cv/layouts/compact/…` |
| (none) | `data/active.json` |

`cv/web/` remains the **shared UI chrome** only:

- `editor.js`, `builder.html` / `builder.js` / `builder.css`
- `variants.html` / `variants.js`
- No CV document template/CSS or `data.yaml` living there after migration

Rendered edit HTML continues to be served at `/cv/web/edit`. Stylesheet and relative asset URLs for the CV body resolve from the active layout pack (via rewrite in `render_html`, a dedicated asset route, or inject of the active layout’s CSS).

## Seed layouts (v1)

All three layouts share the same data contract (`person`, `skills`, `bio`, `experience`, `education`, `panels`, …).

1. **`sidebar`** — today’s full-height navy sidebar + flowing experience (moved as-is).
2. **`single-column`** — no sidebar; identity/contact/skills flow at the top of a single column; experience continues below. Side `panels` render as ordinary titled sections after skills.
3. **`compact`** — denser type scale, tighter spacing, sidebar optional or thinner; prioritises fitting more on fewer pages.

Exact visual polish of the two new layouts is implementation detail; they must be distinctly different from `sidebar` and produce a valid Letter PDF from the default content set.

## Runtime behaviour

### Switching layout

1. Client `PUT /api/active` with new `layout_id` (content unchanged).
2. Server validates the layout exists, writes `data/active.json`.
3. Editor reloads; render uses the new template/CSS with the same content set.

### Switching content set

1. Client `PUT /api/active` with new `content_id`.
2. Server validates; writes `active.json`.
3. Editor reloads; undo buttons reflect that content set’s history file.

### Creating a content set

1. `POST /api/content-sets` with `{ "id"?: string, "name"?: string }`.
2. Server clones active content’s `data.yaml` into `cv/content-sets/<new_id>/`.
3. Optionally switches active `content_id` to the new set (recommended default: yes).

### Creating / duplicating a layout

1. `POST /api/layouts` with `{ "id"?: string, "name"?: string, "from"?: layout_id }`.
2. Server clones `from` (default: active layout) HTML/CSS into a new folder.
3. Does **not** clone content. Optionally switches active `layout_id`.

### Save / structure / history

- Resolve `DATA_FILE` from `active.content_id`.
- Resolve history path from `active.content_id`.
- Snapshot push / undo / redo unchanged in semantics.

### Export / PDF

- Resolve template + CSS from `active.layout_id` (editor preview) or `variant.meta.layout_id` (variant re-render).
- Write PDF under `cv/current/` for the live/active export (name can stay as today or become configurable later — out of scope beyond “it renders”).

### Compose (builder)

- Compose still builds a frozen `data.yaml` from snippet selections.
- Writes `meta.yaml` including `layout_id` = active layout (or an optional layout picker on the builder form).
- PDF generation uses that locked layout.

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/layouts` | List layout packs |
| `POST` | `/api/layouts` | Clone/create a layout pack |
| `GET` | `/api/content-sets` | List content sets |
| `POST` | `/api/content-sets` | Clone active content into a new set |
| `DELETE` | `/api/content-sets/<id>` | Delete a content set (refuse if active; refuse deleting last set) |
| `GET` | `/api/active` | Current `{ layout_id, content_id }` |
| `PUT` | `/api/active` | Switch active layout and/or content |
| (existing) | `/api/save`, `/api/structure`, `/api/undo`, `/api/redo`, `/api/history` | Operate on active content set |
| (existing) | `/api/export`, `/api/preview.pdf` | Render with active layout |
| (existing) | `/api/compose`, `/api/variants…` | Persist/use locked `layout_id` |

## UI changes

### Editor toolbar

- **Layout** `<select>` + “Duplicate layout…”
- **Content** `<select>` + “New content set…”
- Existing Undo / Redo / Save & Preview / page guides unchanged in role

### Builder

- Optional layout selector (default: active layout) shown at compose time
- Composed variant list/detail shows locked layout name

### Variants page

- Display `layout_id` per variant
- Re-render uses locked layout

## Implementation sketch (modules)

- `scripts/cvweb.py`
  - `list_layouts`, `list_content_sets`, `get_active`, `set_active`
  - `clone_layout`, `clone_content_set`
  - `resolve_layout_dir`, `resolve_data_file`
  - `render_html` / `export_pdf` take optional `layout_id` / `content_id`
  - `EditHistory` path derived from content id
- `scripts/serve-editor.py` — new routes; point existing mutators at resolved paths
- `src/cvbuilder/composer.py` — write `meta.yaml` with `layout_id`
- One-shot migration helper (or first-boot in entrypoint) if old paths still present
- Tests: active switch, content clone isolation, layout clone, variant re-render uses locked layout, history isolation per content set

## Success criteria

1. Switch layout without mutating the content set’s `data.yaml`.
2. Create a second content set by clone; edits in A do not appear in B.
3. Compose a variant locked to a non-active layout; re-render still uses the locked layout.
4. Default boot works with `sidebar` × `default` after migration.
5. Automated tests cover the above.

## Open questions deferred to implementation

- Exact CSS/HTML for `single-column` and `compact` (must be distinct; not pixel-perfect brand work).
- Whether builder layout picker is required in v1 or “use active” is enough (spec allows either; prefer including the picker if cheap).
- PDF output filename under `cv/current/` when multiple layouts exist (single shared name is acceptable for v1).
