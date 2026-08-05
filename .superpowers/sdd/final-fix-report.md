# Final Fix Report

## Fix Notes

- Restored Tailor "Save & Preview PDF" behaviour by posting `render_pdf: true` to `/api/compose` while keeping DB-primary compose and not forcing `export_yaml`.
- Kept the Tailor preview path active when `body.pdf` is returned and updated the toast so DB-primary compose no longer displays `null` for omitted YAML exports.
- Added partial export cleanup for `/api/export` failures so YAML, Markdown, and PDF export errors remove a partially written target before returning 500.
- Added a focused API regression test that simulates a YAML write failure and verifies the partial destination is removed.
- Updated the stale composer module docstring.
- Bumped the fix version from `0.2.13.0` to `0.2.13.1` in `VERSION` and `src/cvbuilder/__init__.py`.

## Test Evidence

- `pytest tests/test_api.py::TestApiEndpoints::test_export_yaml_write_failure_removes_partial_target -v`
  - Red before fix: failed because `partial.yaml` remained.
  - Green after fix: 1 passed.
- `pytest tests/test_api.py -k 'export or compose' -v`
  - 5 passed, 30 deselected.
- `pytest tests/test_document_schema.py -k tailor -v`
  - 1 passed, 1 deselected.
- `pytest tests/test_composer.py -v`
  - 3 passed.
- IDE diagnostics for edited Python/JavaScript files: no linter errors found.
