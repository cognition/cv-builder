# DB-Primary CV Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SQLite the source of truth for Master and variant CV documents, with a transitory history table and pins; write YAML/Markdown/PDF only on explicit export.

**Document kinds:** `master` | `variant` only (approved design). Do not introduce `kind='working'` or pin `selections_json` in this plan.

**Architecture:** Extend `SnippetDatabase` with `cv_documents`, `cv_history`, and `cv_pins`. Add a `DocumentStore` class that owns document CRUD, undo/redo stacks, pins, and one-time bootstrap from files. Retarget editor, compose, import-master, and export through that store so live paths never treat `cv/web/data.yaml` as SoT.

**Tech Stack:** Python 3.12, SQLite (`sqlite3`), Flask (`scripts/serve-editor.py`), ruamel YAML via `scripts/cvweb.py`, Jinja + Chrome PDF, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-05-db-primary-cv-documents-design.md`
- Canadian spelling in user-facing copy
- Type hints + pep257 docstrings on all new public Python classes/methods
- Prefer specific exceptions (no broad `except Exception` / Pylint W0718)
- Prefer classes over free functions for new Python modules
- TDD: failing test first for every behaviour
- Version scheme: `Major.Minor.feature.fix` — bump feature when this ships (`0.2.12.3` → `0.2.13.0`)
- Keep existing YAML document shape; do not normalise sections into relational tables this pass
- Pin UI chrome is out of scope; ship pin APIs + tests

## File structure

| File | Responsibility |
| --- | --- |
| `src/cvbuilder/models.py` | `CvDocument`, `CvHistoryState`, `CvPin` dataclasses |
| `src/cvbuilder/database.py` | Schema + low-level SQL for documents/history/pins |
| `src/cvbuilder/document_store.py` | `DocumentStore`: load/save, history, pins, bootstrap |
| `src/cvbuilder/markdown_export.py` | `MarkdownExporter`: document dict → Markdown text |
| `src/cvbuilder/composer.py` | Compose into DB variant documents; export files only when asked |
| `src/cvbuilder/importer.py` | Prefer master document blob when seeding from master sections |
| `scripts/cvweb.py` | Keep YAML parse/dump/path helpers; `EditHistory` becomes DB-backed adapter or thin wrapper |
| `scripts/serve-editor.py` | Editor/export/pins/compose/import routes use `DocumentStore` |
| `scripts/generate-cv-web.py` | Load master from DB for PDF generation |
| `tests/test_document_store.py` | Unit tests for store/history/pins/bootstrap |
| `tests/test_markdown_export.py` | Markdown export unit tests |
| `tests/test_history.py` | Retarget to DB history |
| `tests/test_api.py` | Assert DB mutations; export writes files; edits do not |
| `tests/test_composer.py` | Variant rows in DB without YAML files by default |
| `README.md`, `VERSION`, `src/cvbuilder/__init__.py` | Docs + feature bump |

---

### Task 1: Models + schema for documents/history/pins

**Files:**
- Modify: `src/cvbuilder/models.py`
- Modify: `src/cvbuilder/database.py`
- Create: `tests/test_document_schema.py`

**Interfaces:**
- Consumes: existing `SnippetDatabase.ensure_schema` / `connect`
- Produces:
  ```python
  @dataclass
  class CvDocument:
      kind: str  # "master" | "variant"
      content_yaml: str
      name: Optional[str] = None
      id: Optional[int] = None
      updated_at: Optional[str] = None

  @dataclass
  class CvHistoryState:
      document_id: int
      undo: list[dict[str, str]]  # {label, text}
      redo: list[dict[str, str]]
      updated_at: Optional[str] = None

  @dataclass
  class CvPin:
      document_id: int
      label: str
      content_yaml: str
      undo: list[dict[str, str]]
      redo: list[dict[str, str]]
      id: Optional[int] = None
      created_at: Optional[str] = None
  ```
  Schema tables: `cv_documents`, `cv_history`, `cv_pins` as in the spec.

- [ ] **Step 1: Write the failing schema test**

Create `tests/test_document_schema.py`:

```python
"""Schema tests for CV documents, history, and pins tables."""

from __future__ import annotations

from pathlib import Path

from cvbuilder.database import SnippetDatabase


class TestDocumentSchema:
    """Ensure document-related tables exist after ensure_schema."""

    def test_ensure_schema_creates_document_tables(self, tmp_path: Path) -> None:
        """cv_documents, cv_history, and cv_pins must exist."""
        database = SnippetDatabase(tmp_path / "snippets.db")
        database.ensure_schema()
        with database.connect() as connection:
            names = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert "cv_documents" in names
        assert "cv_history" in names
        assert "cv_pins" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_document_schema.py::TestDocumentSchema::test_ensure_schema_creates_document_tables -v`

Expected: FAIL (tables missing)

- [ ] **Step 3: Add dataclasses and SCHEMA_SQL tables**

Append to `SCHEMA_SQL` in `src/cvbuilder/database.py`:

```sql
CREATE TABLE IF NOT EXISTS cv_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT,
    content_yaml TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cv_documents_variant_name
    ON cv_documents(name) WHERE kind = 'variant';

CREATE UNIQUE INDEX IF NOT EXISTS idx_cv_documents_one_master
    ON cv_documents(kind) WHERE kind = 'master';

CREATE TABLE IF NOT EXISTS cv_history (
    document_id INTEGER PRIMARY KEY,
    undo_json TEXT NOT NULL DEFAULT '[]',
    redo_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(document_id) REFERENCES cv_documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cv_pins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    content_yaml TEXT NOT NULL,
    undo_json TEXT NOT NULL DEFAULT '[]',
    redo_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(document_id) REFERENCES cv_documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cv_pins_document ON cv_pins(document_id);
```

Add the three dataclasses to `src/cvbuilder/models.py` with `to_dict` helpers matching existing style.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_document_schema.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/models.py src/cvbuilder/database.py tests/test_document_schema.py
git commit -m "feat(db): add cv_documents, cv_history, and cv_pins schema"
```

---

### Task 2: `DocumentStore` — CRUD, history, pins

**Files:**
- Create: `src/cvbuilder/document_store.py`
- Modify: `src/cvbuilder/database.py` (optional thin SQL helpers used by the store)
- Create: `tests/test_document_store.py`

**Interfaces:**
- Consumes: `SnippetDatabase`, `CvDocument`, `CvHistoryState`, `CvPin`
- Produces:
  ```python
  class DocumentStore:
      """Database-backed CV documents with transitory undo history and pins."""

      MAX_HISTORY = 50

      def __init__(self, database: SnippetDatabase) -> None: ...

      def get_master(self) -> Optional[CvDocument]: ...
      def get_variant(self, name: str) -> Optional[CvDocument]: ...
      def list_variants(self) -> list[CvDocument]: ...
      def upsert_master(self, content_yaml: str) -> CvDocument: ...
      def upsert_variant(self, name: str, content_yaml: str) -> CvDocument: ...
      def delete_variant(self, name: str) -> None: ...

      def history_status(self, document_id: int) -> dict[str, Any]: ...
      def push_before_change(
          self, document_id: int, label: str, text: str
      ) -> None: ...
      def undo(self, document_id: int) -> dict[str, Any]: ...
      def redo(self, document_id: int) -> dict[str, Any]: ...

      def create_pin(self, document_id: int, label: str) -> CvPin: ...
      def list_pins(self, document_id: int) -> list[CvPin]: ...
      def restore_pin(self, pin_id: int) -> CvPin: ...
      def delete_pin(self, pin_id: int) -> None: ...
  ```

- [ ] **Step 1: Write failing unit tests**

Create `tests/test_document_store.py` covering at least:

```python
"""Unit tests for DocumentStore CRUD, history, and pins."""

from __future__ import annotations

from pathlib import Path

from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore


def _store(tmp_path: Path) -> DocumentStore:
    database = SnippetDatabase(tmp_path / "snippets.db")
    database.ensure_schema()
    return DocumentStore(database)


class TestDocumentStore:
    """Core document and history behaviour."""

    def test_upsert_and_get_master(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_master("bio:\n  - hello\n")
        master = store.get_master()
        assert master is not None
        assert "hello" in master.content_yaml

    def test_undo_redo_round_trip(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        doc = store.upsert_master("bio:\n  - one\n")
        store.push_before_change(doc.id, "edit", doc.content_yaml)
        store.upsert_master("bio:\n  - two\n")
        result = store.undo(doc.id)
        assert "one" in store.get_master().content_yaml
        assert result["can_redo"] is True
        store.redo(doc.id)
        assert "two" in store.get_master().content_yaml

    def test_pin_restore_brings_content_and_stacks(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        doc = store.upsert_master("bio:\n  - pinned\n")
        store.push_before_change(doc.id, "edit", "bio:\n  - pinned\n")
        store.upsert_master("bio:\n  - intermediate\n")
        pin = store.create_pin(doc.id, "checkpoint")
        store.push_before_change(doc.id, "edit", store.get_master().content_yaml)
        store.upsert_master("bio:\n  - later\n")
        store.restore_pin(pin.id)
        assert "intermediate" in store.get_master().content_yaml
        status = store.history_status(doc.id)
        assert status["can_undo"] is True

    def test_variant_upsert_and_list(self, tmp_path: Path) -> None:
        store = _store(tmp_path)
        store.upsert_variant("nuclear-oncall", "person:\n  first_name: Homer\n")
        names = [v.name for v in store.list_variants()]
        assert names == ["nuclear-oncall"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_document_store.py -v`

Expected: FAIL (module missing)

- [ ] **Step 3: Implement `DocumentStore`**

Implement `src/cvbuilder/document_store.py` as a class:

- Parse/serialize history JSON with corrupt → empty stacks + `logging.warning`
- Cap undo/redo to `MAX_HISTORY = 50`
- `restore_pin` always auto-pins current state as `before-restore:<pin_id>` before overwriting
- Enforce one master via upsert (UPDATE if exists, else INSERT)
- Raise `ValueError` / `KeyError` for missing documents/pins (no broad `Exception`)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_document_store.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/document_store.py src/cvbuilder/database.py tests/test_document_store.py
git commit -m "feat(db): add DocumentStore with history and pins"
```

---

### Task 3: Bootstrap migrate from filesystem YAML

**Files:**
- Modify: `src/cvbuilder/document_store.py`
- Modify: `tests/test_document_store.py`

**Interfaces:**
- Produces:
  ```python
  class DocumentStore:
      def bootstrap_from_filesystem(
          self,
          repo_root: Path,
          *,
          history_path: Optional[Path] = None,
      ) -> dict[str, Any]:
          """Import master/variants/history once when DB documents are empty.

          Returns counts: ``{"master": 0|1, "variants": N, "history": 0|1}``.
          No-ops when a master document already exists.
          """
  ```

- [ ] **Step 1: Write failing bootstrap tests**

Append to `tests/test_document_store.py`:

```python
class TestBootstrap:
    """One-time import from on-disk YAML into the database."""

    def test_bootstrap_imports_master_and_variants(
        self, tmp_path: Path
    ) -> None:
        repo = tmp_path / "repo"
        (repo / "cv" / "web").mkdir(parents=True)
        (repo / "cv" / "variants" / "demo").mkdir(parents=True)
        (repo / "cv" / "web" / "data.yaml").write_text(
            "bio:\n  - master\n", encoding="utf-8"
        )
        (repo / "cv" / "variants" / "demo" / "data.yaml").write_text(
            "bio:\n  - variant\n", encoding="utf-8"
        )
        store = _store(tmp_path)
        result = store.bootstrap_from_filesystem(repo)
        assert result["master"] == 1
        assert result["variants"] == 1
        assert "master" in store.get_master().content_yaml
        assert store.get_variant("demo") is not None

    def test_bootstrap_is_noop_when_master_exists(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        (repo / "cv" / "web").mkdir(parents=True)
        (repo / "cv" / "web" / "data.yaml").write_text(
            "bio:\n  - file\n", encoding="utf-8"
        )
        store = _store(tmp_path)
        store.upsert_master("bio:\n  - db\n")
        result = store.bootstrap_from_filesystem(repo)
        assert result["master"] == 0
        assert "db" in store.get_master().content_yaml
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_document_store.py::TestBootstrap -v`

Expected: FAIL (`bootstrap_from_filesystem` missing)

- [ ] **Step 3: Implement bootstrap**

- If master exists → return zeros without reading files.
- Else read `cv/web/data.yaml` if present → `upsert_master`.
- For each `cv/variants/*/data.yaml` → `upsert_variant`.
- If `data/edit-history.json` (or `history_path`) exists and history empty → load stacks into `cv_history` for master.
- Catch `OSError`, `UnicodeError`, `json.JSONDecodeError` specifically when reading history.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_document_store.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/document_store.py tests/test_document_store.py
git commit -m "feat(db): bootstrap CV documents from filesystem YAML"
```

---

### Task 4: Retarget Master editor APIs to `DocumentStore`

**Files:**
- Modify: `scripts/serve-editor.py`
- Modify: `scripts/cvweb.py` (helpers to dump/load YAML text without requiring DATA_FILE SoT; keep parse/set_leaf/structure ops)
- Modify: `tests/test_api.py`
- Modify: `tests/test_history.py`

**Interfaces:**
- Consumes: `DocumentStore.get_master` / `upsert_master` / history methods
- Produces: `/api/save`, `/api/structure`, `/api/history`, `/api/undo`, `/api/redo`, `/api/person`, and Master edit page render load content from DB after bootstrap

- [ ] **Step 1: Write / update failing API tests**

In `tests/test_api.py` fixtures, point the app at a temp DB, call bootstrap from fixture YAML, then assert:

```python
def test_save_updates_database_not_file(
    self, api_app: dict[str, Any], tmp_path: Path
) -> None:
    """Saving an edit must mutate cv_documents, not the fixture YAML path."""
    client = api_app["client"]
    cvweb = api_app["cvweb"]
    store = api_app["document_store"]
    yaml_path = api_app["data_file"]
    before_file = yaml_path.read_text(encoding="utf-8")
    master_before = store.get_master().content_yaml

    response = client.post(
        "/api/save",
        json=[{"path": "bio/0", "value": "Saved only in DB"}],
    )
    assert response.status_code == 200
    assert yaml_path.read_text(encoding="utf-8") == before_file
    assert "Saved only in DB" in store.get_master().content_yaml
    assert store.get_master().content_yaml != master_before
```

Update undo/structure tests similarly to assert DB content via `document_store` instead of `cvweb.load_data()` on the file.

Rewrite `tests/test_history.py` to exercise `DocumentStore` (or a thin `cvweb.EditHistory` adapter that delegates to the store) instead of JSON files.

- [ ] **Step 2: Run targeted tests to verify they fail**

Run: `pytest tests/test_api.py -k "save or structure or undo" -v`

Expected: FAIL (still file-backed) or fixture missing `document_store`

- [ ] **Step 3: Wire serve-editor to DocumentStore**

In `scripts/serve-editor.py`:

```python
def _document_store() -> DocumentStore:
    database = _database()
    database.ensure_schema()
    store = DocumentStore(database)
    store.bootstrap_from_filesystem(REPO_ROOT)
    return store
```

Change `_history` / save / structure / undo / redo / person / edit-page body render to:

1. Load master YAML text from `store.get_master()` (404/500 clear error if missing after bootstrap).
2. Parse with existing `cvweb` helpers (`yaml.load` / `set_leaf` / structure ops / `dump_data_text` style).
3. On mutate: `push_before_change` then `upsert_master`.
4. Never call `cvweb.write_data_text` / `save_data` on the live editor path.

Keep `cvweb` YAML helpers usable against arbitrary text (add `load_data_text(text: str)` / keep `dump_data_text` if not already) so code does not need a file on disk.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py tests/test_history.py -v`

Expected: PASS for updated cases

- [ ] **Step 5: Commit**

```bash
git add scripts/serve-editor.py scripts/cvweb.py tests/test_api.py tests/test_history.py
git commit -m "feat(editor): persist Master CV edits in SQLite"
```

---

### Task 5: Explicit export — YAML, Markdown, PDF

**Files:**
- Create: `src/cvbuilder/markdown_export.py`
- Create: `tests/test_markdown_export.py`
- Modify: `scripts/serve-editor.py` (`POST /api/export`)
- Modify: `scripts/cvweb.py` (`export_pdf` accepts document dict/text)
- Modify: `tests/test_api.py`
- Modify: `scripts/generate-cv-web.py`

**Interfaces:**
- Produces:
  ```python
  class MarkdownExporter:
      """Render a CV document dict to Markdown."""

      def render(self, data: dict[str, Any]) -> str:
          """Return Markdown for person, bio, skills, experience, education."""
  ```
  Export API:
  ```json
  POST /api/export
  {"format": "yaml"|"markdown"|"pdf", "document": "master"|"variant", "name": "...", "path": "..."}
  ```
  Defaults: `format=pdf`, `document=master` (preserves Save & Preview).

- [ ] **Step 1: Write failing tests**

`tests/test_markdown_export.py`:

```python
"""Tests for Markdown export of CV documents."""

from __future__ import annotations

from cvbuilder.markdown_export import MarkdownExporter


class TestMarkdownExporter:
    def test_includes_name_and_bio(self) -> None:
        text = MarkdownExporter().render(
            {
                "person": {"first_name": "Homer", "last_name": "Simpson"},
                "bio": ["Safety first."],
                "skills": {"technical": ["Reacteurs"], "functional": []},
                "experience": [],
                "education": [],
            }
        )
        assert "Homer Simpson" in text
        assert "Safety first." in text
```

API test:

```python
def test_export_yaml_writes_file_only_when_requested(
    self, api_app: dict[str, Any], tmp_path: Path
) -> None:
    out = tmp_path / "exported.yaml"
    response = api_app["client"].post(
        "/api/export",
        json={"format": "yaml", "path": str(out)},
    )
    assert response.status_code == 200
    assert out.is_file()
    assert "bio" in out.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_markdown_export.py tests/test_api.py -k export -v`

Expected: FAIL

- [ ] **Step 3: Implement exporter + export route**

- `MarkdownExporter.render`: headings for Profile/Skills/Experience/Education; Canadian spelling in any chrome labels if added.
- `api_export`: load document from store; branch on format:
  - `yaml` → write `content_yaml` to `path` or default `cv/web/data.yaml` (export artefact only)
  - `markdown` → write `.md` beside default or given path
  - `pdf` → render via existing Chrome path from in-memory/parsed data (temp HTML ok); default `cv/current/cv.pdf`
- Save & Preview keeps posting `/api/export` without YAML SoT writes as a side effect of PDF.
- `generate-cv-web.py`: bootstrap + load master from DB, then PDF.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_markdown_export.py tests/test_api.py -k export -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/markdown_export.py tests/test_markdown_export.py scripts/serve-editor.py scripts/cvweb.py scripts/generate-cv-web.py tests/test_api.py
git commit -m "feat(export): write YAML, Markdown, or PDF only on request"
```

---

### Task 6: Compose + variants API use DB documents

**Files:**
- Modify: `src/cvbuilder/composer.py`
- Modify: `scripts/serve-editor.py` (`/api/compose`, `/api/variants*`)
- Modify: `tests/test_composer.py`
- Modify: `tests/test_mcp_server.py` (if compose asserts YAML paths)

**Interfaces:**
- Produces:
  ```python
  class CvComposer:
      def compose(
          self,
          name: str,
          selections: list[dict[str, Any]] | list[SelectionItem],
          *,
          render_pdf: bool = False,
          export_yaml: bool = False,
      ) -> dict[str, Any]:
          """Upsert a variant document in the DB.

          When ``export_yaml`` is True, also write ``cv/variants/<name>/data.yaml``.
          When ``render_pdf`` is True, also write the variant PDF (export artefact).
          """
  ```

- [ ] **Step 1: Write failing composer test**

```python
def test_compose_stores_variant_in_database_without_yaml(
    self, tmp_path: Path
) -> None:
    # seed snippets as today, but assert:
    result = composer.compose("oncall", selections, render_pdf=False, export_yaml=False)
    assert (tmp_path / "cv" / "variants" / "oncall" / "data.yaml").exists() is False
    store = DocumentStore(database)
    variant = store.get_variant("oncall")
    assert variant is not None
    assert "person" in variant.content_yaml
```

Update default API `/api/compose` to `render_pdf=False`, `export_yaml=False` unless the client requests otherwise (keep backward-compatible query/body flags if tests/MCP need PDF).

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_composer.py -k database -v`

Expected: FAIL (still writes YAML)

- [ ] **Step 3: Implement composer DB write**

- `_load_base_data` reads master from `DocumentStore` (bootstrap first).
- After `_build_document`, dump YAML text and `upsert_variant`.
- Only mkdir/write files when `export_yaml` or `render_pdf` is True.
- `/api/variants` lists from `store.list_variants()`; delete removes DB row (+ optional leftover files).
- `/api/variants/<name>/render` becomes an export PDF for that variant document.

- [ ] **Step 4: Run composer/API variant tests**

Run: `pytest tests/test_composer.py tests/test_api.py -k variant -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/composer.py scripts/serve-editor.py tests/test_composer.py tests/test_mcp_server.py
git commit -m "feat(compose): store variants in SQLite instead of YAML folders"
```

---

### Task 7: Pins API + master import safety pin + seed from DB

**Files:**
- Modify: `scripts/serve-editor.py` (pin routes; import master confirm)
- Modify: `src/cvbuilder/importer.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_resume_to_master.py` only if import path assertions need DB
- Modify: `features/steps/app_steps.py` if Behave fixtures still assume file SoT

**Interfaces:**
- Produces:
  - `GET /api/pins?document=master`
  - `POST /api/pins` body `{"document":"master","label":"..."}`
  - `POST /api/pins/<id>/restore`
  - `DELETE /api/pins/<id>`
  - Master import confirm: `create_pin(..., f"before-import:{token}")` then patch via `upsert_master` (no `data/backups/` requirement)
  - Importer: if master document exists in DB, seed master sections from that blob; else fall back to file for bootstrap compatibility

- [ ] **Step 1: Write failing API tests**

```python
def test_pin_create_and_restore(self, api_app: dict[str, Any]) -> None:
    client = api_app["client"]
    store = api_app["document_store"]
    created = client.post("/api/pins", json={"document": "master", "label": "v1"})
    assert created.status_code == 200
    pin_id = created.get_json()["id"]
    client.post("/api/save", json=[{"path": "bio/0", "value": "After pin"}])
    restored = client.post(f"/api/pins/{pin_id}/restore")
    assert restored.status_code == 200
    assert "After pin" not in store.get_master().content_yaml

def test_confirm_master_mode_updates_db_and_pins(
    self, api_app: dict[str, Any]
) -> None:
    # upload + confirm mode=master
    # assert master document content changed in DB
    # assert a before-import:* pin exists
    # assert fixture data.yaml file unchanged unless exported
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -k "pin or confirm_master" -v`

Expected: FAIL

- [ ] **Step 3: Implement routes and importer/master confirm**

- Pin routes thin wrappers over `DocumentStore`.
- Import master: replace `backup + save_data` with pin + `upsert_master(dump(patched))`.
- Importer accepts optional `content_yaml: str` or reads via `DocumentStore`.
- Update Behave env to isolate a temp DB the same way it copies `data.yaml`.

- [ ] **Step 4: Run API + behave smoke if available**

Run: `pytest tests/test_api.py tests/test_resume_import.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/serve-editor.py src/cvbuilder/importer.py tests/test_api.py tests/test_resume_import.py features/steps/app_steps.py features/environment.py
git commit -m "feat(pins): add pin APIs and DB-backed master import safety"
```

---

### Task 8: Version bump, README, residual test sweep

**Files:**
- Modify: `VERSION` → `0.2.13.0`
- Modify: `src/cvbuilder/__init__.py` → `__version__ = "0.2.13.0"`
- Modify: `README.md` (DB is SoT; export YAML/MD/PDF on demand; bootstrap note)
- Modify: any remaining tests still monkeypatching `DATA_FILE` as live SoT without a store

- [ ] **Step 1: Update docs and version**

README bullet points:

- Master and variant CVs live in SQLite (`cv_documents`).
- Undo history is transitory in `cv_history`; pins freeze content + stacks.
- Export explicitly to YAML, Markdown, or PDF.
- First run bootstraps from existing `cv/web/data.yaml` if the DB has no master.

- [ ] **Step 2: Full test suite**

Run: `pytest tests/ -v`

Expected: PASS (fix any stragglers that still assume file SoT)

- [ ] **Step 3: Commit**

```bash
git add VERSION src/cvbuilder/__init__.py README.md tests/
git commit -m "chore(release): bump to 0.2.13.0 for DB-primary documents"
```

---

## Self-review checklist (plan author)

1. **Spec coverage:** Documents / history / pins / bootstrap / editor SoT / export yaml+md+pdf / compose variants in DB / import pin / seed prefer DB / tests / version — each mapped to a task.
2. **Placeholders:** None intentionally left as TBD.
3. **Type consistency:** `DocumentStore`, `CvDocument`, `CvPin`, `MarkdownExporter`, compose flags `export_yaml` / `render_pdf` used consistently across tasks.

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-05-db-primary-cv-documents.md`. Two execution options:

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session using executing-plans, with checkpoints for review

Which approach?
