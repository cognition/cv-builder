# Database-primary CV documents with pinned history

**Date:** 2026-08-05  
**Repo:** `cv-builder`  
**Status:** Draft for review  
**Depends on:** Existing SQLite snippet library (`SnippetDatabase`), Master CV
editor APIs, compose + PDF render pipelines

## Problem

Today the Master CV (and composed variants) are file-backed:

- Live edits write `cv/web/data.yaml` directly.
- Undo/redo lives in `data/edit-history.json`.
- Compose always writes `cv/variants/<name>/data.yaml` (+ optional PDF).
- SQLite holds snippets, drafts, questions, and import metadata — not the
  master document itself.

That keeps YAML as the source of truth even though the product already has a
database for library content. Users who edit in the browser should mutate the
database; YAML, Markdown, and PDF should appear only when explicitly exported.

## Goals

- Make SQLite the **primary store** for the Master CV and composed variants.
- Keep the existing YAML document **shape** (person, skills, bio, experience,
  education, panels) as a stored text blob so path-based editor APIs keep
  working.
- Replace file-based undo with a **transitory `cv_history` table** bound to
  the working document.
- Support **pins**: freeze content + undo/redo stacks to a labelled snapshot;
  editing continues on the working copy.
- Export **YAML, Markdown, or PDF only on explicit request**; normal save /
  structure / compose must not write those artefacts as the live SoT.
- One-time bootstrap: seed `cv_documents` from existing `data.yaml` (and
  existing variant folders if present) when the DB has no master row.
- Preserve the hybrid model: snippet tables remain for library / match /
  compose selection; documents are separate.

## Non-goals (this pass)

- Normalising CV sections into relational tables (person rows, job rows…).
- Multi-user concurrency / locking beyond SQLite defaults.
- Compare-import mode, multi-layout packs, or template packs.
- Dropping the YAML schema or inventing a new editor wire format.
- Git-style branching of documents (pins are snapshots, not branches).
- Making `content/**/*.md` the master SoT (seed direction stays
  content → snippets).

## Decision summary (confirmed with user)

| Decision | Choice |
| --- | --- |
| Source of truth | Database primary; files only on export |
| Document storage | Hybrid: YAML/text blob in `cv_documents` + existing snippet tables |
| Variant storage | Also DB documents; filesystem only on export |
| Export formats | YAML, Markdown, and PDF when asked |
| History | Transitory `cv_history` table, overwritten often, depth 50 |
| Versioning | One working document + pins that freeze content + undo stacks |
| Architecture | Approach A: `cv_documents` + `cv_history` + `cv_pins` |

## Approach

Add three tables to the existing SQLite schema. Move Master and variant
document I/O behind a small document service. Retarget editor, compose,
import-master, undo/redo, and export to that service. Delete or stop using
`data/edit-history.json` for the live path once history is DB-backed.

```text
┌─────────────────────────────────────────────────────────────┐
│ SQLite                                                      │
│  snippets / drafts / questions  (unchanged library)         │
│  cv_documents  ← Master + variants (content_yaml blob)      │
│  cv_history    ← working undo/redo stacks (transitory)      │
│  cv_pins       ← frozen content + stacks                    │
└─────────────────────────────────────────────────────────────┘
        ▲                              │
        │ save / structure / undo      │ explicit export
        │ compose / import-master      ▼
   Web editor / APIs             YAML / Markdown / PDF files
```

## Schema

### `cv_documents`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER PK | |
| `kind` | TEXT NOT NULL | `'master'` or `'variant'` |
| `name` | TEXT | NULL for master; unique among variants |
| `content_yaml` | TEXT NOT NULL | Full YAML document text |
| `updated_at` | TEXT NOT NULL | UTC ISO-8601 |

Constraints (enforce in SQL where practical; otherwise in the document service):

- Exactly zero or one row with `kind = 'master'` (application check on insert;
  SQLite `UNIQUE(kind, name)` does not reliably limit NULL `name`).
- Variants require non-empty `name`; unique among `kind = 'variant'`.

### `cv_history`

Transitory working undo/redo for a single document. One row per document
(upsert / replace). Overwritten on every successful mutate.

| Column | Type | Notes |
| --- | --- | --- |
| `document_id` | INTEGER PK/FK | References `cv_documents(id)` ON DELETE CASCADE |
| `undo_json` | TEXT NOT NULL | JSON array of `{label, text}` entries |
| `redo_json` | TEXT NOT NULL | Same shape |
| `updated_at` | TEXT NOT NULL | |

Stack depth: **50** (same as today's `EditHistory.max_entries`).

Corrupt JSON → reset stacks to empty, keep document content, log a warning.

### `cv_pins`

Durable snapshots of content **and** history stacks. Pinning does not stop
editing; the working document continues independently.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | INTEGER PK | |
| `document_id` | INTEGER NOT NULL FK | Working document this pin belongs to |
| `label` | TEXT NOT NULL | User-facing name |
| `content_yaml` | TEXT NOT NULL | Frozen document text |
| `undo_json` | TEXT NOT NULL | Frozen undo stack |
| `redo_json` | TEXT NOT NULL | Frozen redo stack |
| `created_at` | TEXT NOT NULL | |

Restore (always):

1. Auto-pin the current working state with label `before-restore:<pin-id>`
   so restore is reversible.
2. Overwrite `cv_documents.content_yaml` with the pin’s content.
3. Replace `cv_history` stacks with the pin’s stacks.

## Data flow

### Bootstrap / migrate

On ensure-schema / first editor load / CLI migrate helpers:

1. If no `kind=master` row and `cv/web/data.yaml` exists → insert master from
   that file.
2. For each `cv/variants/<name>/data.yaml` without a matching variant
   document → insert that variant.
3. If `data/edit-history.json` exists and master has empty history → seed
   `cv_history` for master once, then stop reading that file for live use.

After bootstrap, live paths must not treat `cv/web/data.yaml` as SoT.

### Editor mutate path

`POST /api/save`, `POST /api/structure`, and related Master/variant edits:

1. Read current `content_yaml` from `cv_documents`.
2. Push pre-change snapshot onto undo (clear redo) via `cv_history`.
3. Apply path edits / structure ops in memory (existing helpers).
4. Write new `content_yaml` + upsert history.
5. Do **not** write YAML/MD/PDF files.

Undo / redo restore document text from stacks and update both tables.

### Compose

`CvComposer` reads master person (and empty shells if needed) from the master
document blob. Selected snippets still come from the library tables. Output
is an upsert of a `kind=variant` document. No automatic
`cv/variants/<name>/data.yaml` write.

### Import master mode

`mode=master` confirm auto-pins the current master (`label` like
`before-import:<token>`) then patches the master document in the DB.
File backups under `data/backups/` are no longer required for this path.
Library snippet upserts stay as today.

### Export (explicit only)

New or extended export API accepts `format` in `{yaml, markdown, pdf}` and a
document identity (master or variant name):

| Format | Behaviour |
| --- | --- |
| `yaml` | Write `content_yaml` to the requested/default path |
| `markdown` | Render structured Markdown from the parsed document |
| `pdf` | Existing Jinja + headless Chrome path; content loaded from DB. Temp HTML is fine; committed YAML on disk is not required |

Save & Preview may generate a PDF for the iframe without promoting YAML to
SoT. Preview artefacts under `cv/current/` remain acceptable as disposable
render output if needed; they must not replace `cv_documents`.

### Seed

`SnippetImporter` / `POST /api/seed` continues to upsert library rows from
`content/**/*.md`. Master sections for seed should prefer the master
document blob over the filesystem file when both could apply.

## API surface (target)

Document CRUD / read (existing endpoints reimplemented against DB where
possible):

- Master load/save/structure/history — same routes, DB backing.
- Variants list/get — prefer DB documents; folder listing becomes export-
  oriented or mirrors DB.

History / pins:

- `GET /api/history` — can_undo / can_redo depths from `cv_history`.
- `POST /api/undo`, `POST /api/redo` — DB stacks.
- `GET /api/pins?document=master` — list pins.
- `POST /api/pins` — `{document, label}` → create pin from current working
  state.
- `POST /api/pins/<id>/restore` — restore pin (always auto-pins previous).
- `DELETE /api/pins/<id>` — remove pin.

Export:

- `POST /api/export` body extends with `format: yaml|markdown|pdf` and
  optional `document` / `name` / `path`. Default for Master Save & Preview
  remains PDF behaviour without writing live YAML SoT.

## Error handling

| Situation | Behaviour |
| --- | --- |
| No master document and no bootstrap file | Clear API error instructing seed/migrate |
| Corrupt history JSON | Empty stacks; keep document; warn in logs |
| Pin restore missing id | 404 |
| Export write failure | Leave DB unchanged; clean partial output files |
| Master import cannot create safety pin | Abort before mutating master content |

## Testing

Update existing tests that assert against `cvweb.load_data()` / the repo YAML
file so they assert against `cv_documents` (and use temp DB fixtures).

Add coverage for:

- Bootstrap migrate from fixture YAML → master row; subsequent edits do not
  change the fixture file unless export is called.
- Save / structure / undo / redo mutates DB content and `cv_history` only.
- Pin → edit → restore restores both content and stacks.
- Compose creates/updates a variant document without writing YAML unless
  export is requested.
- Export yaml / markdown / pdf produces the expected artefact.
- Master import mode updates the DB master document and library snippets.

## Migration notes for callers

- MCP compose / reseed tools: read/write documents via DB.
- `scripts/generate-cv-web.py`: load from DB (or require export first —
  prefer load-from-DB for CLI PDF generation).
- README / operator docs: document DB as SoT and export commands/UI.

## Version impact

This is a feature-level change. Bump the application feature version when
implementation lands (per project versioning rules).

## Open follow-ups (out of scope)

- UI chrome for listing / labelling / restoring pins.
- Whether disposable PDF preview should stay under `cv/current/` or become
  a streamed response only.
- Retiring committed sample `cv/web/data.yaml` from the repo in favour of a
  seed fixture used only for bootstrap/tests.
