# Docker Persistent Data Volume Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** Persist SQLite, uploads, imports, variant exports, and preview artefacts on a named Docker volume at `/data` via `CV_DATA_ROOT`.

**Architecture:** Resolve writable paths under `CV_DATA_ROOT` (default `/data` in Docker, else `REPO_ROOT`). Compose mounts `cv_data:/data`. Entrypoint creates dirs and seeds the DB when missing.

**Tech Stack:** Docker Compose, shell entrypoint, Flask path config, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-05-docker-data-volume-design.md`
- Canadian spelling in user-facing docs
- Type hints + pep257 on new Python helpers/classes
- No broad `except Exception`
- Feature version bump
- Keep `.:/app` bind mount for local code

---

### Task 1: `CV_DATA_ROOT` path helpers + wire serve-editor

**Files:**
- Create or extend: `src/cvbuilder/paths.py` (or helpers in `cvweb.py`) with a small class `DataPaths`
- Modify: `scripts/serve-editor.py`, `scripts/generate-cv-web.py`, `docker-entrypoint.sh`, `Dockerfile`, `docker-compose.yml`
- Test: `tests/test_data_paths.py`
- Docs: `README.md`
- Version: `VERSION`, `src/cvbuilder/__init__.py`

**Produces:**
```python
class DataPaths:
    def __init__(self, repo_root: Path, data_root: Optional[Path] = None) -> None: ...
    @property
    def root(self) -> Path: ...
    @property
    def snippets_db(self) -> Path: ...
    @property
    def assets_images(self) -> Path: ...
    @property
    def imports(self) -> Path: ...
    @property
    def variants(self) -> Path: ...
    @property
    def preview_pdf(self) -> Path: ...
    def ensure_directories(self) -> None: ...
```

- [ ] Resolve `CV_DATA_ROOT` / `SNIPPETS_DB` / `RESUME_IMPORTS_DIR`
- [ ] serve-editor uses DataPaths for DB, ASSETS_DIR (images), IMPORTS, VARIANTS, PREVIEW
- [ ] Serve `/assets/images/*` from data root; branding from repo
- [ ] Entrypoint mkdir + seed when DB missing using `SNIPPETS_DB`
- [ ] Compose: `cv_data:/data`, env `CV_DATA_ROOT=/data`, `SNIPPETS_DB=/data/snippets.db`, `RESUME_IMPORTS_DIR=/data/imports`
- [ ] Dockerfile `ENV CV_DATA_ROOT=/data`
- [ ] Tests for path resolution
- [ ] README + feature bump
- [ ] Rebuild container and smoke `/api` or health
