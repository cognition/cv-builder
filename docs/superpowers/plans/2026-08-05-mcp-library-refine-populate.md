# MCP Library Populate & Refine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MCP tools so an assistant can audit the Content library and populate or refine it via batch upsert/delete with dry-run defaults.

**Architecture:** A `LibraryOps` service class owns audit, batch upsert, and batch delete against `SnippetDatabase`. MCP tools in `mcp_server.py` are thin wrappers. The LLM rewrites content; tools only inspect and persist.

**Tech Stack:** Python 3.12, SQLite via `SnippetDatabase`, FastMCP (`mcp.server.fastmcp`), pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-05-mcp-library-refine-populate-design.md`
- Canadian spelling in user-facing copy and instructions
- Type hints + pep257 docstrings on all new public Python classes/methods
- Prefer specific exceptions (no broad `except Exception` / Pylint W0718)
- Prefer classes over free functions for new Python modules (`LibraryOps`)
- TDD: failing test first for every behaviour
- Version scheme: `Major.Minor.feature.fix` — bump feature when this ships (`0.2.20.1` → `0.2.21.0`)
- Existing single-snippet MCP tools and compose/match behaviour must stay unchanged
- Batch mutators default `dry_run=True`
- No server-side LLM, no resume PDF MCP tools, no Working Draft sync in this plan

## File structure

| File | Responsibility |
| --- | --- |
| `src/cvbuilder/library_ops.py` | `LibraryOps`: `audit`, `upsert_snippets`, `delete_snippets` |
| `src/cvbuilder/mcp_server.py` | Wire three tools; update FastMCP instructions |
| `tests/test_library_ops.py` | Unit tests for `LibraryOps` (primary) |
| `tests/test_mcp_server.py` | Thin smoke that MCP wrappers call through |
| `README.md` | Mention audit / batch upsert / dry-run in MCP section |
| `VERSION`, `src/cvbuilder/__init__.py` | Feature bump to `0.2.21.0` |

---

### Task 1: `LibraryOps.audit` — health report

**Files:**
- Create: `src/cvbuilder/library_ops.py`
- Create: `tests/test_library_ops.py`

**Interfaces:**
- Consumes: `SnippetDatabase.list_snippets`, `Snippet.variant_for`, `DetailLevel`
- Produces:

```python
VALID_CATEGORIES: frozenset[str] = frozenset(
    {"bio", "skill", "experience", "education", "part", "requirement"}
)
DETAIL_LEVELS: tuple[str, ...] = ("brief", "standard", "detailed")
MIN_VARIANT_CHARS: int = 20
MAX_VARIANT_CHARS: int = 8000

class LibraryOps:
    def __init__(self, database: SnippetDatabase) -> None: ...

    def audit(
        self,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        search: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return library health report (counts, gaps, outliers, dupes)."""
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_library_ops.py`:

```python
"""Tests for Content library audit and batch ops."""

from __future__ import annotations

from pathlib import Path

import pytest

from cvbuilder.database import SnippetDatabase
from cvbuilder.library_ops import LibraryOps
from cvbuilder.models import Snippet, SnippetVariant


@pytest.fixture
def database(tmp_path: Path) -> SnippetDatabase:
    """Isolated empty snippet database."""
    path = tmp_path / "snippets.db"
    db = SnippetDatabase(path)
    db.ensure_schema()
    return db


def _create(
    database: SnippetDatabase,
    *,
    category: str,
    content: str,
    detail_level: str = "standard",
    company: str | None = None,
    role: str | None = None,
    heading: str | None = None,
    tags: list[str] | None = None,
) -> int:
    """Insert one snippet with a single variant; return id."""
    snippet_id = database.create_snippet(
        Snippet(
            category=category,
            company=company,
            role=role,
            heading=heading,
            tags=tags or [],
        )
    )
    database.upsert_variant(
        SnippetVariant(
            snippet_id=snippet_id,
            detail_level=detail_level,
            content=content,
        )
    )
    return snippet_id


class TestAuditLibrary:
    """Read-only library health report."""

    def test_reports_missing_detail_levels(self, database: SnippetDatabase) -> None:
        """Snippets lacking brief/detailed appear under missing_detail_levels."""
        sid = _create(database, category="bio", content="A" * 40)
        report = LibraryOps(database).audit()
        entry = next(e for e in report["missing_detail_levels"] if e["id"] == sid)
        assert set(entry["missing"]) == {"brief", "detailed"}
        assert entry["category"] == "bio"

    def test_reports_empty_tags(self, database: SnippetDatabase) -> None:
        """Untagged snippets appear under empty_tags."""
        sid = _create(database, category="skill", content="A" * 40, tags=[])
        report = LibraryOps(database).audit()
        assert any(e["id"] == sid for e in report["empty_tags"])

    def test_reports_sparse_experience_heading(self, database: SnippetDatabase) -> None:
        """Experience without heading is flagged."""
        sid = _create(
            database,
            category="experience",
            content="A" * 40,
            company="Acme",
            role="Eng",
            heading=None,
        )
        report = LibraryOps(database).audit()
        assert any(e["id"] == sid for e in report["sparse_headings"])

    def test_reports_length_outliers(self, database: SnippetDatabase) -> None:
        """Very short variant content is flagged as too_short."""
        sid = _create(database, category="skill", content="x", tags=["t"])
        report = LibraryOps(database).audit()
        hits = [e for e in report["length_outliers"] if e["id"] == sid]
        assert hits
        assert hits[0]["reason"] == "too_short"

    def test_duplicate_candidates_same_company_role(
        self, database: SnippetDatabase
    ) -> None:
        """Two experience rows with same company+role are duplicate candidates."""
        a = _create(
            database,
            category="experience",
            content="A" * 40,
            company="Acme",
            role="Engineer",
            heading="One",
            tags=["x"],
        )
        b = _create(
            database,
            category="experience",
            content="B" * 40,
            company="Acme",
            role="Engineer",
            heading="Two",
            tags=["x"],
        )
        report = LibraryOps(database).audit()
        found = False
        for group in report["duplicate_candidates"]:
            if set(group["ids"]) == {a, b}:
                assert group["reason"] == "same_company_role"
                found = True
        assert found

    def test_counts_by_category(self, database: SnippetDatabase) -> None:
        """Report includes per-category counts."""
        _create(database, category="bio", content="A" * 40, tags=["a"])
        _create(database, category="skill", content="B" * 40, tags=["b"])
        report = LibraryOps(database).audit()
        assert report["counts_by_category"]["bio"] == 1
        assert report["counts_by_category"]["skill"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_library_ops.py::TestAuditLibrary -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'cvbuilder.library_ops'`.

- [ ] **Step 3: Implement `LibraryOps.audit`**

Create `src/cvbuilder/library_ops.py` with module constants, `LibraryOps.__init__`, and `audit()` as specified in the design: `counts_by_category`, `missing_detail_levels`, `empty_tags`, `sparse_headings` (experience/education without heading), `length_outliers` (`too_short` / `too_long` using `MIN_VARIANT_CHARS` / `MAX_VARIANT_CHARS`), `duplicate_candidates` (`same_company_role` for experience with matching casefolded company+role; `identical_content` via SHA-256 of stripped variant text). Use `hashlib` and `collections.defaultdict`. Prefer classes; pep257 docstrings; no broad `except Exception`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_library_ops.py::TestAuditLibrary -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/library_ops.py tests/test_library_ops.py
git commit -m "$(cat <<'EOF'
feat(mcp): add LibraryOps.audit for content library health

EOF
)"
```

---

### Task 2: `LibraryOps.upsert_snippets` with dry-run

**Files:**
- Modify: `src/cvbuilder/library_ops.py`
- Modify: `tests/test_library_ops.py`

**Interfaces:**
- Consumes: `create_snippet`, `update_snippet`, `upsert_variant`, `get_snippet`
- Produces:

```python
def upsert_snippets(
    self,
    snippets: list[dict[str, Any]],
    dry_run: bool = True,
) -> dict[str, Any]:
    """Batch create/update snippets; dry_run defaults to True."""
```

Result keys: `dry_run`, `created`, `updated`, `errors`, `counts` (`created` / `updated` / `errors`).

Create items need `category` + ≥1 non-empty variant; update by `id` may change metadata and/or variants. Invalid items → per-item error; batch continues. Tags on update: present → replace; omitted → keep. Metadata fields omitted on update keep current values (track `has_company` / `has_role` / `has_heading` from raw keys).

- [ ] **Step 1: Write the failing tests**

Append `TestUpsertSnippets` to `tests/test_library_ops.py` covering:

1. `dry_run=True` plans create, DB stays empty
2. `dry_run=False` creates with multiple variants
3. Update by id changes heading/tags and upserts `detailed`; company unchanged when omitted
4. Partial batch: invalid category errors at index 0; valid bio still created
5. Create without variants → error, no create

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_library_ops.py::TestUpsertSnippets -v`

Expected: FAIL (`AttributeError: ... upsert_snippets`).

- [ ] **Step 3: Implement upsert**

Add `upsert_snippets`, `_normalise_upsert_item`, `_summarise_item`, `_apply_create`, `_apply_update` on `LibraryOps`. Validate categories against `VALID_CATEGORIES` and levels against `DETAIL_LEVELS`. Catch only `ValueError` from normalisation for per-item errors. On create, `tags is None` → `[]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_library_ops.py::TestUpsertSnippets -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/library_ops.py tests/test_library_ops.py
git commit -m "$(cat <<'EOF'
feat(mcp): batch upsert_snippets with dry_run default

EOF
)"
```

---

### Task 3: `LibraryOps.delete_snippets` with dry-run

**Files:**
- Modify: `src/cvbuilder/library_ops.py`
- Modify: `tests/test_library_ops.py`

**Interfaces:**
- Produces:

```python
def delete_snippets(
    self,
    snippet_ids: list[int],
    dry_run: bool = True,
) -> dict[str, Any]:
    """Batch delete by id; dry_run defaults to True."""
```

Result keys: `dry_run`, `deleted`, `errors`, `counts` (`deleted` / `errors`).

- [ ] **Step 1: Write the failing tests**

Append `TestDeleteSnippets` (dry-run keeps row; apply deletes; unknown id errors) and `TestAuditRefinePlaybook.test_fill_missing_brief` (audit → upsert brief → audit no longer lists `brief` for that id).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_library_ops.py::TestDeleteSnippets -v`

Expected: FAIL (`no attribute 'delete_snippets'`).

- [ ] **Step 3: Implement `delete_snippets`**

For each id: invalid int → error; missing snippet → error; else append to `deleted` with summary; call `delete_snippet` only when `not dry_run`.

- [ ] **Step 4: Run full library_ops suite**

Run: `pytest tests/test_library_ops.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/library_ops.py tests/test_library_ops.py
git commit -m "$(cat <<'EOF'
feat(mcp): batch delete_snippets and audit→refine smoke test

EOF
)"
```

---

### Task 4: Wire MCP tools + instructions + docs + version

**Files:**
- Modify: `src/cvbuilder/mcp_server.py`
- Modify: `tests/test_mcp_server.py`
- Modify: `README.md`
- Modify: `VERSION` → `0.2.21.0`
- Modify: `src/cvbuilder/__init__.py` → `__version__ = "0.2.21.0"`

**Interfaces:**

```python
def audit_library(...) -> dict[str, Any]: ...
def upsert_snippets(snippets: list[dict[str, Any]], dry_run: bool = True) -> dict[str, Any]: ...
def delete_snippets(snippet_ids: list[int], dry_run: bool = True) -> dict[str, Any]: ...
```

- [ ] **Step 1: Write failing MCP wrapper tests**

Append `TestLibraryOpsTools` to `tests/test_mcp_server.py`:

- `audit_library` returns skill count after `create_snippet`
- `upsert_snippets` without `dry_run` arg defaults dry and does not write
- `delete_snippets(..., dry_run=False)` removes the row

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mcp_server.py::TestLibraryOpsTools -v`

Expected: FAIL (tools missing).

- [ ] **Step 3: Wire tools and docs**

1. Import `LibraryOps` from `cvbuilder.library_ops`
2. Expand FastMCP `instructions` with populate/refine playbook (audit → draft → `upsert_snippets` dry_run then apply; `delete_snippets` for removals; single CRUD still for one-offs)
3. Add `@mcp.tool()` wrappers calling `LibraryOps(_database())`
4. README MCP section: bullet for `audit_library`, `upsert_snippets` / `delete_snippets` (dry-run default)
5. Bump `VERSION` and `__version__` to `0.2.21.0`

- [ ] **Step 4: Run suites + version check**

```bash
pytest tests/test_library_ops.py tests/test_mcp_server.py -v
grep -E '0\.2\.21\.0' VERSION src/cvbuilder/__init__.py
```

Expected: PASS; both files show `0.2.21.0`.

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/mcp_server.py tests/test_mcp_server.py README.md VERSION src/cvbuilder/__init__.py
git commit -m "$(cat <<'EOF'
feat(mcp): expose audit_library and batch upsert/delete tools

Bump to 0.2.21.0 for Content library populate/refine via MCP.

EOF
)"
```

---

## Spec coverage self-review

| Spec requirement | Task |
| --- | --- |
| `audit_library` report fields | Task 1 |
| `upsert_snippets` + dry_run default | Task 2 |
| `delete_snippets` + dry_run default | Task 3 |
| Per-item errors, batch continues | Task 2 |
| MCP instructions playbooks | Task 4 |
| README mention | Task 4 |
| Tests: audit, dry-run, apply, partial, playbook | Tasks 1–3 |
| Feature version bump | Task 4 |
| No server LLM / PDF / draft sync | Out of scope |

## Placeholder scan

Concrete tests and behaviours listed; no TBD steps.

## Type consistency

`LibraryOps` method names match MCP wrappers; result keys match the design spec.
