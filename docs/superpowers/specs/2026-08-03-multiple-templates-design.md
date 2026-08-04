# Multiple templates (folder-per-template)

**Date:** 2026-08-03 (revised 2026-08-04)  
**Repo:** `cv-builder`  
**Status:** Draft for review  

## Problem

Today the editor has a single hard-wired visual pipeline (`cv/web/template.html.j2` + `style.css` + `data.yaml`). Users need to:

1. Maintain several complete templates (layout **and** content together).
2. Switch between them in the editor.
3. Lock a template onto each composed variant so re-render stays faithful.

## Goals

- One folder per template owns HTML, CSS, **and** its own `data.yaml` copy.
- Creating a new template **clones** the active template folder once (layout + data); afterwards edits are independent.
- Switching templates opens that template’s own data (no copy, no prompt).
- Composed variants record which template they used and freeze composed data.
- Ship three templates in v1: `sidebar` (current design), `single-column`, `compact`.
- Undo/redo history keyed **per template**.

## Non-goals (this pass)

- Mix-and-match of layout packs with separate content sets (explicitly rejected; see Questionnaire).
- WYSIWYG / drag-drop template designer.
- Per-template schema divergence (all templates consume the same `data.yaml` shape; a template may simply ignore unused sections such as side panels).
- Syncing or merging templates after fork.
- Multi-user / auth.

## Questionnaire decisions

| Topic | Choice |
| --- | --- |
| Main unlock | Switch templates in the editor **and** lock a template onto each saved variant |
| Starter set | Plumbing + current sidebar + **two** more templates |
| Content vs layout | **Pure Approach A:** each template folder owns its own `data.yaml` (no mix-and-match) |
| New template | Clone current template (layout + data) once on create; switching thereafter is independent |
| Target repo | `cv-builder` |

## Data model

### Template pack

Path: `cv/templates/<template_id>/`

| File | Purpose |
| --- | --- |
| `template.html.j2` | Jinja2 document template (same data contract as today’s template) |
| `style.css` | Print/screen styles for that template |
| `data.yaml` | Full CV structured content for this template only |
| `meta.yaml` | `{ id, name, description, created_at, cloned_from? }` |

Template IDs are filesystem-safe names (`sidebar`, `single-column`, `compact`, …).

### Active template

Path: `data/active.json`

```json
{
  "template_id": "sidebar"
}
```

The editor, Save & Preview, structure ops, and history all resolve through this id.

### Undo history

Path: `data/history/<template_id>.json`  
(stacks of YAML text snapshots; same semantics as today’s `EditHistory`, but one file per template).

### Composed variants

Path: `cv/variants/<name>/`

| File | Purpose |
| --- | --- |
| `data.yaml` | Frozen composed document (as today) |
| `meta.yaml` | `{ template_id, created_at, … }` — **template_id required** for re-render |
| `<name>.pdf` | Rendered PDF using the locked template’s HTML/CSS |

Re-render always uses `meta.yaml.template_id`’s layout files + the frozen `data.yaml` (not the live active template’s live data).

## Directory migration

| Before | After |
| --- | --- |
| `cv/web/template.html.j2` | `cv/templates/sidebar/template.html.j2` |
| `cv/web/style.css` | `cv/templates/sidebar/style.css` |
| `cv/web/data.yaml` | `cv/templates/sidebar/data.yaml` |
| (none) | `cv/templates/single-column/…`, `cv/templates/compact/…` |
| (none) | `data/active.json` → `{ "template_id": "sidebar" }` |

`cv/web/` remains the **shared UI chrome** only:

- `editor.js`, `builder.html` / `builder.js` / `builder.css`
- `variants.html` / `variants.js`
- No CV document template/CSS or `data.yaml` living there after migration

Rendered edit HTML continues to be served at `/cv/web/edit`. Stylesheet and relative asset URLs for the CV body resolve from the active template pack (via rewrite in `render_html`, a dedicated asset route, or inject of the active template’s CSS).

## Seed templates (v1)

All three templates share the same data contract (`person`, `skills`, `bio`, `experience`, `education`, `panels`, …). Initial content for `single-column` and `compact` is cloned from `sidebar`’s `data.yaml` at seed time (then diverges independently if edited).

1. **`sidebar`** — today’s full-height navy sidebar + flowing experience (moved as-is).
2. **`single-column`** — no sidebar; identity/contact/skills flow at the top of a single column; experience continues below. Side `panels` render as ordinary titled sections after skills.
3. **`compact`** — denser type scale, tighter spacing, thinner or optional sidebar; prioritises fitting more on fewer pages.

Exact visual polish of the two new templates is implementation detail; they must be distinctly different from `sidebar` and produce a valid Letter PDF from their own `data.yaml`.

## Runtime behaviour

### Switching template

1. Client `PUT /api/active` with new `template_id`.
2. Server validates the template folder exists, writes `data/active.json`.
3. Editor reloads; render uses that folder’s template/CSS/`data.yaml`.
4. Undo buttons reflect that template’s history file.

### Creating / duplicating a template

1. `POST /api/templates` with `{ "id"?: string, "name"?: string, "from"?: template_id }`.
2. Server clones `from` (default: active template) — HTML, CSS, **and** `data.yaml` — into `cv/templates/<new_id>/`.
3. Writes `meta.yaml` with `cloned_from`.
4. Switches active `template_id` to the new id (default: yes).

### Deleting a template

1. `DELETE /api/templates/<id>`.
2. Refuse if it is the active template, or if it is the last remaining template.

### Save / structure / history

- Resolve `DATA_FILE` from `active.template_id` → `cv/templates/<id>/data.yaml`.
- Resolve history path from `active.template_id`.
- Snapshot push / undo / redo unchanged in semantics.

### Export / PDF

- Resolve template + CSS + data from `active.template_id` (editor preview).
- Variant re-render: locked `template_id`’s HTML/CSS + frozen variant `data.yaml`.
- Write PDF under `cv/current/` for the live/active export (single shared name is acceptable for v1).

### Compose (builder)

- Compose still builds a frozen `data.yaml` from snippet selections.
- Writes `meta.yaml` including `template_id` = active template (or an optional template picker on the builder form).
- PDF generation uses that locked template’s HTML/CSS.

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/templates` | List template packs |
| `POST` | `/api/templates` | Clone/create a template pack (layout + data) |
| `DELETE` | `/api/templates/<id>` | Delete a template (refuse if active or last) |
| `GET` | `/api/active` | Current `{ template_id }` |
| `PUT` | `/api/active` | Switch active template |
| (existing) | `/api/save`, `/api/structure`, `/api/undo`, `/api/redo`, `/api/history` | Operate on active template’s `data.yaml` |
| (existing) | `/api/export`, `/api/preview.pdf` | Render with active template |
| (existing) | `/api/compose`, `/api/variants…` | Persist/use locked `template_id` |

## UI changes

### Editor toolbar

- **Template** `<select>` populated from `GET /api/templates`
- **Duplicate template…** — prompts for id/name, `POST /api/templates`, reload
- Existing Undo / Redo / Save & Preview / page guides unchanged in role

### Builder

- Optional template selector (default: active template) shown at compose time
- Composed variant list/detail shows locked template name

### Variants page

- Display `template_id` per variant
- Re-render uses locked template’s HTML/CSS + frozen data

## Implementation sketch (modules)

- `scripts/cvweb.py`
  - `list_templates`, `get_active`, `set_active`
  - `clone_template`, `delete_template`
  - `resolve_template_dir`, `resolve_data_file`
  - `render_html` / `export_pdf` take optional `template_id`
  - `EditHistory` path derived from template id
- `scripts/serve-editor.py` — new routes; point existing mutators at resolved paths
- `src/cvbuilder/composer.py` — write `meta.yaml` with `template_id`
- One-shot migration helper (or first-boot in entrypoint) if old paths still present
- Tests: active switch, clone isolation (edit A ≠ B), variant re-render uses locked template, history isolation per template

## Success criteria

1. Switch template loads that folder’s layout **and** its own `data.yaml`.
2. Create a second template by clone; edits in A do not appear in B (neither layout nor data).
3. Compose a variant locked to a non-active template; re-render still uses the locked template’s HTML/CSS.
4. Default boot works with `sidebar` after migration.
5. Automated tests cover the above.

## Open questions deferred to implementation

- Exact CSS/HTML for `single-column` and `compact` (must be distinct; not pixel-perfect brand work).
- Whether builder template picker is required in v1 or “use active” is enough (spec allows either; prefer including the picker if cheap).
- PDF output filename under `cv/current/` when multiple templates exist (single shared name is acceptable for v1).
