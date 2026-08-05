# Import mode: Create a new master CV

**Date:** 2026-08-04
**Repo:** `cv-builder`
**Status:** Draft for review
**Depends on:** B2 resume import (library mode) already shipped

## Problem

Track B2 shipped `/cv/web/import` with real upload → extract → review →
confirm into the **snippet library**. The wireframe also offers two other
modes:

- **Create a new master CV** — treat the uploaded resume as the primary
  document and materialise it as editable master content
  (`cv/web/data.yaml`).
- **Compare with my current CV** — review additions/conflicts before
  merging.

Today those two radios are visibly disabled ("Coming soon"). Users who
import a complete resume still have to rebuild the Master CV by hand from
library snippets.

## Goals

- Enable **Create a new master CV** end-to-end (UI + API + tests).
- Reuse the existing staged-upload / re-parse-on-confirm trust model from
  library import — never trust a client-sent extraction payload.
- Preserve identity/contact data already on the master CV (`person` block
  and other unmapped keys).
- Also populate the content library from the same extraction so Tailor /
  Questions keep working afterward.
- Fail safely: backup `data.yaml` before overwrite; do not mutate YAML if
  the backup cannot be written.

## Non-goals (this pass)

- **Compare with my current CV** (stays disabled; separate design).
- Parsing identity/contact fields (name, email, phone, profiles) from the
  resume header — extractor quality is not good enough for overwrite.
- URL / link-based resume fetch (wireframe mock only).
- Multi-layout packs / content-set pickers.
- Importing into a named `cv/variants/<name>/` folder instead of master
  (rejected for this pass — mode writes the live master).

## Decision summary (confirmed with user)

| Decision | Choice |
| --- | --- |
| Priority | Master-CV mode first; compare later |
| Overwrite policy | Replace `cv/web/data.yaml` after a timestamped backup |
| Library side-effect | Always also create library snippets for selected sections |
| `person` block | Preserve existing; do not overwrite from extraction |
| API shape | Extend `POST /api/imports/<token>/confirm` with `mode` |

## Approach

Extend the existing confirm route rather than adding a parallel master
endpoint. Staging, file-type checks, section pickers, candidate building,
and library upsert logic stay shared. `mode: "master"` adds the YAML
backup + content-section write on the same request.

```text
upload → stage + preview (unchanged)
         ↓
confirm(mode=library|master, sections={...})
         ↓
  re-parse staged file
         ↓
  upsert selected snippets ────────── always
         ↓
  if mode=master:
    backup data.yaml
    patch bio / experience / skills / education
    (optional) push editor history snapshot
```

## API

### `POST /api/imports/<token>/confirm`

Request body (JSON):

```json
{
  "mode": "library",
  "sections": {
    "profile": true,
    "experience": true,
    "skills": true,
    "education": true
  }
}
```

- `mode` — `"library"` (default if omitted) or `"master"`. Any other value
  → `400` with `{ "error": "..." }`.
- `sections` — unchanged from B2. Missing keys default to enabled.
  Disabled sections skip both library upserts and YAML field updates for
  that section.

Master response (additive fields; library response stays backward
compatible):

```json
{
  "id": 12,
  "filename": "resume.pdf",
  "snippet_count": 18,
  "mode": "master",
  "master_updated": true,
  "backup_path": "data/backups/data.yaml.20260804T163000Z.bak"
}
```

Library mode returns `mode: "library"` and `master_updated: false` (or
omits the master-only fields). Prefer including `mode` always for a
stable client contract.

Confirm continues to:

1. Resolve the staged file by token (404 if missing).
2. Re-read + `extract_text` + `parse_resume` server-side.
3. Upsert selected candidates into the snippet DB.
4. Move the staged file into permanent imports storage + create the
   `resume_imports` row (snippet_count = created).
5. If `mode == "master"`: mutate YAML using the fixed order below;
   otherwise skip YAML steps.

**Fixed confirm order (v1):**

1. Resolve + re-parse staged file.
2. If `mode == "master"`: write `data/backups/data.yaml.<UTC>Z.bak`. Abort
   with `500` and leave everything unchanged if backup fails.
3. If `mode == "master"`: write the patched `cv/web/data.yaml`.
4. Upsert selected library snippets.
5. Move staging → permanent imports storage and create the
   `resume_imports` row.

A crash between steps 3 and 4 leaves a recoverable master (backup on
disk) with fewer snippets than expected — acceptable for v1. Prefer
returning `5xx` with `backup_path` if step 4 fails after a successful
YAML write so the operator can restore deliberately.

## YAML mapping

Source: `ParsedResume` from `cvbuilder.resume_extractor`.
Target: `cv/web/data.yaml` (loaded with the same `ruamel.yaml` path the
editor already uses).

| Enabled section | `data.yaml` field | Mapping |
| --- | --- | --- |
| `profile` | `bio` | list of profile paragraphs (strings) |
| `experience` | `experience` | one entry per `ParsedExperience`: `company`, `role`, `dates: ""`, `location: ""`, `subsections: [{ heading: "Highlights", bullets: [...] }]`. If there are no bullets, use a single bullet from the heading/role line so the editor still has something editable. |
| `skills` | `skills` | `technical` = extracted skill strings; `functional` = `[]` when skills section is enabled (flat extractor output has no tech/functional split). |
| `education` | `education` | list of education paragraph strings |

**Preserved always (never overwritten by this mode):**

- `person` (names, contacts, address, profiles, photo, strengths, tagline,
  quote, etc.)
- `panels`
- Any other top-level key not in the mapping table

**Partial section updates:** if a section checkbox is off, leave that
YAML field unchanged (do not clear it).

**Empty enabled section:** if extraction finds zero items for an enabled
section, write an empty list / empty structure for that field (explicit
clear) — the user asked to build a new master from this resume, so an
empty extracted section should not silently keep old Example Company
content. Call this out in the review UI copy when counts are zero.

## Backup & recovery

- Directory: `data/backups/` (gitignored like other runtime data).
- Filename: `data.yaml.<UTC compact timestamp>Z.<hex>.bak`
  e.g. `data.yaml.20260804T163045Z.a1b2c3d4.bak` (hex suffix makes
  same-second confirms collision-safe).
- Write backup **before** mutating `cv/web/data.yaml`. If backup write
  fails → abort with `500`, no YAML change.
- Prefer also pushing a snapshot into the existing editor history store
  (`/api/history` / undo) when that API is available from the confirm
  path, so Master CV → Undo recovers without hunting the filesystem.
  If wiring history from confirm is awkward, filesystem backup alone is
  enough for v1; note it as a follow-up.

## UI (`cv/web/src/pages/import.*`)

- Enable the **Create a new master CV** radio (remove `disabled` +
  "Coming soon" microcopy; restore wireframe-equivalent description:
  "Best when this is your primary or most complete resume.").
- Keep **Compare** disabled.
- Default radio: leave **library** as the default (safer; master is
  destructive). Wireframe defaults to `new`; we intentionally diverge
  because the real app has a live master worth protecting.
- On confirm, send `mode` from the selected radio.
- Success toast / banner for master:
  `Master CV updated · {n} snippets added` with a link to `/cv/web/edit`.
- When profile/experience/skills/education counts are all zero after
  upload, warn before confirm that enabling master will clear those
  sections.

No new routes or nav items.

## Module shape

Prefer a small pure mapper in `src/cvbuilder/` (e.g.
`resume_to_master.py` or a function on the extractor package) that takes
`ParsedResume` + enabled sections + current YAML dict → new YAML dict.
Keep Flask route thin: load YAML, call mapper, dump, backup helpers.

Typing + pep257 docstrings on all new public functions/classes. Python
3.12. Prefer specific exception handling (no bare `except Exception`).

## Tests

### Pytest (TDD)

- Master confirm: person preserved; mapped sections match fixtures;
  backup file exists; snippets created; `master_updated` true.
- Disabled section left unchanged in YAML.
- Empty enabled section clears that YAML field.
- Invalid `mode` → 400.
- Library mode (no `mode` / `mode=library`) unchanged vs existing tests.
- Backup failure (inject unwritable backups dir) → YAML untouched.

### Behave (`@app @import`)

Extend `features/import_resume.feature` beyond "page returns 200":

- Master mode is selectable (not disabled).
- API confirm with `mode=master` against a staged sample resume updates
  master content while leaving `person.first_name` intact.

Wireframe scenarios stay under `features/wireframe/` and are not the
source of truth for this behaviour.

## Versioning

Bump the feature component of `VERSION` (per project
`Major.Minor.feature.fix` rules) when this ships.

## Success criteria

- User can select Create a new master CV, upload a resume, review
  sections, and confirm.
- `cv/web/data.yaml` content sections reflect the extraction; `person`
  unchanged.
- A backup file exists under `data/backups/`.
- Selected sections also appear as library snippets.
- Compare mode remains disabled and labelled coming soon.
- Existing library-import tests stay green.

## Open questions deferred

- Whether editor-history snapshot on confirm is required for v1 or a
  fast follow-up (filesystem backup is mandatory either way).
- Whether `skills.functional` should be preserved when overwriting
  `skills.technical` instead of clearing to `[]` (current decision:
  clear functional when skills section is enabled).
- Exact empty-section warning copy in the review UI.
