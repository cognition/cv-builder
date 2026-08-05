# Working Draft CV + Tailor drafts ↔ Versions

**Date:** 2026-08-05
**Repo:** `cv-builder`
**Status:** SUPERSEDED — see
[`2026-08-05-working-draft-cv-db-revision.md`](2026-08-05-working-draft-cv-db-revision.md)
(aligns with DB-primary documents; do not implement the filesystem
apply/snapshot paths below).

## Problem

Today:

- **Master CV** (`/cv/web/edit`, `cv/web/data.yaml`) is a separate editable
  document.
- **Tailor** ranks/selects snippets and **Save draft** only persists an
  ordered selection list in SQLite (`drafts` table).
- **Compose** writes a named folder under `cv/variants/` — it does not
  update the live Master document.
- There is no first-class path to **load a Version back into Tailor** as a
  starting point.

The product intent is: one live **Working Draft CV** that reflects chosen
Tailor content, with drafts and Versions as save/load points around it.

## Goals

1. Rename **Master CV** → **Working Draft CV** in the UI (nav, titles,
   crumbs, README). Keep route `/cv/web/edit` for compatibility.
2. Working Draft CV (`cv/web/data.yaml`) is the **active** document Tailor
   applies into.
3. Tailor **Save draft** stores the selection list **and** applies those
   snippets into Working Draft CV (backup `data.yaml` first; preserve
   `person` / contacts / unmapped keys).
4. Tailor **Load draft** restores the selection list **and** re-applies
   into Working Draft CV.
5. **Versions** remain named snapshots under `cv/variants/<name>/`.
6. **Load Version → draft**: hydrate Working Draft CV from that version’s
   `data.yaml`; recreate Tailor draft selections when composition
   metadata was recorded; otherwise open Tailor with a fresh draft after
   hydration.

## Non-goals

- Multi-template / layout packs (separate design).
- Changing snippet library schema.
- Auto-apply on every checkbox click (explicit Save / Load / Compose /
  Load Version only).
- Deleting the Versions page.

## Decisions (confirmed with user)

| Topic | Choice |
| --- | --- |
| Master vs Working Draft | **Rename** Master CV → Working Draft CV |
| Save draft | Store selections **and** apply into Working Draft CV |
| Versions | Keep named snapshots; loadable back into drafts |
| Load Version | Hydrate Working Draft CV **and** recreate Tailor selections when available |

## Data flow

```text
Tailor selections (ordered snippet_id + detail_level)
        │
        ├─ Save draft ──► SQLite drafts table
        │                      │
        │                      ▼
        └──────────────► Compose document (person from current Working Draft)
                               │
                               ├─► backup + write cv/web/data.yaml  (Working Draft CV)
                               ├─► regenerate cv/current/cv.pdf
                               └─► optional: write cv/variants/<name>/  (if version name set)

Load draft ──► restore selections + same apply path

Load Version ──► copy variants/<name>/data.yaml → Working Draft CV (+ backup)
              └─► if selections.json (or equivalent) present → open Tailor draft
                  else → Tailor with empty draft, Working Draft already hydrated
```

## Composition metadata on Versions

Today variants store `data.yaml` (+ PDF). To support “recreate draft from
Version”, each compose/apply that writes a snapshot also writes:

`cv/variants/<name>/selections.json`

```json
{
  "source": "tailor",
  "saved_at": "2026-08-05T12:00:00Z",
  "selections": [
    {"snippet_id": 12, "detail_level": "standard", "section": "experience"}
  ]
}
```

Older versions without this file can still **hydrate** Working Draft CV;
Tailor starts with an empty draft list.

## API

### Extend draft save

`PUT /api/drafts/<name>`

Request body gains optional:

```json
{
  "selections": [ ... ],
  "apply": true,
  "version_name": "ircc-it04"
}
```

When `apply` is true (Tailor Save draft sends `true`):

1. Persist draft selections (existing behaviour).
2. Backup `cv/web/data.yaml`.
3. Build composed document from selections via existing composer logic
   (person preserved from current Working Draft).
4. Write Working Draft `data.yaml` + regenerate preview PDF.
5. If `version_name` non-empty: also write `cv/variants/<version_name>/`
   including `selections.json`.

Response includes `applied`, `backup_path`, optional `version`.

### Load draft

`GET /api/drafts/<name>` unchanged for payload. Tailor client after load
calls apply (or save with `apply: true` and same selections) so Working
Draft CV matches.

### Load Version into draft

New:

`POST /api/variants/<name>/load-into-draft`

Behaviour:

1. Backup current Working Draft `data.yaml`.
2. Copy `variants/<name>/data.yaml` → `cv/web/data.yaml`.
3. Regenerate preview PDF.
4. If `selections.json` exists: upsert a draft named after the version
   (or `from-<name>`) and return `{ draft_name, selections, applied: true }`.
5. If missing: return `{ draft_name: null, selections: [], applied: true,
   warning: "no selections recorded for this version" }`.

### Compose button

Tailor’s primary compose becomes **Update Working Draft CV** (same apply
path as Save draft with `apply: true`). If a version name field is filled,
also snapshot.

## UI

- Shell nav: **Working Draft CV** → `/cv/web/edit` (`active` key can stay
  `master` internally or rename to `draft` carefully).
- Page header: “Working Draft CV” / “Edit your working draft”.
- Tailor:
  - Version name field → “Snapshot name (optional Versions entry)”.
  - Save draft → persists + applies + optional snapshot.
  - Load draft → restore list + apply.
  - Compose → Update Working Draft CV.
  - Versions sidebar or link: “Use as starting point” per version calls
    `load-into-draft`, then navigates to Tailor (and/or Working Draft CV).
- Versions page: add **Use as starting point** action.

## Preservation rules

When applying Tailor selections into Working Draft CV:

- Keep `person`, `panels`, and any unmapped top-level keys from the
  **current** Working Draft (same as composer’s base load today).
- Replace `bio`, `skills`, `experience`, `education` from selections
  (composer `_build_document` behaviour).

## Testing

- Pytest: apply-on-draft-save updates `data.yaml` and preserves person;
  writes `selections.json` on snapshot; load-into-draft hydrates +
  restores selections when file present.
- Behave: nav label Working Draft CV; Tailor save draft applies; Versions
  “starting point” endpoint/UI hook.

## Versioning

Bump feature component of `VERSION` when this ships.

## Success criteria

- UI no longer says “Master CV”; says Working Draft CV.
- Save draft on Tailor updates the document you edit at `/cv/web/edit`.
- Load draft re-syncs Working Draft CV.
- A Version can be loaded as a Tailor starting point (hydrate + draft
  when metadata exists).

## Open follow-ups

- Whether internal `active="master"` template key is renamed to `draft`.
- Exact draft naming when loading a Version (`from-<version>` vs overwrite).
- MCP tool names that still say “compose variant” — align docs in a
  follow-up.
