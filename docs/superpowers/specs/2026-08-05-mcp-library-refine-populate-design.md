# MCP library populate & refine — design

**Date:** 2026-08-05  
**Status:** Approved for planning  
**Version impact:** feature bump when implemented

## Goal

Extend the CV Builder MCP server so an assistant can **populate** and
**refine** the Content library: audit gaps/noise, then apply structured
batch creates/updates/deletes. The **LLM performs rewriting**; MCP only
inspects and persists. Existing single-snippet CRUD tools remain.

## Non-goals (v1)

- Server-side LLM calls inside MCP (`refine_snippet` that invents text)
- Resume PDF / job-text extractors as MCP tools
- Working Draft ↔ library sync
- Automatic split/merge algorithms (agent uses upsert + delete for that)

## Context

Today `src/cvbuilder/mcp_server.py` already exposes:

- `list_snippets`, `get_snippet`, `create_snippet`, `update_snippet`
- `add_snippet_variant`, `delete_snippet`, `delete_snippet_variant`
- `match_job_posting`, `compose_cv`, drafts, `reseed_snippets`

Gaps for agent workflows:

- No **library health** report to drive refine passes
- No **batch** upsert/delete with preview (`dry_run`)
- MCP instructions do not describe populate/refine playbooks

## Approach

**Workflow tools (chosen):** keep existing CRUD; add three focused tools
plus instruction updates.

| Tool | Role |
|------|------|
| `audit_library` | Read-only health report |
| `upsert_snippets` | Batch create/update from structured items; `dry_run=true` default |
| `delete_snippets` | Batch delete by ids; `dry_run=true` default |

Rejected alternatives:

- Single `library_ops` mega-tool — harder to discover and type in clients
- Thin HTTP-only wrappers — no new value beyond what agents can already do one call at a time

## Tool details

### `audit_library`

**Args (optional filters):** `category`, `tag`, `search` (same semantics as
`list_snippets` where applicable).

**Returns** a report object, for example:

```json
{
  "counts_by_category": {"bio": 1, "skill": 40, "experience": 25},
  "missing_detail_levels": [
    {"id": 12, "category": "experience", "missing": ["brief", "detailed"]}
  ],
  "empty_tags": [{"id": 3, "category": "skill"}],
  "sparse_headings": [{"id": 8, "category": "experience", "heading": null}],
  "length_outliers": [
    {"id": 99, "detail_level": "standard", "chars": 12, "reason": "too_short"}
  ],
  "duplicate_candidates": [
    {"ids": [10, 11], "reason": "same_company_role", "company": "X", "role": "Y"}
  ]
}
```

Heuristics (tunable constants in code):

- Missing levels: any of brief/standard/detailed absent
- Empty tags: `tags` empty or missing
- Sparse headings: experience/education without useful `heading` (and optionally company/role)
- Length outliers: variant content under ~20 chars or over a high ceiling
- Duplicate candidates: same normalised `company`+`role`, or identical content hash on a detail level — **candidates only**, not auto-merged

### `upsert_snippets`

**Args:**

- `snippets`: list of items
- `dry_run`: bool, **default `true`**

**Item shape:**

```json
{
  "id": 12,
  "category": "experience",
  "company": "Example Corp",
  "role": "Engineer",
  "heading": "Platform work",
  "tags": ["python", "aws"],
  "variants": {
    "brief": "- Short bullet",
    "standard": "- Medium bullets…",
    "detailed": "- Longer bullets…"
  }
}
```

Rules:

- Omit `id` → **create**; include `id` → **update** existing
- Create requires `category` and at least one variant with non-empty content
- Update may change metadata and/or any subset of variants (upsert per level)
- Tags on update: if `tags` is present, replace; if omitted, leave unchanged
- Metadata fields omitted on update keep current values
- Invalid category / detail level / missing create fields → per-item error; rest of batch continues

**Result:**

```json
{
  "dry_run": true,
  "created": [{"id": null, "planned_index": 0, "category": "skill", "summary": "…"}],
  "updated": [{"id": 12, "summary": "…"}],
  "errors": [{"index": 3, "message": "…"}],
  "counts": {"created": 1, "updated": 1, "errors": 1}
}
```

When `dry_run=false`, `created`/`updated` include real ids after write.

### `delete_snippets`

**Args:** `snippet_ids: list[int]`, `dry_run: bool = true`

**Result:** `{dry_run, deleted: [{id, summary}], errors: [...], counts: {...}}`

Unknown ids are errors; known ids are listed (and removed only when not dry-run).

## Agent playbooks (MCP instructions)

Update FastMCP `instructions` (and README MCP section briefly) with:

1. **Populate:** inspect with `list_snippets` / `audit_library` → draft structured items → `upsert_snippets(dry_run=true)` → review → `upsert_snippets(dry_run=false)`.
2. **Refine:** `audit_library` → `get_snippet` for targets → rewrite variants in the agent → `upsert_snippets` / `delete_snippets` with dry-run then apply. For splits: create children then delete parent. For merges: upsert survivor then delete duplicates.

## Implementation notes

- Prefer a small service module (e.g. `cvbuilder.library_ops`) used by MCP tools so pytest can call it without FastMCP.
- Reuse `SnippetDatabase` create/update/upsert_variant/delete; no schema change required for v1.
- Canadian spelling in user-facing strings (`favour`, etc.) where applicable.
- Bump application **feature** version when shipping.

## Testing

In `tests/test_mcp_server.py` (or `tests/test_library_ops.py`):

1. `audit_library` reports missing levels / empty tags for seeded fixtures
2. `upsert_snippets(dry_run=true)` does not persist; `false` creates and updates
3. Partial batch: one bad item errors; siblings succeed
4. `delete_snippets` dry-run vs apply
5. Playbook smoke: audit → upsert missing brief → audit no longer flags that id for brief

## Success criteria

- An MCP client can run populate and refine flows without calling single-create N times for bulk work
- Accidental writes are hard: batch mutators default to dry-run
- Existing MCP tools and compose/match behaviour unchanged
