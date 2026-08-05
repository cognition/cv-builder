# Revised approach: Working Draft CV on DB-primary documents

**Date:** 2026-08-05
**Repo:** `cv-builder`
**Status:** Implemented — see
`docs/superpowers/plans/2026-08-05-working-draft-cv-db.md`
**Peers with:** `2026-08-05-db-primary-cv-documents-design.md` (other agent)

## Why the earlier Working Draft design is wrong now

`2026-08-05-working-draft-cv-design.md` assumed the live document still
lived on disk:

- Apply Tailor → backup + rewrite `cv/web/data.yaml`
- Snapshot Versions → `cv/variants/<name>/data.yaml` + `selections.json`
- Load Version → copy YAML files around

That fights the **DB-primary** direction already designed/planned:

- SoT = SQLite (`cv_documents` / `cv_history` / `cv_pins`)
- YAML / Markdown / PDF only on **explicit export**
- File backups under `data/backups/` retire for live mutate paths

Shipping both as written would double-write (DB + files) and leave two
sources of truth. **Do not implement the filesystem apply/snapshot path.**

## Product intent to preserve

From product conversation (still valid):

1. Rename **Master CV** → **Working Draft CV** in the UI.
2. Tailor **Save draft** stores the selection list **and** applies
   composed content into the Working Draft CV.
3. Tailor **Load draft** restores selections **and** re-applies.
4. **Versions** can be loaded back into Tailor drafts as a starting
   point (hydrate working document + restore selections when known).

## New approach (DB-native)

Treat Working Draft / Tailor / Versions as **roles on top of the
DB-primary document model**, not as file workflows.

### Mapping

| Product name | Storage | Notes |
| --- | --- | --- |
| Working Draft CV | Single `cv_documents` row (`kind='working'`, rename from planned `master`) | Active editable document for `/cv/web/edit` |
| Tailor draft | Existing `drafts` table | Ordered `{snippet_id, detail_level, section?}` only |
| Version (starting point / snapshot) | `cv_pins` on the working document **plus** `selections_json` | Freeze content + undo stacks **and** Tailor selection list |
| Optional “published” / export name | Explicit export only | No live `cv/variants/` SoT |

Use `kind='working'` (not `master`) so naming matches the product. On
bootstrap from old `data.yaml`, insert `kind='working'`. If an early
implementation already inserted `kind='master'`, migrate that row.

### Why pins (not variant documents) for Versions

DB-primary already distinguishes:

- **Working document** — continues after you pin
- **Pins** — freeze content + history; restore loads them back

That matches “use a Version as a starting point” better than creating a
second full document per tailor run. Variant-kind documents can remain
for rare export/archive use later; **Versions UI for Tailor should be
pins of the Working Draft.**

Extend `cv_pins`:

| Column | Type | Notes |
| --- | --- | --- |
| `selections_json` | TEXT NOT NULL DEFAULT `'[]'` | Tailor selections frozen with the pin |

Restore/load-into-draft then has everything needed in one row.

### Tailor Save draft (DB path)

```text
PUT /api/drafts/<name>  { selections, apply: true, pin_label?: "…" }

1. Upsert drafts table (selections)
2. DocumentStore: load working content_yaml → parse
3. Composer._build_document(base=working, selections)  # person preserved
4. DocumentStore: push history + save working content_yaml
5. If pin_label set: create cv_pin from current working state
   including selections_json = selections
6. Optional PDF preview artefact only (not SoT)
```

No `data.yaml` write. No `cv/variants/` write.

### Tailor Load draft

1. Load selections from `drafts`
2. Same apply steps 2–4 as above (rebuild working document from selections)

### Load Version into draft (“Use as starting point”)

```text
POST /api/pins/<id>/load-into-draft

1. Auto-pin current working state (`before-restore:<id>`) — already in
   DB-primary restore rules
2. Restore pin content → working document + history stacks
3. Upsert a Tailor draft (name e.g. from-<label> or pin label)
   from pin.selections_json
4. Return { draft_name, selections, document_updated: true }
5. Client opens Tailor (and/or Working Draft CV)
```

If `selections_json` is empty (legacy pin): still hydrate Working Draft;
return empty selections + warning — user rebuilds the Tailor list from
the library.

### Compose button

Same as Save draft with `apply: true`. Optional `pin_label` / snapshot
name field on Tailor maps to creating a pin, not a filesystem variant.

### UI

- Nav / edit page: **Working Draft CV**
- Tailor: Save draft / Load draft / Update Working Draft CV
- Versions page: list **pins** of the working document; action
  **Use as starting point** → `load-into-draft`

### What to change in DB-primary (small deltas)

1. Prefer `kind='working'` over `kind='master'` (or accept both during
   migrate; UI always says Working Draft).
2. Add `selections_json` to `cv_pins`.
3. Document Tailor apply + load-into-draft as first-class DocumentStore /
   API flows in the DB-primary plan (not file backup / selections.json on
   disk).
4. Defer or demote filesystem `cv/variants/` compose as SoT — compose
   updates working doc and optional pin; variant-kind rows only if still
   needed for MCP compatibility (map pin ↔ old “variant name” carefully).

### What to stop / void from the old Working Draft spec

| Old idea | Disposition |
| --- | --- |
| Backup + rewrite `cv/web/data.yaml` on apply | **Void** — DocumentStore save |
| `cv/variants/<name>/selections.json` | **Void** — `cv_pins.selections_json` |
| Copy variant YAML onto master on load | **Void** — pin restore |
| File backups for apply safety | **Void** — auto-pin before restore / history push |

Keep: UI rename, apply-on-save-draft, load-version-as-starting-point.

## Sequencing recommendation

1. **Land DB-primary document store** (other agent’s plan) with the deltas
   above (`working` kind + `selections_json` on pins).
2. **Then** implement Tailor apply-on-save/load and Versions →
   load-into-draft against DocumentStore only.
3. Mark `2026-08-05-working-draft-cv-design.md` as **superseded** by this
   revision + DB-primary.

Do **not** implement filesystem tailor→master apply in parallel.

## Success criteria (revised)

- Working Draft CV is a DB document; edits don’t rely on live `data.yaml`.
- Tailor Save draft updates `drafts` **and** the working DB document.
- Tailor Load draft re-applies into the working DB document.
- A Version (pin) can hydrate Working Draft CV and restore Tailor
  selections when recorded.
- Explicit export is the only path that writes YAML/MD/PDF as artefacts.
