# Working Draft CV (DB-native) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Tailor Save/Load apply into a DB Working Draft CV, and let Versions (pins) hydrate that document plus Tailor selections — with no live `data.yaml` / `cv/variants/` SoT writes.

**Architecture:** Depends on `DocumentStore` from `2026-08-05-db-primary-cv-documents.md`. Amend that store to use `kind='working'` and `cv_pins.selections_json`. Add `WorkingDraftApplier` that composes selections onto the working YAML blob and saves via DocumentStore. Retarget Tailor drafts API + Versions UI to pins.

**Tech Stack:** Python 3.12, SQLite, Flask (`scripts/serve-editor.py`), `CvComposer._build_document`, pytest, Behave.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-05-working-draft-cv-db-revision.md`
- Prerequisite: DB-primary DocumentStore / pin APIs landed (or land Task 1 deltas in the same branch before Tailor work)
- Canadian spelling in user-facing copy
- Type hints + pep257 docstrings on all new public Python classes/methods
- Prefer specific exceptions (no broad `except Exception` / Pylint W0718)
- Prefer classes over free functions for new Python modules
- TDD: failing test first for every behaviour
- Version scheme: `Major.Minor.feature.fix` — bump feature when this ships (coordinate with DB-primary: one bump if same release; otherwise `0.2.13.0` → `0.2.14.0` if DB already bumped)
- Do **not** write live SoT to `cv/web/data.yaml` or `cv/variants/` on apply/save/load
- Keep `drafts` table for selection lists; pins hold frozen selections for Versions

## File structure

| File | Responsibility |
| --- | --- |
| `src/cvbuilder/models.py` | `CvPin.selections`; keep working-document helpers |
| `src/cvbuilder/database.py` | Schema: `kind` allows `working`; `cv_pins.selections_json` |
| `src/cvbuilder/document_store.py` | `get_working` / `upsert_working`; pin create/restore with selections |
| `src/cvbuilder/working_draft.py` | `WorkingDraftApplier`: compose selections → save working doc |
| `src/cvbuilder/composer.py` | Public `build_document_from_selections` (no file write) |
| `scripts/serve-editor.py` | Draft apply flags; `POST /api/pins/<id>/load-into-draft`; UI rename |
| `cv/web/src/shell/nav.html` | Nav label Working Draft CV |
| `cv/web/src/pages/master.html` (or rename) | Page title Working Draft CV |
| `cv/web/src/pages/tailor.html` / `tailor.js` | Apply on save/load; pin on compose |
| `cv/web/src/pages/versions.js` / `versions.html` | List pins; Use as starting point |
| `tests/test_working_draft.py` | Applier + pin selections unit tests |
| `tests/test_api.py` | Draft apply + load-into-draft API tests |
| `features/master_cv.feature` → working draft | Behave rename |
| `README.md`, `VERSION`, `src/cvbuilder/__init__.py` | Docs + feature bump |

---

### Task 1: Schema/store deltas (`working` + pin selections)

**Files:**
- Modify: `src/cvbuilder/models.py`
- Modify: `src/cvbuilder/database.py`
- Modify: `src/cvbuilder/document_store.py`
- Modify: `tests/test_document_schema.py`
- Modify: `tests/test_document_store.py`

**Interfaces:**
- Consumes: existing DocumentStore CRUD/history/pins from DB-primary plan
- Produces:
  ```python
  @dataclass
  class CvPin:
      document_id: int
      label: str
      content_yaml: str
      undo: list[dict[str, str]]
      redo: list[dict[str, str]]
      selections: list[dict[str, Any]] = field(default_factory=list)
      id: Optional[int] = None
      created_at: Optional[str] = None

  class DocumentStore:
      def get_working(self) -> Optional[CvDocument]:
          """Return the single working document (kind working|master)."""

      def upsert_working(self, content_yaml: str) -> CvDocument:
          """Insert or update the working document row."""

      def create_pin(
          self,
          document_id: int,
          label: str,
          *,
          selections: Optional[list[dict[str, Any]]] = None,
      ) -> CvPin:
          """Freeze content + history stacks + optional Tailor selections."""

      # Prefer get_working/upsert_working; keep get_master/upsert_master as
      # thin aliases that call working methods during transition.
  ```

- [ ] **Step 1: Write failing schema/store tests**

Append to `tests/test_document_schema.py`:

```python
def test_cv_pins_has_selections_json(self, tmp_path: Path) -> None:
    """cv_pins must include selections_json after ensure_schema."""
    database = SnippetDatabase(tmp_path / "snippets.db")
    database.ensure_schema()
    with database.connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(cv_pins)")
        }
    assert "selections_json" in columns
```

Append to `tests/test_document_store.py`:

```python
def test_upsert_working_and_pin_with_selections(self, tmp_path: Path) -> None:
    """Working doc + pin must round-trip Tailor selections."""
    store = _store(tmp_path)
    doc = store.upsert_working("person:\n  first_name: Homer\nbio:\n  - hi\n")
    pin = store.create_pin(
        doc.id,
        "ircc-v1",
        selections=[{"snippet_id": 1, "detail_level": "standard"}],
    )
    assert pin.selections == [{"snippet_id": 1, "detail_level": "standard"}]
    listed = store.list_pins(doc.id)
    assert listed[0].selections[0]["snippet_id"] == 1
    assert store.get_working() is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_document_schema.py::TestDocumentSchema::test_cv_pins_has_selections_json tests/test_document_store.py::TestDocumentStore::test_upsert_working_and_pin_with_selections -v`

Expected: FAIL (column or method missing)

- [ ] **Step 3: Implement schema + store methods**

In `database.py` `ensure_schema`:

- Create/alter `cv_documents.kind` to allow `'working'` (and treat `'master'` as synonym on read).
- Add `selections_json TEXT NOT NULL DEFAULT '[]'` to `cv_pins` (`ALTER TABLE` for existing DBs if table already created without it).

In `document_store.py`:

- `get_working` / `upsert_working` prefer `kind='working'`; if only `kind='master'` exists, migrate that row’s kind to `working` once on first upsert or get.
- `create_pin(..., selections=None)` serialises `json.dumps(selections or [])`.
- `_row_to_pin` deserialises; corrupt JSON → `[]` + `logging.warning`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_document_schema.py tests/test_document_store.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/models.py src/cvbuilder/database.py \
  src/cvbuilder/document_store.py tests/test_document_schema.py \
  tests/test_document_store.py
git commit -m "$(cat <<'EOF'
feat(db): working document kind and pin selections_json

EOF
)"
```

---

### Task 2: Compose without writing files + WorkingDraftApplier

**Files:**
- Modify: `src/cvbuilder/composer.py`
- Create: `src/cvbuilder/working_draft.py`
- Create: `tests/test_working_draft.py`

**Interfaces:**
- Consumes: `CvComposer._build_document`, `DocumentStore.get_working` / `upsert_working` / `push_before_change` / `create_pin`, `SnippetDatabase`
- Produces:
  ```python
  class CvComposer:
      def build_document_from_selections(
          self,
          base: dict[str, Any],
          selections: list[dict[str, Any]] | list[SelectionItem],
      ) -> dict[str, Any]:
          """Return a data.yaml-shaped dict; do not write files."""

  class WorkingDraftApplier:
      def __init__(
          self,
          database: SnippetDatabase,
          store: DocumentStore,
          repo_root: Path,
      ) -> None: ...

      def apply_selections(
          self,
          selections: list[dict[str, Any]],
          *,
          history_label: str = "apply-draft",
          pin_label: Optional[str] = None,
      ) -> dict[str, Any]:
          """Push history, compose onto working YAML, save; optional pin.

          Returns:
              {
                "ok": True,
                "document_id": int,
                "selection_count": int,
                "pin": Optional[dict],  # pin.to_dict()-like if created
              }
          Raises:
              ValueError: empty selections or missing working document.
              KeyError: missing snippet detail level.
          """
  ```

- [ ] **Step 1: Write failing applier tests**

Create `tests/test_working_draft.py`:

```python
"""Tests for applying Tailor selections into the Working Draft CV."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.models import DetailLevel, Snippet, SnippetVariant
from cvbuilder.working_draft import WorkingDraftApplier


def _seed_snippets(database: SnippetDatabase) -> int:
    snippet = Snippet(
        category="bio",
        heading="Opening",
        company="",
        role="",
        variants=[
            SnippetVariant(
                detail_level=DetailLevel.STANDARD,
                content="Springfield power plant operator.",
            )
        ],
    )
    return database.upsert_snippet(snippet).id


def _applier(tmp_path: Path, repo_root: Path) -> tuple[WorkingDraftApplier, DocumentStore]:
    database = SnippetDatabase(tmp_path / "snippets.db")
    database.ensure_schema()
    store = DocumentStore(database)
    store.upsert_working(
        "person:\n  first_name: Homer\n  last_name: Simpson\n"
        "bio: []\nskills:\n  technical: []\n  functional: []\n"
        "experience: []\neducation: []\n"
    )
    return WorkingDraftApplier(database, store, repo_root), store


class TestWorkingDraftApplier:
    """Apply Tailor selections into the DB working document."""

    def test_apply_updates_working_yaml_without_files(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """Working blob gains bio text; no cv/variants write."""
        applier, store = _applier(tmp_path, repo_fixture)
        snippet_id = _seed_snippets(applier.database)
        before = list((repo_fixture / "cv" / "variants").glob("*/data.yaml"))
        result = applier.apply_selections(
            [{"snippet_id": snippet_id, "detail_level": "standard"}]
        )
        assert result["ok"] is True
        working = store.get_working()
        assert working is not None
        assert "Springfield power plant" in working.content_yaml
        assert "Homer" in working.content_yaml
        after = list((repo_fixture / "cv" / "variants").glob("*/data.yaml"))
        assert after == before

    def test_apply_with_pin_stores_selections(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """pin_label freezes selections_json on the new pin."""
        applier, store = _applier(tmp_path, repo_fixture)
        snippet_id = _seed_snippets(applier.database)
        selections = [{"snippet_id": snippet_id, "detail_level": "standard"}]
        result = applier.apply_selections(selections, pin_label="nuclear-v1")
        assert result["pin"] is not None
        pin = store.list_pins(result["document_id"])[0]
        assert pin.label == "nuclear-v1"
        assert pin.selections[0]["snippet_id"] == snippet_id

    def test_apply_rejects_empty_selections(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """Empty selection list must raise ValueError."""
        applier, _store = _applier(tmp_path, repo_fixture)
        with pytest.raises(ValueError, match="selections"):
            applier.apply_selections([])
```

Adapt `Snippet` / `upsert_snippet` construction to match existing `tests/test_composer.py` fixtures if the dataclass shape differs — reuse that fixture pattern rather than inventing new seed APIs.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_working_draft.py -v`

Expected: FAIL (`working_draft` module missing)

- [ ] **Step 3: Implement composer helper + applier**

In `composer.py`, add:

```python
def build_document_from_selections(
    self,
    base: dict[str, Any],
    selections: list[dict[str, Any]] | list[SelectionItem],
) -> dict[str, Any]:
    """Assemble a document dict from selections without writing files."""
    items = self._normalise_selections(selections)
    return self._build_document(base, items)
```

In `working_draft.py`:

```python
"""Apply Tailor selections into the Working Draft CV document store."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any, Optional

from cvbuilder.composer import CvComposer, _YAML
from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore


class WorkingDraftApplier:
    """Compose Tailor selections onto the DB working document."""

    def __init__(
        self,
        database: SnippetDatabase,
        store: DocumentStore,
        repo_root: Path,
    ) -> None:
        """Initialise with DB, document store, and repo root for composer."""
        self.database = database
        self.store = store
        self.composer = CvComposer(database=database, repo_root=repo_root)

    def apply_selections(
        self,
        selections: list[dict[str, Any]],
        *,
        history_label: str = "apply-draft",
        pin_label: Optional[str] = None,
    ) -> dict[str, Any]:
        """Push history, compose onto working YAML, save; optional pin."""
        if not selections:
            raise ValueError("selections must be a non-empty list")
        working = self.store.get_working()
        if working is None or working.id is None:
            raise ValueError("working draft document is missing")
        base = _YAML.load(StringIO(working.content_yaml)) or {}
        document = self.composer.build_document_from_selections(
            base, selections
        )
        buf = StringIO()
        _YAML.dump(document, buf)
        new_yaml = buf.getvalue()
        self.store.push_before_change(
            working.id, history_label, working.content_yaml
        )
        saved = self.store.upsert_working(new_yaml)
        pin_payload: Optional[dict[str, Any]] = None
        if pin_label:
            pin = self.store.create_pin(
                saved.id, pin_label.strip(), selections=list(selections)
            )
            pin_payload = {
                "id": pin.id,
                "label": pin.label,
                "selections": list(pin.selections),
            }
        return {
            "ok": True,
            "document_id": saved.id,
            "selection_count": len(selections),
            "pin": pin_payload,
        }
```

If `_YAML` is private, expose a small dump/load helper on `CvComposer` instead of importing `_YAML` — keep encapsulation clean.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_working_draft.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/composer.py src/cvbuilder/working_draft.py \
  tests/test_working_draft.py
git commit -m "$(cat <<'EOF'
feat(tailor): apply selections into Working Draft via DocumentStore

EOF
)"
```

---

### Task 3: Draft APIs apply on save/load + optional pin

**Files:**
- Modify: `scripts/serve-editor.py`
- Modify: `tests/test_api.py` (or create `tests/test_working_draft_api.py`)

**Interfaces:**
- Consumes: `WorkingDraftApplier`, `SnippetDatabase.save_draft` / `get_draft`
- Produces HTTP:
  - `PUT /api/drafts/<name>` body `{selections, apply?: bool, pin_label?: str}`
  - `POST /api/drafts/<name>/apply` body `{pin_label?: str}` (load-from-saved + apply)
  - Keep `GET /api/drafts/<name>` returning selections only

- [ ] **Step 1: Write failing API tests**

```python
def test_put_draft_with_apply_updates_working_document(
    client, seeded_db
) -> None:
    """PUT apply=true must update working content_yaml."""
    # Arrange: working document + one bio snippet in DB (reuse API fixtures)
    selections = [{"snippet_id": 1, "detail_level": "standard"}]
    resp = client.put(
        "/api/drafts/demo",
        json={"selections": selections, "apply": True},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["name"] == "demo"
    assert body["applied"] is True
    working = client.get("/api/person")  # or dedicated get-working helper
    assert working.status_code == 200


def test_post_draft_apply_reapplies_saved_selections(client, seeded_db) -> None:
    """POST /api/drafts/<name>/apply rebuilds working from stored selections."""
    client.put("/api/drafts/demo", json={"selections": [...]})
    resp = client.post("/api/drafts/demo/apply", json={})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
```

Use the same Flask test client / DB seeding pattern as existing `tests/test_api.py` draft tests. Assert **no** new files under `cv/variants/` when `apply` is true.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -k "draft_with_apply or draft_apply" -v`

Expected: FAIL

- [ ] **Step 3: Implement routes**

Update `api_save_draft`:

```python
@app.put("/api/drafts/<name>")
def api_save_draft(name: str) -> Any:
    """Create or update a named draft; optionally apply into Working Draft."""
    payload = request.get_json(force=True) or {}
    selections = payload.get("selections") or []
    if not isinstance(selections, list):
        return jsonify(error="selections must be a list"), 400
    apply = bool(payload.get("apply"))
    pin_label = payload.get("pin_label")
    database = _database()
    try:
        draft = database.save_draft(name, selections)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    result = draft.to_dict()
    result["applied"] = False
    if apply:
        if not selections:
            return jsonify(error="selections must be a non-empty list"), 400
        applier = WorkingDraftApplier(
            database, _document_store(), cvweb.REPO_ROOT
        )
        try:
            applied = applier.apply_selections(
                selections,
                history_label=f"draft:{name}",
                pin_label=str(pin_label).strip() if pin_label else None,
            )
        except (ValueError, KeyError) as exc:
            return jsonify(error=str(exc)), 400
        result["applied"] = True
        result["apply"] = applied
    return jsonify(result)


@app.post("/api/drafts/<name>/apply")
def api_apply_draft(name: str) -> Any:
    """Re-apply a saved draft's selections into the Working Draft CV."""
    payload = request.get_json(force=True) or {}
    pin_label = payload.get("pin_label")
    database = _database()
    draft = database.get_draft(name)
    if draft is None:
        return jsonify(error="not found"), 404
    applier = WorkingDraftApplier(
        database, _document_store(), cvweb.REPO_ROOT
    )
    try:
        applied = applier.apply_selections(
            draft.selections,
            history_label=f"draft:{name}",
            pin_label=str(pin_label).strip() if pin_label else None,
        )
    except (ValueError, KeyError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify({"ok": True, "name": name, **applied})
```

Wire `_document_store()` the same way DB-primary editor routes do.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -k draft -v tests/test_working_draft.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/serve-editor.py tests/test_api.py
git commit -m "$(cat <<'EOF'
feat(api): apply Tailor drafts into Working Draft CV

EOF
)"
```

---

### Task 4: Load pin into draft API

**Files:**
- Modify: `src/cvbuilder/document_store.py` (if restore needs to return selections)
- Modify: `scripts/serve-editor.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces:
  - `POST /api/pins/<int:pin_id>/load-into-draft`
  - Body optional: `{ "draft_name": "…" }`
  - Response:
    ```json
    {
      "ok": true,
      "draft_name": "from-ircc-v1",
      "selections": [...],
      "document_updated": true,
      "selections_restored": true,
      "warning": null
    }
    ```

- [ ] **Step 1: Write failing API test**

```python
def test_load_pin_into_draft_hydrates_working_and_draft(client) -> None:
    """Restore pin content, upsert draft from selections_json."""
    # create working, apply+pin via WorkingDraftApplier or POST /api/pins
    # mutate working away from pin
    resp = client.post(f"/api/pins/{pin_id}/load-into-draft", json={})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["document_updated"] is True
    assert body["selections"]
    draft = client.get(f"/api/drafts/{body['draft_name']}")
    assert draft.status_code == 200
    assert draft.get_json()["selections"] == body["selections"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py::test_load_pin_into_draft_hydrates_working_and_draft -v`

Expected: FAIL (404 / missing route)

- [ ] **Step 3: Implement route**

```python
@app.post("/api/pins/<int:pin_id>/load-into-draft")
def api_pin_load_into_draft(pin_id: int) -> Any:
    """Restore a pin into Working Draft and recreate a Tailor draft."""
    payload = request.get_json(force=True) or {}
    store = _document_store()
    database = _database()
    try:
        pin = store.restore_pin(pin_id)  # auto before-restore pin
    except KeyError as exc:
        return jsonify(error=str(exc)), 404
    draft_name = str(payload.get("draft_name") or "").strip()
    if not draft_name:
        safe = re.sub(r"[^a-zA-Z0-9._-]+", "-", pin.label).strip("-")
        draft_name = f"from-{safe}" if safe else f"from-pin-{pin_id}"
    selections = list(pin.selections or [])
    warning = None
    if not selections:
        warning = "Pin has no Tailor selections; Working Draft was restored only."
    database.save_draft(draft_name, selections)
    return jsonify(
        {
            "ok": True,
            "draft_name": draft_name,
            "selections": selections,
            "document_updated": True,
            "selections_restored": bool(selections),
            "warning": warning,
        }
    )
```

Ensure `restore_pin` returns a `CvPin` that includes `selections` from the restored pin row (not the auto before-restore pin).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -k "load_pin_into_draft or pins" -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/serve-editor.py src/cvbuilder/document_store.py tests/test_api.py
git commit -m "$(cat <<'EOF'
feat(api): load version pin into Tailor draft and Working Draft

EOF
)"
```

---

### Task 5: Tailor + Versions UI

**Files:**
- Modify: `cv/web/src/pages/tailor.html`
- Modify: `cv/web/src/pages/tailor.js`
- Modify: `cv/web/src/pages/versions.html`
- Modify: `cv/web/src/pages/versions.js`
- Modify: `cv/web/src/shell/nav.html`
- Modify: Master edit page titles (`cv/web/src/pages/master.html`, shell `active`)
- Test: `features/master_cv.feature` (rename assertions) + manual smoke

**Interfaces:**
- Consumes: `PUT /api/drafts/<name>` with `apply: true`; `POST /api/drafts/<name>/apply`; `GET /api/pins?document=working`; `POST /api/pins/<id>/load-into-draft`

- [ ] **Step 1: Write failing Behave expectations**

Update `features/master_cv.feature` (or rename to `working_draft_cv.feature`):

```gherkin
@app @working-draft
Feature: Working Draft CV
  Scenario: Working Draft CV opens inside the Studio shell
    When I open the "working draft" page
    Then the response status is 200
    And the "working-draft" nav item is marked active
    And the page title contains "Working Draft"
```

Update step aliases in `features/steps/app_steps.py` so `"working draft"` resolves to `/cv/web/edit` and nav `active == 'working-draft'` (or keep `master` id temporarily and only change visible label — prefer renaming `active` to `working-draft` consistently).

- [ ] **Step 2: Run Behave to verify fail**

Run: `behave features/master_cv.feature -v` (or renamed feature)

Expected: FAIL on title/nav copy

- [ ] **Step 3: Implement UI**

1. `nav.html`: label **Working Draft CV**; `active == 'working-draft'`.
2. Edit page title / H1: **Working Draft CV**.
3. `tailor.js` `saveDraft`:

```javascript
const resp = await fetch("/api/drafts/" + encodeURIComponent(name), {
  method: "PUT",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    selections: draft.map(...),
    apply: true,
    pin_label: variantName.value.trim() || null,
  }),
});
```

4. `loadDraft`: after GET, call `POST /api/drafts/<name>/apply`, then refresh local draft UI; toast if warning.

5. `composeDraft`: switch primary path to save+apply (and optional pin); PDF preview via existing `/api/preview.pdf` against working document (DB-primary must already serve preview from store). Do **not** call `/api/compose` for live SoT; leave `/api/compose` only if still used for explicit export (follow DB-primary flags).

6. `versions.js`: fetch `GET /api/pins?document=working` instead of `/api/variants`. Render pin label + created_at. Add button **Use as starting point** → `POST /api/pins/<id>/load-into-draft` then `location.href = '/cv/web/build'` (or equivalent Tailor route) with toast for `draft_name`.

7. Copy: rename “Version name” field help to “Pin / version label (optional on save)”.

- [ ] **Step 4: Run Behave + pytest smoke**

Run:

```bash
behave features/ -v
pytest tests/test_working_draft.py tests/test_api.py -k "draft or pin or working" -v
```

Expected: PASS for updated scenarios

- [ ] **Step 5: Commit**

```bash
git add cv/web/src features/ scripts/serve-editor.py
git commit -m "$(cat <<'EOF'
feat(ui): Working Draft CV rename and Tailor/Versions pin flows

EOF
)"
```

---

### Task 6: Docs, version bump, supersede old specs

**Files:**
- Modify: `README.md`
- Modify: `VERSION`
- Modify: `src/cvbuilder/__init__.py`
- Modify: `docs/superpowers/specs/2026-08-05-working-draft-cv-db-revision.md` (status: Implemented when done)
- Ensure `2026-08-05-working-draft-cv-design.md` stays SUPERSEDED

- [ ] **Step 1: Bump feature version**

If DB-primary already shipped as `0.2.13.0`, set `VERSION` to `0.2.14.0`. If this lands with DB-primary in one release, use a single feature bump only.

- [ ] **Step 2: README**

Document: Working Draft CV is DB-backed; Tailor Save/Load apply into it; Versions are pins with optional Tailor selections; export for YAML/PDF artefacts.

- [ ] **Step 3: Verification suite**

Run:

```bash
pytest tests/ -v
behave features/ -v
```

Expected: PASS (exclude wireframe tags as configured)

- [ ] **Step 4: Commit**

```bash
git add README.md VERSION src/cvbuilder/__init__.py docs/superpowers/specs/
git commit -m "$(cat <<'EOF'
docs: document Working Draft CV on DB-primary documents

EOF
)"
```

---

## Self-review

1. **Spec coverage:** Working rename → Task 5; Save draft apply → Tasks 2–3, 5; Load draft re-apply → Tasks 3, 5; Load Version → Tasks 1, 4, 5; no file SoT → Tasks 2–3 asserts.
2. **Placeholders:** None intentionally left; adapt Snippet seeding to existing composer test fixtures in Task 2.
3. **Type consistency:** `get_working` / `upsert_working` / `create_pin(..., selections=)` / `WorkingDraftApplier.apply_selections` used uniformly.

## Prerequisite note for the DB-primary plan

Before or during Task 1 of this plan, update
`docs/superpowers/plans/2026-08-05-db-primary-cv-documents.md` so new work uses:

- `kind='working'` (alias `master` on read/migrate)
- `cv_pins.selections_json`
- Pin list query `document=working`

Do not implement filesystem Tailor→master apply from the superseded Working Draft design.
