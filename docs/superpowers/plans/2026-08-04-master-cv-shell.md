# Master CV Inside Studio Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `/cv/web/edit` a Studio shell page so the left nav stays visible while editing the contenteditable Master CV, with Save/Preview/Undo in the sticky header and PDF preview as an overlay.

**Architecture:** Extract the CV markup into `cv/web/cv_body.html.j2`. Standalone `template.html.j2` still wraps it for PDF export. A new `pages/master.html` extends the shell, injects a Python-rendered body under `.cv-document`, and hosts header actions + preview overlay. Scope edit/print CSS under `.cv-document` so Studio `aside`/`main` do not clash with the CV sidebar.

**Tech Stack:** Jinja2, Flask (`serve-editor.py` / `cvweb.py`), existing `editor.js` / `style.css`, Behave, pytest.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-04-master-cv-shell-design.md`
- Keep contenteditable data-paths and `/api/save|structure|history|undo|redo` contracts unchanged
- PDF export HTML must contain **no** Studio shell / brand nav
- Canadian spelling in user-facing copy
- Type hints + pep257 on new/changed Python public functions
- No bare `except Exception`
- TDD: failing Behave/pytest first where behaviour is asserted
- Version: bump feature component when this ships (`0.2.11.0` → `0.2.12.0` unless VERSION has moved)

## File structure

| File | Responsibility |
| --- | --- |
| `cv/web/cv_body.html.j2` | Printable/editable CV body only (macros + hero/content) |
| `cv/web/template.html.j2` | Standalone print wrapper; includes body; no Studio chrome |
| `cv/web/src/pages/master.html` | Shell Master page + header actions + preview overlay |
| `cv/web/src/pages/master.css` | Overlay, main scroll, header action layout |
| `cv/web/style.css` | Scope edit-mode / document rules under `.cv-document` |
| `cv/web/editor.js` | Target header toolbar; preview overlay class on document/shell |
| `scripts/cvweb.py` | `render_cv_body()`; `render_html()` uses wrapper + include |
| `scripts/serve-editor.py` | `edit_page()` → `_render_page("pages/master.html", …)` |
| `features/master_cv.feature` (+ steps if needed) | Assert shell nav + master active on edit |
| `VERSION`, `src/cvbuilder/__init__.py` | Feature bump |

---

### Task 1: Failing shell assertions for Master CV

**Files:**
- Modify: `features/master_cv.feature`
- Modify: `features/steps/app_steps.py` only if a step is missing
- Test: Behave Master CV feature

**Interfaces:**
- Consumes: existing `I open the "master cv" page`, shell steps from navigation
- Produces: scenarios that fail until shell wrap lands

- [ ] **Step 1: Write the failing scenarios**

Update `features/master_cv.feature`:

```gherkin
@app @master
Feature: Master CV
  As a candidate
  I want a complete source CV inside CV Studio
  So that I can edit it without losing the app navigation

  Background:
    Given the CV Studio app is running

  Scenario: Master CV opens inside the Studio shell
    When I open the "master cv" page
    Then the response status is 200
    And the page contains the app shell navigation
    And the "master" nav item is marked active
    And the page title contains "Master"
    And the Master CV editor document is present
    And the page has an element matching ".cv-document.edit-mode"
    And the page has an element matching "header #btn-save"
    And the page has an element matching "#preview-pane"

  Scenario: Person details API backs the editor
    When I GET the API path "/api/person"
    Then the response status is 200
    And the JSON response has field "first_name"
```

Ensure `step_master_editor` still accepts contenteditable / `.cv-document` markup (update assertion if it only checks `body.edit-mode`).

- [ ] **Step 2: Run Behave — expect failure**

```bash
PYTHONPATH=src:scripts behave features/master_cv.feature -q
```

Expected: FAIL (shell nav missing and/or `.cv-document` / `header #btn-save` missing).

- [ ] **Step 3: Commit the red tests**

```bash
git add features/master_cv.feature features/steps/app_steps.py
git commit -m "$(cat <<'EOF'
test(master): require Studio shell on /cv/web/edit

EOF
)"
```

---

### Task 2: Extract `cv_body.html.j2` and keep PDF export green

**Files:**
- Create: `cv/web/cv_body.html.j2`
- Modify: `cv/web/template.html.j2`
- Modify: `scripts/cvweb.py` (optional thin `render_cv_body` helper)
- Test: `PYTHONPATH=src:scripts python3 -m pytest -k "render or export or pdf or html" -q` plus any existing template tests; smoke `render_html(False)`

**Interfaces:**
- Produces:
  ```python
  def render_cv_body(data: Optional[dict] = None, *, edit_mode: bool = False) -> str:
      """Render only the CV body partial (no html/shell chrome)."""
  ```
  and `render_html(...)` still returns a full standalone document for export.

- [ ] **Step 1: Extract body**

Move the `{% macro ea %}`, `PROVIDER_BADGES`, and everything from the current `.hero` through the experience/content blocks out of `template.html.j2` into `cv_body.html.j2` **without** the edit-mode toolbar/preview/script.

- [ ] **Step 2: Standalone wrapper**

`template.html.j2` becomes:

```jinja
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ person.first_name }} {{ person.last_name }} — CV</title>
<link rel="stylesheet" href="style.css">
</head>
<body{% if edit_mode %} class="edit-mode"{% endif %}>
<div class="cv-document{% if edit_mode %} edit-mode{% endif %}">
{% include "cv_body.html.j2" %}
</div>
</body>
</html>
```

(Do **not** include editor toolbar here — export path must stay chrome-free. Edit mode via this wrapper is only a fallback; Studio uses `master.html`.)

- [ ] **Step 3: Add `render_cv_body` in `cvweb.py`**

```python
def render_cv_body(data: Optional[Any] = None, *, edit_mode: bool = False) -> str:
    """Render ``cv_body.html.j2`` with CV data (no page chrome)."""
    if data is None:
        data = load_data()
    env = Environment(loader=FileSystemLoader(str(WEB_DIR)))
    return env.get_template("cv_body.html.j2").render(
        edit_mode=edit_mode, **data
    )


def render_html(data: Optional[Any] = None, edit_mode: bool = False) -> str:
    """Render the standalone CV HTML document (print / export)."""
    if data is None:
        data = load_data()
    env = Environment(loader=FileSystemLoader(str(WEB_DIR)))
    return env.get_template(TEMPLATE_NAME).render(edit_mode=edit_mode, **data)
```

Add pep257 docstrings / types on touched functions.

- [ ] **Step 4: Verify export path**

```bash
PYTHONPATH=src:scripts python3 - <<'PY'
import cvweb
html = cvweb.render_html(edit_mode=False)
assert "cv-document" in html
assert "shell" not in html
assert "CV Studio" not in html or "person" in html  # no studio brand nav
assert 'class="nav-link' not in html
print("ok", len(html))
PY
PYTHONPATH=src:scripts python3 -m pytest -q
```

Expected: pytest green; smoke assert passes.

- [ ] **Step 5: Commit**

```bash
git add cv/web/cv_body.html.j2 cv/web/template.html.j2 scripts/cvweb.py
git commit -m "$(cat <<'EOF'
refactor(cv): extract reusable CV body partial for shell embedding

EOF
)"
```

---

### Task 3: Scope `style.css` under `.cv-document`

**Files:**
- Modify: `cv/web/style.css`
- Smoke: open rendered HTML string / visual not required in CI

**Interfaces:**
- Edit-mode rules that currently key off `body.edit-mode` must also (or instead) key off `.cv-document.edit-mode` so they work inside the shell.
- Prefer dual selectors during transition where print still sets `body.edit-mode`:
  `body.edit-mode …, .cv-document.edit-mode …`

- [ ] **Step 1: Update selectors**

Mechanically update edit-mode and layout rules:

- `body.edit-mode` sheet background / padding → apply to `.cv-document.edit-mode` (and keep `body.edit-mode` aliases if standalone edit wrapper still uses body class).
- `body.edit-mode .hero` etc. → `.cv-document.edit-mode .hero`
- Structural control selectors (`body.edit-mode .struct-…`) → `.cv-document.edit-mode …`
- `#editor-toolbar` / `#preview-pane` rules: leave ids, but preview open state should use `.preview-open` on `.cv-document` or `main` rather than only `body.edit-mode.preview-open`.
- Avoid styling bare `aside` / `main` globally if any exist; prefer `.cv-document aside.sidebar` / `.cv-document main.intro` if bare tags currently fight the shell.

- [ ] **Step 2: Quick grep audit**

```bash
grep -nE '^(aside|main|body)\b|body\.edit-mode|^aside|^main' cv/web/style.css | head -80
```

Fix remaining collisions that would style `.shell > aside`.

- [ ] **Step 3: Commit**

```bash
git add cv/web/style.css
git commit -m "$(cat <<'EOF'
fix(cv): scope edit/document CSS under .cv-document

EOF
)"
```

---

### Task 4: Shell Master page + route wiring

**Files:**
- Create: `cv/web/src/pages/master.html`
- Create: `cv/web/src/pages/master.css`
- Modify: `scripts/serve-editor.py` (`edit_page`)
- Modify: `cv/web/editor.js` (toolbar + preview class hooks)
- Test: Behave Master CV (now green) + pytest

**Interfaces:**
- `edit_page()` renders shell page with `active="master"`, injects `cv_body_html`
- `#editor-toolbar` lives in `header_actions` (still that id so `editor.js` finds it)
- `#preview-pane` is an overlay sibling inside shell main/content

- [ ] **Step 1: `master.html`**

```jinja
{% extends "shell/base.html" %}
{% block title %}CV Studio — Master CV{% endblock %}
{% block extra_css %}
<link rel="stylesheet" href="/cv/web/style.css">
<link rel="stylesheet" href="/cv/web/src/pages/master.css">
{% endblock %}
{% block header_actions %}
<div id="editor-toolbar" class="master-toolbar">
  <button type="button" id="btn-save" class="primary">Save &amp; Preview</button>
  <span id="editor-status">Loaded.</span>
</div>
{% endblock %}
{% block content %}
<div class="master-workspace">
  <div class="cv-document edit-mode">
    {{ cv_body_html | safe }}
  </div>
  <div id="preview-pane" aria-hidden="true">
    <button type="button" id="preview-close" aria-label="Close preview">×</button>
    <iframe id="preview-frame" src="about:blank" title="CV PDF preview"></iframe>
  </div>
</div>
{% endblock %}
{% block extra_body %}
<script src="/cv/web/editor.js"></script>
<script src="/cv/web/src/pages/master.js"></script>
{% endblock %}
```

Create `master.js` only if a tiny close-button binder is cleaner outside `editor.js`; otherwise wire close inside `editor.js`.

- [ ] **Step 2: `master.css`**

- `.master-workspace { position: relative; }`
- Main scroll: `.shell > main` already scrolls; ensure `.cv-document` can show Letter-width sheet with side margins inside main (grey desk background on workspace, not whole viewport only).
- `#preview-pane`: fixed/absolute overlay covering the **main column** (not the shell aside); `z-index` above document; hidden by default; `.open` shows it.
- `#preview-close` visible control.
- `.master-toolbar` fits sticky header (no fixed bottom bar). Hide/override old bottom `#editor-toolbar { position:fixed; bottom:0 }` when inside header — e.g. `#editor-toolbar.master-toolbar { position: static; … }` in `master.css`.

- [ ] **Step 3: Wire `edit_page`**

```python
@app.get("/cv/web/edit")
def edit_page() -> str:
    """Serve Master CV inside the Studio shell."""
    from markupsafe import Markup

    body = cvweb.render_cv_body(edit_mode=True)
    return _render_page(
        "pages/master.html",
        crumb="MASTER CV",
        title="Edit your source CV",
        active="master",
        cv_body_html=Markup(body),
    )
```

- [ ] **Step 4: Adapt `editor.js` preview class**

Where code does `document.body.classList.add("preview-open")`, also toggle `.open` on `#preview-pane` (already likely) and prefer toggling on `.cv-document` / `.master-workspace` so layout CSS that no longer depends on `body.edit-mode.preview-open` still works. Wire `#preview-close` to remove `.open` / `preview-open`.

Undo/redo buttons are dynamically inserted into `#editor-toolbar` — keep that behaviour so they appear in the header.

Script `src` must be absolute `/cv/web/editor.js` (already on master.html).

- [ ] **Step 5: Verify**

```bash
PYTHONPATH=src:scripts behave features/master_cv.feature features/app_shell.feature features/navigation.feature -q
PYTHONPATH=src:scripts python3 -m pytest -q
PYTHONPATH=src:scripts python3 - <<'PY'
import runpy
from pathlib import Path
# optional: boot app test client if fixture-heavy — Behave already covers HTML
print('manual check: GET /cv/web/edit contains nav-link active and cv-document')
PY
```

Expected: Behave Master scenarios pass; pytest green.

- [ ] **Step 6: Commit**

```bash
git add cv/web/src/pages/master.html cv/web/src/pages/master.css \
  cv/web/src/pages/master.js scripts/serve-editor.py cv/web/editor.js
git commit -m "$(cat <<'EOF'
feat(master): embed Master CV editor in the Studio shell

EOF
)"
```

---

### Task 5: Version bump + README touch

**Files:**
- Modify: `VERSION` → `0.2.12.0`
- Modify: `src/cvbuilder/__init__.py` `__version__`
- Modify: `README.md` (Editing in the browser: note Master CV is inside the shell)

- [ ] **Step 1: Bump + README one-liner**

- [ ] **Step 2: Full verification**

```bash
PYTHONPATH=src:scripts python3 -m pytest -q
PYTHONPATH=src:scripts behave -q
```

Expected: green (wireframe excluded via `default_tags`).

- [ ] **Step 3: Commit**

```bash
git add VERSION src/cvbuilder/__init__.py README.md
git commit -m "$(cat <<'EOF'
chore(master): bump feature version for shell-wrapped editor

EOF
)"
```

---

## Plan self-review

| Spec requirement | Task |
| --- | --- |
| Shell nav always visible on edit | 1, 4 |
| Keep contenteditable document | 2, 4 |
| Header Save/Preview/Undo | 4 |
| Preview overlay | 4 |
| PDF export sans shell | 2 |
| CSS scoping `.cv-document` | 3 |
| Behave shell assertions | 1, 4 |
| Feature version bump | 5 |

No TBD placeholders. Loader constraint addressed by rendering `cv_body` in Python (`Markup`) rather than including a WEB_DIR template from the `src/`-only `_APP_ENV`.
