# DEMO Env Var First-Boot Content Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On Docker first boot, load Homer demo snippets and master CV only when `DEMO=1`; otherwise create an empty schema DB with no master document.

**Architecture:** Gate seeding in `docker-entrypoint.sh`. Blank boots call a small Python helper that runs `ensure_schema` only and export `SKIP_FS_BOOTSTRAP=1`. `DocumentStore.bootstrap_from_filesystem` reads that env var so web and MCP both skip importing `cv/web/data.yaml`. Existing DB files are never wiped.

**Tech Stack:** Python 3.12, SQLite (`SnippetDatabase` / `DocumentStore`), POSIX `docker-entrypoint.sh`, Docker Compose, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-06-demo-env-var-design.md`
- Canadian spelling in user-facing copy
- Type hints + pep257 docstrings on all new public Python classes/methods
- Prefer specific exceptions (no broad `except Exception` / Pylint W0718)
- Prefer classes over free functions for new Python modules
- TDD: failing test first for every behaviour
- Version scheme: `Major.Minor.feature.fix` — bump feature when this ships (`0.2.24.0` → `0.2.25.0`)
- Do not change `/api/seed` or MCP seed behaviour
- Do not default `DEMO=1` in the Dockerfile

## File structure

| File | Responsibility |
| --- | --- |
| `src/cvbuilder/document_store.py` | Honour `SKIP_FS_BOOTSTRAP=1` in `bootstrap_from_filesystem` |
| `src/cvbuilder/first_boot.py` | `FirstBoot.prepare_database` — demo seed vs blank schema |
| `docker-entrypoint.sh` | Call `FirstBoot` based on `DEMO`; export `SKIP_FS_BOOTSTRAP` when blank |
| `docker-compose.yml` | Document optional `DEMO: "1"` |
| `README.md` | Document blank vs `DEMO=1` first boot |
| `tests/test_document_store.py` | Unit test for skip-bootstrap |
| `tests/test_first_boot.py` | Unit tests for blank vs demo prepare |
| `VERSION`, `src/cvbuilder/__init__.py` | Feature bump to `0.2.25.0` |

---

### Task 1: Skip filesystem bootstrap when `SKIP_FS_BOOTSTRAP=1`

**Files:**
- Modify: `src/cvbuilder/document_store.py`
- Modify: `tests/test_document_store.py`
- Test: `tests/test_document_store.py::TestBootstrap::test_bootstrap_skipped_when_env_set`

**Interfaces:**
- Consumes: existing `DocumentStore.bootstrap_from_filesystem(repo_root, *, history_path=None) -> dict[str, Any]`
- Produces: same method; when `os.environ.get("SKIP_FS_BOOTSTRAP") == "1"`, returns `{"master": 0, "variants": 0, "history": 0}` without reading YAML

- [ ] **Step 1: Write the failing test**

Append to `TestBootstrap` in `tests/test_document_store.py`:

```python
def test_bootstrap_skipped_when_env_set(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SKIP_FS_BOOTSTRAP=1 leaves the store empty even if YAML exists."""
    monkeypatch.setenv("SKIP_FS_BOOTSTRAP", "1")
    repo = tmp_path / "repo"
    (repo / "cv" / "web").mkdir(parents=True)
    (repo / "cv" / "web" / "data.yaml").write_text(
        "bio:\n  - master\n", encoding="utf-8"
    )
    store = _store(tmp_path)
    result = store.bootstrap_from_filesystem(repo)
    assert result == {"master": 0, "variants": 0, "history": 0}
    assert store.get_working() is None
```

Add `MonkeyPatch` to the TYPE_CHECKING import block if missing:

```python
if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
```

(Keep using `pytest.MonkeyPatch` in the signature; the TYPE_CHECKING import satisfies the project convention.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_document_store.py::TestBootstrap::test_bootstrap_skipped_when_env_set -v`

Expected: FAIL — master is imported (`result["master"] == 1`) because the env guard is missing.

- [ ] **Step 3: Implement the guard**

In `src/cvbuilder/document_store.py`, add `import os` near the other imports. At the top of `bootstrap_from_filesystem`, after the docstring and before the existing `get_working()` check:

```python
if os.environ.get("SKIP_FS_BOOTSTRAP") == "1":
    return {"master": 0, "variants": 0, "history": 0}
```

Leave all other bootstrap logic unchanged. Do not change `scripts/web_state.py` or `mcp_server.py` — both already call `bootstrap_from_filesystem`, so they inherit the guard.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_document_store.py::TestBootstrap -v`

Expected: PASS for all bootstrap tests, including the new skip test.

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/document_store.py tests/test_document_store.py
git commit -m "$(cat <<'EOF'
feat(store): honour SKIP_FS_BOOTSTRAP during filesystem bootstrap

EOF
)"
```

---

### Task 2: `FirstBoot.prepare_database` for blank vs demo seed

**Files:**
- Create: `src/cvbuilder/first_boot.py`
- Create: `tests/test_first_boot.py`
- Test: `tests/test_first_boot.py`

**Interfaces:**
- Consumes: `SnippetDatabase.ensure_schema`, `SnippetImporter.seed`
- Produces:
  ```python
  class FirstBoot:
      """Prepare the SQLite store on container / volume first boot."""

      @staticmethod
      def prepare_database(
          db_path: Path,
          repo_root: Path,
          *,
          demo: bool,
      ) -> dict[str, Any]:
          """Create schema; optionally seed demo snippets.

          Args:
              db_path: Path to `snippets.db`.
              repo_root: Repository root containing `cv/web/data.yaml`
                  and `content/`.
              demo: When True, run `SnippetImporter.seed()`. When False,
                  create schema only (no snippets).

          Returns:
              ``{"demo": bool, "snippet_total": int, "stats": dict}``.
              ``stats`` is empty when ``demo`` is False.
          """
  ```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_first_boot.py`:

```python
"""Unit tests for first-boot blank vs demo database preparation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.first_boot import FirstBoot

if TYPE_CHECKING:
    pass


def _mini_repo(tmp_path: Path) -> Path:
    """Create a tiny repo with Homer-like YAML and one markdown snippet."""
    repo = tmp_path / "repo"
    (repo / "cv" / "web").mkdir(parents=True)
    (repo / "content" / "parts").mkdir(parents=True)
    (repo / "cv" / "web" / "data.yaml").write_text(
        "person:\n  first_name: Homer\nbio:\n  - Safety first.\n"
        "skills:\n  technical: []\n  functional: []\n"
        "experience: []\neducation: []\n",
        encoding="utf-8",
    )
    (repo / "content" / "parts" / "intro.md").write_text(
        "# Intro\n\n## Alternate bio\n\nA longer intro paragraph.\n",
        encoding="utf-8",
    )
    return repo


class TestFirstBoot:
    """Blank vs demo first-boot preparation."""

    def test_blank_creates_schema_with_zero_snippets(
        self, tmp_path: Path
    ) -> None:
        """DEMO-off path creates DB schema and no snippets."""
        repo = _mini_repo(tmp_path)
        db_path = tmp_path / "data" / "snippets.db"
        result = FirstBoot.prepare_database(db_path, repo, demo=False)
        assert result["demo"] is False
        assert result["snippet_total"] == 0
        assert db_path.is_file()
        database = SnippetDatabase(db_path)
        assert database.list_snippets() == []
        assert DocumentStore(database).get_working() is None

    def test_demo_seeds_snippets_from_yaml(
        self, tmp_path: Path
    ) -> None:
        """DEMO-on path seeds at least the YAML bio snippet."""
        repo = _mini_repo(tmp_path)
        db_path = tmp_path / "data" / "snippets.db"
        result = FirstBoot.prepare_database(db_path, repo, demo=True)
        assert result["demo"] is True
        assert result["snippet_total"] >= 1
        database = SnippetDatabase(db_path)
        snippets = database.list_snippets()
        assert len(snippets) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_first_boot.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'cvbuilder.first_boot'`.

- [ ] **Step 3: Implement `FirstBoot`**

Create `src/cvbuilder/first_boot.py`:

```python
"""First-boot preparation of the SQLite store for Docker / volume starts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cvbuilder.database import SnippetDatabase
from cvbuilder.importer import SnippetImporter


class FirstBoot:
    """Prepare the SQLite store on container / volume first boot."""

    @staticmethod
    def prepare_database(
        db_path: Path,
        repo_root: Path,
        *,
        demo: bool,
    ) -> dict[str, Any]:
        """Create schema; optionally seed demo snippets.

        Args:
            db_path: Path to ``snippets.db``.
            repo_root: Repository root containing ``cv/web/data.yaml``
                and ``content/``.
            demo: When True, run ``SnippetImporter.seed()``. When False,
                create schema only (no snippets).

        Returns:
            ``{"demo": bool, "snippet_total": int, "stats": dict}``.
            ``stats`` is empty when ``demo`` is False.
        """
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        database = SnippetDatabase(db_path)
        if not demo:
            database.ensure_schema()
            return {"demo": False, "snippet_total": 0, "stats": {}}

        importer = SnippetImporter(database=database, repo_root=Path(repo_root))
        stats = importer.seed()
        return {
            "demo": True,
            "snippet_total": sum(stats.values()),
            "stats": stats,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_first_boot.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/first_boot.py tests/test_first_boot.py
git commit -m "$(cat <<'EOF'
feat(bootstrap): add FirstBoot blank vs demo database prepare

EOF
)"
```

---

### Task 3: Wire `DEMO` into `docker-entrypoint.sh`

**Files:**
- Modify: `docker-entrypoint.sh`
- Test: manual logic covered by Task 2 unit tests; smoke-check via shell syntax

**Interfaces:**
- Consumes: `FirstBoot.prepare_database`; env `DEMO`, `SNIPPETS_DB`, `CV_DATA_ROOT`
- Produces: On missing DB — demo seed when `DEMO=1`, else blank schema + `export SKIP_FS_BOOTSTRAP=1`

- [ ] **Step 1: Replace the seed block in `docker-entrypoint.sh`**

Replace the existing block:

```sh
if [ ! -f "$DB_PATH" ]; then
  echo "No snippet database at ${DB_PATH}; seeding from data.yaml and content/…"
  python3 -m cvbuilder.importer
fi
```

with:

```sh
if [ ! -f "$DB_PATH" ]; then
  if [ "${DEMO:-}" = "1" ]; then
    echo "No snippet database at ${DB_PATH}; DEMO=1 — seeding Homer demo from data.yaml and content/…"
    python3 -c "
from pathlib import Path
from cvbuilder.first_boot import FirstBoot
result = FirstBoot.prepare_database(
    Path('${DB_PATH}'),
    Path('/app'),
    demo=True,
)
print(f\"Seeded {result['snippet_total']} demo snippets into ${DB_PATH}\")
"
  else
    echo "No snippet database at ${DB_PATH}; DEMO unset — creating blank schema (no Homer demo)…"
    python3 -c "
from pathlib import Path
from cvbuilder.first_boot import FirstBoot
FirstBoot.prepare_database(
    Path('${DB_PATH}'),
    Path('/app'),
    demo=False,
)
print(f\"Created blank database at ${DB_PATH}\")
"
    export SKIP_FS_BOOTSTRAP=1
  fi
fi
```

Notes:

- Keep `set -eu` and the rest of the entrypoint unchanged.
- Use `/app` as `repo_root` (image `WORKDIR` / compose mount).
- Only export `SKIP_FS_BOOTSTRAP=1` on the blank first-boot path — never clear it if an operator already set it, and never set it when `DEMO=1`.

- [ ] **Step 2: Syntax-check the entrypoint**

Run: `sh -n docker-entrypoint.sh`

Expected: exit code 0, no output.

- [ ] **Step 3: Commit**

```bash
git add docker-entrypoint.sh
git commit -m "$(cat <<'EOF'
feat(docker): gate first-boot Homer seed behind DEMO=1

EOF
)"
```

---

### Task 4: Document `DEMO` and bump the feature version

**Files:**
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `VERSION`
- Modify: `src/cvbuilder/__init__.py`

**Interfaces:**
- Consumes: behaviour from Tasks 1–3
- Produces: documented `DEMO` / blank default; version `0.2.25.0`

- [ ] **Step 1: Update compose environment docs**

In `docker-compose.yml`, under `environment:`, add a commented optional demo flag (do not enable by default):

```yaml
      # Set DEMO to "1" for Homer Simpson sample snippets + master CV
      # on first boot only (ignored when /data/snippets.db already exists).
      # DEMO: "1"
```

- [ ] **Step 2: Update README Docker section**

After the paragraph that ends with “omit that mount for image-only runs.” in `### Docker`, add:

```markdown
First boot of an empty volume creates a blank SQLite database (schema only,
no master CV) unless you set `DEMO=1` in the compose `environment` block.
With `DEMO=1`, the container seeds the synthetic Homer Simpson snippets and
allows bootstrapping the master CV from `cv/web/data.yaml`. Existing
volumes are never wiped when `DEMO` changes.
```

Also update the opening “Ships with…” paragraph so it matches blank-by-default Docker behaviour:

Replace:

```markdown
Ships with a fully synthetic example person (Homer Simpson) in
`cv/web/data.yaml` and `content/` — replace it with your own before you
rely on this for real. Nothing in this repo is anyone's real personal data.
```

with:

```markdown
Includes a fully synthetic example person (Homer Simpson) in
`cv/web/data.yaml` and `content/` for local seeding and optional Docker
demo mode (`DEMO=1`). Docker first boot is blank unless `DEMO=1`. Replace
the sample with your own before you rely on this for real. Nothing in this
repo is anyone's real personal data.
```

Update the Document storage paragraph similarly — note that filesystem
bootstrap of `data.yaml` is skipped when `SKIP_FS_BOOTSTRAP=1` (set
automatically on blank Docker first boot):

After “On first run, if the database has no master CV row, the app
bootstraps that row from the shipped `cv/web/data.yaml`”, append:
“ unless `SKIP_FS_BOOTSTRAP=1` (blank Docker first boot).”

- [ ] **Step 3: Bump version**

Set both to `0.2.25.0`:

- `VERSION`
- `src/cvbuilder/__init__.py` → `__version__ = "0.2.25.0"`

- [ ] **Step 4: Run full related tests**

Run:

```bash
pytest tests/test_document_store.py::TestBootstrap tests/test_first_boot.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml README.md VERSION src/cvbuilder/__init__.py
git commit -m "$(cat <<'EOF'
docs(docker): document DEMO=1 first-boot and bump to 0.2.25.0

EOF
)"
```

---

## Spec coverage checklist

| Spec requirement | Task |
| --- | --- |
| `DEMO=1` seeds Homer on first boot | Task 2 + 3 |
| Unset/other → empty snippets + no master | Task 1 + 2 + 3 |
| Existing volume never wiped | Task 3 (only runs when DB missing) |
| `SKIP_FS_BOOTSTRAP` shared by web/MCP | Task 1 (guard inside `DocumentStore`) |
| Compose / README document `DEMO` | Task 4 |
| Dockerfile does not default `DEMO=1` | Task 4 (no Dockerfile `ENV DEMO`) |
| `/api/seed` unchanged | No task touches it |
| Feature version bump | Task 4 |
| Unit: skip bootstrap | Task 1 |
| Unit: blank vs demo prepare | Task 2 |

## Self-review notes

- No placeholders / TBDs.
- `FirstBoot.prepare_database` signatures match entrypoint usage in Task 3.
- `SKIP_FS_BOOTSTRAP` exact string `"1"` matches the design and Task 1 test.
- Version floor copied from tip at plan time: `0.2.24.0` → `0.2.25.0`.
