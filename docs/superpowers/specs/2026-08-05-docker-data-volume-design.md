# Docker persistent data volume (`CV_DATA_ROOT`)

**Date:** 2026-08-05  
**Repo:** `cv-builder`  
**Status:** Draft for review  
**Depends on:** DB-primary documents (`cv_documents` in SQLite), current
`docker-compose.yml` / `docker-entrypoint.sh`

## Problem

Compose today bind-mounts the whole repo (`.:/app`). That keeps content on
the host only when the code mount is present. A production-style run of the
image alone has nowhere durable for:

- SQLite (`snippets.db` — library + master/variant documents + pins/history)
- Uploaded images (`assets/images/`)
- Resume import files (`data/imports/`)
- Optional composed exports (`cv/variants/`) and preview PDFs (`cv/current/`)

Operators need a **named volume** (or host path) that persists across
container rebuilds independently of the code tree.

## Goals

- Mount a named Docker volume at `/data` for all mutable user content.
- Configure paths via `CV_DATA_ROOT` (and existing `SNIPPETS_DB` /
  `RESUME_IMPORTS_DIR` where already used).
- On empty volume: create directories; seed the DB from image-shipped
  `cv/web/data.yaml` + `content/` when the DB file is missing.
- Keep built-in branding in the image (`/app/assets/branding`); user uploads
  land on the volume.
- Keep `.:/app` as an optional local-dev code mount.
- Document named-volume default and host-path override in the README.

## Non-goals

- Moving on-disk studio templates out of `cv/web/` in the image.
- Separating one volume per subdirectory (multi-mount compose).
- Cloud object storage / S3 for assets.
- Automatic migration of an existing host `./data` into the named volume
  beyond documenting how to copy if needed.
- Changing API contracts for `/api/images*` beyond path resolution.

## Decision summary (confirmed with user)

| Decision | Choice |
| --- | --- |
| Volume shape | Named volume at `/data` |
| Scope | All user-generated: DB, uploads, imports, variant exports, preview artefacts |
| First start | Seed DB from image content when DB missing; mkdir data dirs |
| Approach | `CV_DATA_ROOT=/data`; resolve writable paths under it |

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│ Container                                                   │
│  /app          code + seed YAML/content + branding (image)  │
│  /data  ◄────  named volume `cv_data` (persistent)          │
│     snippets.db                                             │
│     imports/                                                │
│     assets/images/                                          │
│     cv/variants/                                            │
│     cv/current/                                             │
└─────────────────────────────────────────────────────────────┘
```

### Path resolution

Introduce `CV_DATA_ROOT`:

- Docker Compose: `/data`
- Local (unset): same as `REPO_ROOT` (today’s layout under the repo)

Derived defaults (overridable by existing env vars when already present):

| Concern | Env | Under `CV_DATA_ROOT` |
| --- | --- | --- |
| SQLite | `SNIPPETS_DB` | `snippets.db` |
| User images | (new) `ASSETS_IMAGES_DIR` or derived | `assets/images` |
| Resume imports | `RESUME_IMPORTS_DIR` | `imports` |
| Variant exports | derived | `cv/variants` |
| Preview PDF/MD | derived | `cv/current/cv.pdf` |

Bootstrap / seed read-only sources stay under `REPO_ROOT` (`/app`):
`cv/web/data.yaml`, `content/**`, branding.

### HTTP asset serving

- `/assets/branding/...` → files under `REPO_ROOT/assets/branding`
- `/assets/images/...` → files under `CV_DATA_ROOT/assets/images`
- Prefer an explicit rule before the catch-all so user images resolve from
  the data volume when `CV_DATA_ROOT != REPO_ROOT`.

Person photo `web_path` values that point at `/assets/images/...` continue
to work; `data_path` used in YAML may stay repo-relative when exporting YAML
to the app tree, or be expressed relative to the served URL space—prefer
keeping `web_path` absolute-from-site-root (`/assets/images/...`) so export/
display do not depend on the data root layout.

### Compose

```yaml
services:
  cv-editor:
    build: .
    volumes:
      - cv_data:/data
      - .:/app   # local code bind; omit for image-only runs
    environment:
      CV_DATA_ROOT: /data
      SNIPPETS_DB: /data/snippets.db
      RESUME_IMPORTS_DIR: /data/imports
      # …existing EDITOR_*/MCP_*…

volumes:
  cv_data:
```

Host-path override (documented, not default):

```yaml
volumes:
  - ./persistent-data:/data
```

### Entrypoint

1. Resolve `CV_DATA_ROOT` (default `/data` if the directory exists or
   `CV_DATA_ROOT` is set; else `/app`).
2. `mkdir -p` for `assets/images`, `imports/staging`, `cv/variants`,
   `cv/current`.
3. If `SNIPPETS_DB` (or default under data root) is missing → seed via
   existing importer (`python3 -m cvbuilder.importer`) with paths that read
   seed content from `/app` and write the DB under `/data`.
4. Start MCP + editor as today.

### Local non-Docker

Unset `CV_DATA_ROOT` → behaviour unchanged (everything under the repo).
Developers may set `CV_DATA_ROOT` to an absolute path for a local dry-run of
volume layout.

## Testing

- Unit/helper test: with `CV_DATA_ROOT` set to a temp dir, DB, assets,
  imports, variants, and preview paths resolve under that dir.
- Entrypoint / compose smoke (manual or scripted): fresh named volume →
  container creates dirs, seeds DB, upload image lands under `/data`.
- Existing API tests keep using temp `SNIPPETS_DB` / monkeypatched dirs.

## Version impact

Feature bump when implementation ships (e.g. `0.2.14.x` → `0.2.15.0`
depending on tip at implement time).

## Open follow-ups (out of scope)

- One-shot migration helper copying host `./data` + `./assets/images` into
  the named volume.
- Read-only root filesystem with only `/data` writable.
