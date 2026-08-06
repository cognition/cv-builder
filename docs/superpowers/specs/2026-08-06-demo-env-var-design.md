# Docker `DEMO` env var for first-boot content

**Date:** 2026-08-06  
**Repo:** cv-builder  
**Status:** Approved for implementation  
**Depends on:** Docker data volume (`CV_DATA_ROOT`), DB-primary documents

## Problem

Image and compose first-boot always seed the Homer Simpson synthetic
demo (snippets from `cv/web/data.yaml` + `content/`, and a master CV
bootstrapped from that YAML). Operators who want a blank install have no
way to skip that without deleting content after start.

## Goals

- Gate first-boot demo content behind Docker env `DEMO=1`.
- When `DEMO` is unset or any value other than `1`: empty snippet library
  and **no** master CV document (truly blank until import/create).
- Never wipe an existing volume based on `DEMO`.
- Document the variable in compose / Dockerfile / README.

## Non-goals

- Changing `/api/seed` or MCP seed to refuse demo sources (explicit
  reseed may still load shipped YAML/content).
- Auto-migrating or clearing DBs when `DEMO` flips after first boot.
- Removing Homer assets from the image (they remain available when
  `DEMO=1` or when someone reseeds intentionally).

## Decision summary

| Decision | Choice |
| --- | --- |
| Env var | `DEMO=1` enables demo; otherwise blank |
| Scope when blank | Empty snippet library **and** no master document |
| When applied | First boot only (DB file missing) |
| Approach | Gate in `docker-entrypoint.sh`; skip FS bootstrap via `SKIP_FS_BOOTSTRAP=1` |

## Behaviour

### First boot (`SNIPPETS_DB` path missing)

| `DEMO` | Snippets | Master CV |
| --- | --- | --- |
| `1` | Seed via `python3 -m cvbuilder.importer` (YAML + `content/`) | Allowed: normal `bootstrap_from_filesystem` loads `cv/web/data.yaml` |
| unset / other | Create DB + `ensure_schema` only; no importer | Set `SKIP_FS_BOOTSTRAP=1`; bootstrap is a no-op; `get_working()` stays `None` |

### Existing volume

If the DB file already exists, the entrypoint does **not** reseed and does
**not** change documents based on `DEMO`.

## Architecture

```text
docker-entrypoint.sh
  DB missing?
    DEMO=1  → importer.seed()  → later app bootstrap loads Homer YAML
    else    → ensure_schema only + SKIP_FS_BOOTSTRAP=1
              → document_store() skips FS import → blank UI empty-state
```

### Entrypoint

1. Resolve `CV_DATA_ROOT` / `SNIPPETS_DB` as today.
2. `mkdir -p` data dirs as today.
3. If DB missing:
   - `DEMO=1`: log and run `python3 -m cvbuilder.importer`.
   - else: create empty DB with schema only (small Python one-liner or
     tiny helper), export `SKIP_FS_BOOTSTRAP=1`, log that demo seed was
     skipped.
4. Start MCP + editor as today.

### Filesystem bootstrap guard

`DocumentStore.bootstrap_from_filesystem` (or the caller in
`scripts/web_state.document_store`) must honour `SKIP_FS_BOOTSTRAP`:

- When set to `1`, return zero counts immediately without reading
  `cv/web/data.yaml` or `cv/variants/*/data.yaml`.
- When unset / other, keep current behaviour (needed for `DEMO=1` and
  local non-Docker workflows that expect Homer).

Prefer reading the env in the bootstrap entry path so MCP and the web
editor share one rule.

### Compose / image defaults

- `docker-compose.yml`: document `DEMO` (omit or leave unset for blank;
  set `DEMO: "1"` when operators want Homer).
- `Dockerfile`: do **not** default `DEMO=1` (blank is the safe default for
  image-only runs).
- `README.md`: short note on `DEMO=1` vs blank first boot.

## Editor empty state

With no master document, existing empty-state / lookup handling for a
missing Working Draft must remain usable (no crash on home/editor). This
work does not invent a new blank YAML skeleton.

## Testing

- Unit: with `SKIP_FS_BOOTSTRAP=1`, `bootstrap_from_filesystem` does not
  create a master even when `data.yaml` exists.
- Unit/integration: first-boot blank path creates schema and zero
  snippets / no master (or equivalent coverage via a small helper).
- Manual/compose: fresh volume + no `DEMO` → blank; fresh volume +
  `DEMO=1` → Homer present.

## Version impact

Feature bump when implementation ships (e.g. `0.2.24.0` → `0.2.25.0`
depending on tip at implement time).
