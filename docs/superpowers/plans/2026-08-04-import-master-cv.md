# Import Master CV Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Import's "Create a new master CV" mode so confirm backups `cv/web/data.yaml`, replaces content sections from the extracted resume while preserving `person`, and still upserts selected snippets into the library.

**Architecture:** Add a pure mapper (`apply_resume_to_master`) that patches a YAML dict from a `ParsedResume` + enabled sections. Extend `POST /api/imports/<token>/confirm` with `mode: library|master` using fixed order backup → YAML write → snippet upserts → permanentise staging. Enable the master radio in the Import UI and send `mode` on confirm.

**Tech Stack:** Python 3.12, Flask test client, `ruamel.yaml` via `scripts/cvweb.py`, existing `cvbuilder.resume_extractor`, pytest, Behave.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-04-import-master-cv-design.md`
- Canadian spelling in user-facing copy
- Type hints + pep257 docstrings on all new public Python functions/classes
- Prefer specific exceptions (no broad `except Exception`)
- TDD: failing test first for every behaviour
- Version scheme: `Major.Minor.feature.fix` — bump feature for this ship
- Compare mode stays disabled
- Default import radio remains **library** (safer)

## File structure

| File | Responsibility |
| --- | --- |
| `src/cvbuilder/resume_to_master.py` | Pure mapper: `ParsedResume` + enabled sections + current YAML → patched YAML dict |
| `tests/test_resume_to_master.py` | Unit tests for the mapper (preserve person, section enable/disable, empty clears) |
| `scripts/serve-editor.py` | Confirm route: `mode`, backup dir, call mapper + `cvweb.save_data`, history push |
| `tests/test_api.py` | Integration tests for master confirm / invalid mode / backup failure / library unchanged |
| `cv/web/src/pages/import.html` | Enable master radio; refresh copy |
| `cv/web/src/pages/import.js` | Send `mode`; master success toast; empty-extraction warning |
| `features/import_resume.feature` + `features/steps/app_steps.py` | Behave coverage for selectable mode + API master confirm |
| `.gitignore` | Ignore `data/backups/` |
| `VERSION`, `src/cvbuilder/__init__.py` | Feature bump |

---

### Task 1: Pure mapper `apply_resume_to_master`

**Files:**
- Create: `src/cvbuilder/resume_to_master.py`
- Create: `tests/test_resume_to_master.py`

**Interfaces:**
- Consumes: `cvbuilder.resume_extractor.ParsedResume`, `ParsedExperience`
- Produces:
  ```python
  def apply_resume_to_master(
      current: dict[str, Any],
      resume: ParsedResume,
      enabled_sections: set[str],
  ) -> dict[str, Any]:
      """Return a shallow-copied YAML document with enabled sections replaced.

      Preserves ``person``, ``panels``, and any other unmapped top-level keys.
      Disabled sections leave their existing YAML fields untouched.
      Enabled sections with zero extracted items write an empty structure
      (clear Example Company residue when the user chose that section).
      """
  ```

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_resume_to_master.py`:

```python
"""Unit tests for mapping ParsedResume into master data.yaml documents."""

from __future__ import annotations

from typing import Any

from cvbuilder.resume_extractor import ParsedExperience, ParsedResume
from cvbuilder.resume_to_master import apply_resume_to_master


def _base_doc() -> dict[str, Any]:
    return {
        "person": {"first_name": "Jordan", "last_name": "Rivers"},
        "panels": [{"title": "Keep me"}],
        "bio": ["Old bio"],
        "experience": [{"company": "Example Company", "role": "Example"}],
        "skills": {"technical": ["Old"], "functional": ["Keep?"]},
        "education": ["Old Uni"],
        "extra_key": "untouched",
    }


class TestApplyResumeToMaster:
    """Mapper behaviour for master-CV import."""

    def test_preserves_person_panels_and_unknown_keys(self) -> None:
        resume = ParsedResume(profile=["New bio"])
        result = apply_resume_to_master(
            _base_doc(), resume, {"profile", "experience", "skills", "education"}
        )
        assert result["person"] == {"first_name": "Jordan", "last_name": "Rivers"}
        assert result["panels"] == [{"title": "Keep me"}]
        assert result["extra_key"] == "untouched"

    def test_maps_all_enabled_sections(self) -> None:
        resume = ParsedResume(
            profile=["Leader in platforms."],
            experience=[
                ParsedExperience(
                    heading="Staff @ Acme",
                    role="Staff",
                    company="Acme",
                    bullets=["Shipped Kubernetes"],
                )
            ],
            skills=["Kubernetes", "Python"],
            education=["BSc CS"],
        )
        result = apply_resume_to_master(
            _base_doc(), resume, {"profile", "experience", "skills", "education"}
        )
        assert result["bio"] == ["Leader in platforms."]
        assert result["experience"] == [
            {
                "company": "Acme",
                "role": "Staff",
                "dates": "",
                "location": "",
                "subsections": [
                    {"heading": "Highlights", "bullets": ["Shipped Kubernetes"]}
                ],
            }
        ]
        assert result["skills"] == {
            "technical": ["Kubernetes", "Python"],
            "functional": [],
        }
        assert result["education"] == ["BSc CS"]

    def test_disabled_section_left_unchanged(self) -> None:
        resume = ParsedResume(skills=["New"])
        result = apply_resume_to_master(_base_doc(), resume, {"skills"})
        assert result["bio"] == ["Old bio"]
        assert result["experience"][0]["company"] == "Example Company"
        assert result["education"] == ["Old Uni"]
        assert result["skills"]["technical"] == ["New"]

    def test_empty_enabled_section_clears_field(self) -> None:
        resume = ParsedResume()
        result = apply_resume_to_master(_base_doc(), resume, {"bio"} & set() | {"experience"})
        # enable experience only with zero items
        result = apply_resume_to_master(_base_doc(), resume, {"experience"})
        assert result["experience"] == []
        assert result["bio"] == ["Old bio"]

    def test_experience_without_bullets_uses_heading_bullet(self) -> None:
        resume = ParsedResume(
            experience=[
                ParsedExperience(heading="Solo Consultant", role="Consultant", company="")
            ]
        )
        result = apply_resume_to_master(_base_doc(), resume, {"experience"})
        bullets = result["experience"][0]["subsections"][0]["bullets"]
        assert bullets == ["Solo Consultant"]
```

Fix the messy line in `test_empty_enabled_section_clears_field` — keep only the clean version:

```python
    def test_empty_enabled_section_clears_field(self) -> None:
        resume = ParsedResume()
        result = apply_resume_to_master(_base_doc(), resume, {"experience"})
        assert result["experience"] == []
        assert result["bio"] == ["Old bio"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src python3 -m pytest tests/test_resume_to_master.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'cvbuilder.resume_to_master'` (or import error for `apply_resume_to_master`).

- [ ] **Step 3: Implement the mapper**

Create `src/cvbuilder/resume_to_master.py`:

```python
"""Map a parsed resume onto a master CV ``data.yaml`` document."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from cvbuilder.resume_extractor import ParsedExperience, ParsedResume

_MAPPED_SECTIONS = frozenset({"profile", "experience", "skills", "education"})


def apply_resume_to_master(
    current: dict[str, Any],
    resume: ParsedResume,
    enabled_sections: set[str],
) -> dict[str, Any]:
    """Return a deep-copied YAML document with enabled sections replaced.

    Preserves ``person``, ``panels``, and any other unmapped top-level keys.
    Disabled sections leave their existing YAML fields untouched. Enabled
    sections with zero extracted items write an empty structure so old
    placeholder content does not linger.

    Args:
        current: Existing master CV document (``data.yaml`` root).
        resume: Structured extraction from the staged resume file.
        enabled_sections: Subset of ``profile`` / ``experience`` /
            ``skills`` / ``education`` chosen on the review screen.

    Returns:
        A new document dict safe to dump back to ``data.yaml``.
    """
    document = deepcopy(current)
    enabled = enabled_sections & _MAPPED_SECTIONS

    if "profile" in enabled:
        document["bio"] = list(resume.profile)
    if "experience" in enabled:
        document["experience"] = [
            _experience_entry(entry) for entry in resume.experience
        ]
    if "skills" in enabled:
        document["skills"] = {
            "technical": list(resume.skills),
            "functional": [],
        }
    if "education" in enabled:
        document["education"] = list(resume.education)
    return document


def _experience_entry(entry: ParsedExperience) -> dict[str, Any]:
    """Convert one parsed role into a ``data.yaml`` experience block."""
    bullets = list(entry.bullets) if entry.bullets else [entry.heading]
    return {
        "company": entry.company or "",
        "role": entry.role or entry.heading,
        "dates": "",
        "location": "",
        "subsections": [{"heading": "Highlights", "bullets": bullets}],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src python3 -m pytest tests/test_resume_to_master.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cvbuilder/resume_to_master.py tests/test_resume_to_master.py
git commit -m "$(cat <<'EOF'
feat(import): map parsed resume onto master data.yaml sections

EOF
)"
```

---

### Task 2: Master confirm API (backup + YAML + snippets)

**Files:**
- Modify: `scripts/serve-editor.py` (confirm handler ~818–870; add backup helper + imports)
- Modify: `tests/test_api.py` (add master-mode cases beside existing import tests)
- Modify: `.gitignore` (add `data/backups/`)

**Interfaces:**
- Consumes: `apply_resume_to_master`, `cvweb.load_data`, `cvweb.save_data`, `cvweb.read_data_text`, `_history().push_before_change`
- Produces: confirm JSON always includes `mode`; master also `master_updated`, `backup_path`

- [ ] **Step 1: Write the failing API tests**

Append to the import test class in `tests/test_api.py` (reuse `SAMPLE_RESUME_TEXT` already defined there):

```python
    def test_confirm_master_mode_updates_yaml_and_preserves_person(
        self, client: "FlaskClient"
    ) -> None:
        from io import BytesIO

        import cvweb

        before = cvweb.load_data()
        original_first = before["person"]["first_name"]

        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        token = uploaded.get_json()["token"]
        confirmed = client.post(
            f"/api/imports/{token}/confirm",
            json={"mode": "master"},
        )
        assert confirmed.status_code == 200
        body = confirmed.get_json()
        assert body["mode"] == "master"
        assert body["master_updated"] is True
        assert body["snippet_count"] > 0
        assert body["backup_path"].startswith("data/backups/data.yaml.")
        assert (cvweb.REPO_ROOT / body["backup_path"]).is_file()

        after = cvweb.load_data()
        assert after["person"]["first_name"] == original_first
        assert after["bio"]  # non-empty from SAMPLE_RESUME_TEXT summary
        assert after["experience"]
        assert after["experience"][0]["company"] or after["experience"][0]["role"]
        skills = client.get("/api/snippets?tag=import")
        assert len(skills.get_json()) == body["snippet_count"]

    def test_confirm_invalid_mode_returns_400(self, client: "FlaskClient") -> None:
        from io import BytesIO

        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        token = uploaded.get_json()["token"]
        resp = client.post(
            f"/api/imports/{token}/confirm",
            json={"mode": "compare"},
        )
        assert resp.status_code == 400

    def test_confirm_library_mode_default_does_not_touch_master(
        self, client: "FlaskClient"
    ) -> None:
        from io import BytesIO

        import cvweb

        before_text = cvweb.read_data_text()
        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        token = uploaded.get_json()["token"]
        confirmed = client.post(
            f"/api/imports/{token}/confirm",
            json={},
        )
        assert confirmed.status_code == 200
        body = confirmed.get_json()
        assert body.get("mode", "library") == "library"
        assert body.get("master_updated", False) is False
        assert cvweb.read_data_text() == before_text
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
PYTHONPATH=src:scripts python3 -m pytest \
  tests/test_api.py::TestResumeImportApiEndpoints::test_confirm_master_mode_updates_yaml_and_preserves_person \
  tests/test_api.py::TestResumeImportApiEndpoints::test_confirm_invalid_mode_returns_400 \
  tests/test_api.py::TestResumeImportApiEndpoints::test_confirm_library_mode_default_does_not_touch_master \
  -v
```

Expected: FAIL (invalid mode accepted or master_updated missing / YAML unchanged).

- [ ] **Step 3: Implement API support**

1. Add to `.gitignore`:

```
data/backups/
```

2. Near other import constants in `scripts/serve-editor.py`:

```python
BACKUPS_DIR = cvweb.REPO_ROOT / "data" / "backups"
IMPORT_MODES = frozenset({"library", "master"})
```

3. Import mapper:

```python
from cvbuilder.resume_to_master import apply_resume_to_master
```

4. Add helper:

```python
def _backup_master_yaml() -> Path:
    """Write a UTC timestamped backup of data.yaml under data/backups/.

    Returns:
        Path relative to the repo root (posix) for API responses.

    Raises:
        OSError: If the backup directory or file cannot be written.
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    relative = Path("data") / "backups" / f"data.yaml.{stamp}.bak"
    absolute = cvweb.REPO_ROOT / relative
    absolute.write_text(cvweb.read_data_text(), encoding="utf-8")
    return relative
```

5. Rewrite `api_confirm_import` body handling to:

- Parse `mode = (payload.get("mode") or "library")`; if not in `IMPORT_MODES` → 400.
- Re-parse staged file (existing).
- Compute `enabled` set from `sections` (existing).
- If `mode == "master"`:
  - `before = cvweb.read_data_text()`
  - `backup_rel = _backup_master_yaml()`  # catch `OSError` → 500 `{error,}`
  - `patched = apply_resume_to_master(cvweb.load_data(), resume, enabled)`
  - `_history().push_before_change("import-master", text=before)`
  - `cvweb.save_data(patched)`
- Then existing snippet upserts + permanentise staging.
- Response:

```python
result = {
    "id": import_id,
    "filename": original_name,
    "snippet_count": created,
    "mode": mode,
    "master_updated": mode == "master",
}
if mode == "master":
    result["backup_path"] = backup_rel.as_posix()
return jsonify(**result)
```

Keep Canadian user-facing error strings where returned to UI
(`"unsupported import mode"` for 400).

- [ ] **Step 4: Run API import tests**

Run:

```bash
PYTHONPATH=src:scripts python3 -m pytest tests/test_api.py -k import -v
PYTHONPATH=src python3 -m pytest tests/test_resume_to_master.py -v
```

Expected: all PASS. Existing library import cases still green.

- [ ] **Step 5: Commit**

```bash
git add scripts/serve-editor.py tests/test_api.py .gitignore
git commit -m "$(cat <<'EOF'
feat(import): confirm mode=master backups and rewrites data.yaml

EOF
)"
```

---

### Task 3: Enable master mode in the Import UI

**Files:**
- Modify: `cv/web/src/pages/import.html` (radios ~29–42)
- Modify: `cv/web/src/pages/import.js` (confirm payload + toast + empty warn)

**Interfaces:**
- Consumes: confirm response fields `mode`, `master_updated`, `snippet_count`, `backup_path`
- Produces: request body `{ mode, sections }`

- [ ] **Step 1: Write a failing Behave scenario (page + mode selectable)**

Update `features/import_resume.feature`:

```gherkin
@app @import
Feature: Import a resume
  As a candidate
  I want to import an existing resume into the library or master CV
  So that I do not have to retype my history

  Scenario: Import resume route is shipped in the real app
    Given the CV Studio app is running
    When I open the "import" page
    Then the response status is 200
    And the page contains the app shell navigation
    And the "import" nav item is marked active
    And the page title contains "Import"
    And the import mode "library" is available
    And the import mode "new" is available
    And the import mode "compare" is disabled

  Scenario: Master confirm rewrites content sections and preserves person
    Given the CV Studio app is running
    And a staged sample resume upload
    When I confirm the import with mode "master"
    Then the response status is 200
    And the master CV person first name is unchanged
    And the master CV has non-empty bio content
    And the import created library snippets
```

Add step helpers in `features/steps/app_steps.py` / `app_client.py` as needed:

```python
@then('the import mode "{mode}" is available')
def step_mode_available(context: Context, mode: str) -> None:
    soup = BeautifulSoup(context.response_html, "html.parser")
    radio = soup.select_one(f'input[name="import-mode"][value="{mode}"]')
    assert radio is not None
    assert radio.has_attr("disabled") is False


@then('the import mode "{mode}" is disabled')
def step_mode_disabled(context: Context, mode: str) -> None:
    soup = BeautifulSoup(context.response_html, "html.parser")
    radio = soup.select_one(f'input[name="import-mode"][value="{mode}"]')
    assert radio is not None
    assert radio.has_attr("disabled")


@given("a staged sample resume upload")
def step_stage_sample(context: Context) -> None:
    sample = (
        "Summary\nPlatform leader.\n\n"
        "Experience\nEngineer — Acme\n- Built things\n\n"
        "Skills\nPython\n\nEducation\nBSc\n"
    )
    resp = context.client.post(
        "/api/imports",
        data={"file": (BytesIO(sample.encode()), "resume.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201
    context.import_token = resp.get_json()["token"]
    context.person_before = context.client.get("/api/person").get_json()


@when('I confirm the import with mode "{mode}"')
def step_confirm_mode(context: Context, mode: str) -> None:
    context.response = context.client.post(
        f"/api/imports/{context.import_token}/confirm",
        json={"mode": mode},
    )
    context.response_json = context.response.get_json()


@then("the master CV person first name is unchanged")
def step_person_unchanged(context: Context) -> None:
    after = context.client.get("/api/person").get_json()
    assert after["first_name"] == context.person_before["first_name"]


@then("the master CV has non-empty bio content")
def step_bio_nonempty(context: Context) -> None:
    # Prefer a small debug endpoint if none exists: read via compose/file —
    # use GET /cv/web/edit HTML containing bio text, or expose nothing and
    # call through internal fixture. Simplest for Behave: POST is enough and
    # assert response.master_updated; also re-open home is weak.
    assert context.response_json.get("master_updated") is True
    # Stronger check via API person alone is insufficient; add a
    # GET that isn't available — instead compare snippet tags and
    # rely on pytest for YAML. For Behave, assert backup_path present:
    assert context.response_json.get("backup_path")


@then("the import created library snippets")
def step_snippets_created(context: Context) -> None:
    assert context.response_json["snippet_count"] > 0
```

Prefer tightening `the master CV has non-empty bio content` by reading `cvweb.load_data()` inside the step (Behave's `environment.py` already has `PYTHONPATH` for `cvbuilder`/`cvweb`):

```python
@then("the master CV has non-empty bio content")
def step_bio_nonempty(context: Context) -> None:
    import cvweb

    data = cvweb.load_data()
    assert data.get("bio")
```

- [ ] **Step 2: Run Behave import feature — expect failure on `new` available**

Run: `PYTHONPATH=src:scripts behave features/import_resume.feature -q`

Expected: FAIL because master radio is still `disabled`.

- [ ] **Step 3: Update HTML**

In `cv/web/src/pages/import.html`, replace the disabled master choice with:

```html
      <label class="import-choice">
        <input type="radio" name="import-mode" value="new">
        <span><b>Create a new master CV</b><small>Best when this is your primary or most complete resume. Existing personal details are kept; content sections are replaced.</small></span>
      </label>
```

Keep library as `checked` default. Leave compare disabled.

- [ ] **Step 4: Update JS confirm path**

In `import.js` confirm handler:

```javascript
    const modeInput = document.querySelector('input[name="import-mode"]:checked');
    const uiMode = modeInput ? modeInput.value : "library";
    const mode = uiMode === "new" ? "master" : "library";

    // warn when master + all counts zero
    if (
      mode === "master" &&
      state.counts &&
      Object.values(state.counts).every((n) => n === 0)
    ) {
      if (
        !confirm(
          "No content was extracted. Continuing will clear enabled master sections. Continue?"
        )
      ) {
        btn.disabled = false;
        return;
      }
    }

    const resp = await fetch(`/api/imports/${state.token}/confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sections, mode }),
    });
    // ...
    if (body.mode === "master" && body.master_updated) {
      const noun = body.snippet_count === 1 ? "snippet" : "snippets";
      showToast(
        `Master CV updated · ${body.snippet_count} ${noun} added. Open Master CV to review.`
      );
    } else {
      const noun = body.snippet_count === 1 ? "snippet" : "snippets";
      showToast(`${body.snippet_count} ${noun} added to your library.`);
    }
```

Also add radio selection styling (match wireframe) if not already handled:

```javascript
  document.querySelectorAll('input[name="import-mode"]').forEach((input) => {
    input.addEventListener("change", () => {
      document.querySelectorAll(".import-choice").forEach((el) =>
        el.classList.remove("selected")
      );
      input.closest(".import-choice").classList.add("selected");
    });
  });
```

Map UI `value="new"` → API `mode="master"` as above (keeps wireframe value names in HTML).

- [ ] **Step 5: Re-run Behave + pytest import suites**

```bash
PYTHONPATH=src:scripts behave features/import_resume.feature -q
PYTHONPATH=src:scripts python3 -m pytest tests/test_api.py -k import tests/test_resume_to_master.py -q
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add cv/web/src/pages/import.html cv/web/src/pages/import.js \
  features/import_resume.feature features/steps/app_steps.py features/steps/app_client.py
git commit -m "$(cat <<'EOF'
feat(import): enable Create a new master CV in the Import UI

EOF
)"
```

---

### Task 4: Version bump + README note

**Files:**
- Modify: `VERSION` (e.g. `0.2.11.0` → `0.2.12.0` — verify current value first)
- Modify: `src/cvbuilder/__init__.py` (keep `__version__` in sync if present)
- Modify: `README.md` briefly under Import / API bullets if Import is documented

- [ ] **Step 1: Read current VERSION and bump feature component**

- [ ] **Step 2: Add one README line under API endpoints**

```
- `POST /api/imports/<token>/confirm` — confirm staged import (`mode`:
  `library`|`master`); master backups `data.yaml` then rewrites content sections
```

- [ ] **Step 3: Run full verification**

```bash
PYTHONPATH=src:scripts python3 -m pytest -q
PYTHONPATH=src:scripts behave -q
```

Expected: pytest green; Behave default suite green (wireframe excluded).

- [ ] **Step 4: Commit**

```bash
git add VERSION src/cvbuilder/__init__.py README.md
git commit -m "$(cat <<'EOF'
chore(import): bump feature version for master-CV import mode

EOF
)"
```

---

## Plan self-review

| Spec requirement | Task |
| --- | --- |
| Extend confirm with `mode` | Task 2 |
| Backup before YAML write | Task 2 |
| Preserve `person` / unmapped keys | Task 1 + 2 |
| Map profile/experience/skills/education | Task 1 |
| Empty enabled section clears field | Task 1 |
| Also upsert library snippets | Task 2 |
| Enable master radio; default library | Task 3 |
| Compare stays disabled | Task 3 |
| Behave + pytest coverage | Tasks 1–3 |
| Feature version bump | Task 4 |
| Editor history push on master | Task 2 (`push_before_change`) |
| Ignore `data/backups/` | Task 2 |

No TBD/placeholder steps remain after fixing the Behave bio assertion to use `cvweb.load_data()`.
