# CV Builder

A self-hosted tool for maintaining a CV as structured content instead of a
single hand-formatted document: a browser editor for a data-driven
HTML/CSS resume, a SQLite-backed document and snippet library for assembling
role-tailored variants, and an MCP server so an LLM can help do the same
thing from a chat client instead of the browser.

Includes a fully synthetic example person (Homer Simpson) in
`cv/web/data.yaml` and `content/` for local seeding and optional Docker
demo mode (`DEMO=1`). Docker first boot is blank unless `DEMO=1`. Replace
the sample with your own before you rely on this for real. Nothing in this
repo is anyone's real personal data.

## Layout

- `cv/web/` — HTML/CSS CV source (`data.yaml`, `template.html.j2`,
  `style.css`, `editor.js`) and the app UI (`cv/web/src/`: shared shell
  + design tokens in `shell/` and `theme.css`, one Jinja page + CSS/JS
  per app-chrome route under `pages/`)
- `content/` — optional additional detail for the snippet library, as
  markdown alongside the bootstrap YAML:
  - `work-experience/` — one file per employer (`category: experience`,
    company taken from the filename)
  - `parts/` — reusable blocks not tied to an employer, e.g. an alternate
    bio or a longer "detailed" variant of a strength (`category: part`)
  - `requirements/` — pre-written answers to recurring posting
    requirements, for `match_job_posting`/the builder's posting-matcher
    to surface (`category: requirement`)
  - See the example files under each for the heading convention: only
    the *last* heading before a block of prose becomes a snippet
- `src/cvbuilder/` — SQLite-backed CV document store, snippet library,
  importer, matcher, composer, exporters, and the MCP server
- `scripts/` — CLI entry points (see below)
- `data/` — local (non-Docker) SQLite database (`snippets.db`, gitignored);
  when `CV_DATA_ROOT` is set (Docker defaults to `/data`), the DB, uploads,
  imports, and export artefacts live under that data root instead
- Explicit variant export files default to `cv/variants/` locally, or
  `$CV_DATA_ROOT/cv/variants/` in Docker

## Quickstart

```
pip install -r requirements.txt

# Seed the SQLite database from cv/web/data.yaml + content/
PYTHONPATH=src python3 scripts/seed-snippets.py

# Run the editor / builder / variants UI
python3 scripts/serve-editor.py        # http://127.0.0.1:5057/edit
```

Requires `google-chrome` or `chromium` on PATH for PDF export
(`CHROME_BIN` env var to point at a specific binary).

### Document storage and export

Master and variant CV documents live in SQLite (`cv_documents`), which is
the source of truth for live browser edits, composed variants, imports, and
exports. On first run, if the database has no master CV row, the app
bootstraps that row from the shipped `cv/web/data.yaml` unless
`SKIP_FS_BOOTSTRAP=1` (blank Docker first boot); after that,
`data.yaml` is just an input or explicit export target, not the live store.

Undo and redo state is transitory and stored in `cv_history`. Pins preserve
frozen document content together with the snippet stacks used to produce it,
so a pinned variant can be inspected or exported later without depending on
current snippet selections.

Exports are explicit: request YAML, Markdown, or PDF when you want files on
disk. Composing or editing a CV updates the database first and writes
`cv/variants/<name>/` output only when export options are selected.

### Editing in the browser

`scripts/serve-editor.py` serves one app, sharing a common nav/header
shell (`cv/web/src/shell/`) across every page below, including Working Draft
(`/edit`):

- **`/`** — Home dashboard: live snippet/version counts and
  recent versions.
- **`/edit`** ("Working Draft") — click any text to edit it in place
  inside the shell; hover controls add/reorder/delete list items (bullets,
  skills, jobs, subsections, education, custom side panels); Save & Preview
  stores the Working Draft in SQLite and can render a real PDF.
  Adding a skill/bio paragraph/education entry opens a picker fed from
  the snippet database, with search and duplicate flagging.
- **`/build`** ("Tailor") — paste a job posting to re-rank
  snippets by keyword match, choose content, assemble an ordered draft,
  and compose it into a named SQLite variant; choose export options when
  you want YAML, Markdown, or PDF files under `cv/variants/<name>/`.
- **`/library`** ("Content library") — browse/search/filter every
  snippet, switch between its brief/standard/detailed variants, and
  create/edit/delete snippets or re-seed the database from source files.
- **`/variants`** ("Versions") — preview, re-render, export, or
  delete composed variant documents.
- **`/assets`** — browse/upload photos and logos (backed by the
  `/api/images*` endpoints) and reference the built-in contact icons.
- **`/connect`** ("Connect AI") — MCP setup instructions and an
  optional local connectivity check.

### Docker

Runs the editor/builder UI and the MCP server in one container. Mutable
user content is stored on a named volume at `/data` (`cv_data`), so the
database, uploaded images, resume imports, and optional variant/PDF
exports survive image rebuilds. The repo is still bind-mounted at `/app`
for local code edits — omit that mount for image-only runs.

First boot of an empty volume creates a blank SQLite database (schema only,
no master CV) unless you set `DEMO=1` in the compose `environment` block.
Blank Docker installs stay blank across restarts because non-demo starts
skip filesystem bootstrap. With `DEMO=1`, the container seeds the synthetic
Homer Simpson snippets and allows bootstrapping the master CV from
`cv/web/data.yaml`. Existing volumes are never wiped when `DEMO` changes.

```
docker compose up --build
# home:     http://127.0.0.1:5057/
# editor:   http://127.0.0.1:5057/edit
# tailor:   http://127.0.0.1:5057/build
# library:  http://127.0.0.1:5057/library
# variants: http://127.0.0.1:5057/variants
# assets:   http://127.0.0.1:5057/assets
# connect:  http://127.0.0.1:5057/connect
# MCP:      http://127.0.0.1:8765/mcp  (streamable-http)
```

Volume layout (`CV_DATA_ROOT=/data`):

```
/data/snippets.db
/data/assets/images/     # uploaded photos and logos
/data/imports/           # resume uploads
/data/cv/variants/       # optional YAML/PDF exports
/data/cv/current/        # disposable preview artefacts
```

To use a host directory instead of the named volume, replace the
`cv_data:/data` mount with e.g. `./persistent-data:/data`.

Both ports publish to `127.0.0.1` only. Set `ENABLE_MCP=0` in the compose
`environment` block to run the web UI without the MCP server.

## Connecting an LLM (MCP server)

`src/cvbuilder/mcp_server.py` (run via `scripts/mcp-server.py`) exposes
the snippet library and composer as [MCP](https://modelcontextprotocol.io)
tools: `list_snippets`, `get_snippet`, `create_snippet`, `update_snippet`,
`add_snippet_variant`, `delete_snippet`, `delete_snippet_variant`,
`audit_library`, `upsert_snippets` (batch create/update; `dry_run` defaults
to true), `delete_snippets` (batch delete; `dry_run` defaults to true),
`match_job_posting`, `compose_cv`, `list_variants`, `list_drafts`,
`get_draft`, `save_draft`, `delete_draft`, `reseed_snippets`. Use
`audit_library` then dry-run `upsert_snippets` / `delete_snippets` to
populate or refine the Content library.

**Local subprocess (stdio)** — the client spawns the server itself:

```
claude mcp add cv-builder -- python3 /absolute/path/to/cv-builder/scripts/mcp-server.py
```

```json
{
  "mcpServers": {
    "cv-builder": {
      "command": "python3",
      "args": ["/absolute/path/to/cv-builder/scripts/mcp-server.py"]
    }
  }
}
```

**Already-running server (HTTP)** — point a client at the Docker
container instead (`MCP_TRANSPORT=streamable-http` inside the container,
published at `http://127.0.0.1:8765/mcp`):

```
claude mcp add --transport http cv-builder http://127.0.0.1:8765/mcp
```

```json
{
  "mcpServers": {
    "cv-builder": { "url": "http://127.0.0.1:8765/mcp" }
  }
}
```

There's no authentication on the MCP endpoint or the web UI — fine for
local personal use, but don't publish either port beyond `127.0.0.1`
without adding auth first.

Set `SNIPPETS_DB` to point either server at a different database file
(defaults to `data/snippets.db`).

## API endpoints (same Flask process as the editor)

- `GET /api/person` — read-only `person` block of the master CV (Assets page)
- `GET/POST/PUT/DELETE /api/snippets` — list/create/update/delete snippets
- `DELETE /api/snippets/<id>/variants/<level>` — remove one detail level
- `POST /api/structure` — insert/delete/move/replace items in the master CV
- `GET /api/history`, `POST /api/undo`, `POST /api/redo` — editor undo/redo
- `GET/PUT/DELETE /api/drafts[/<name>]` — saved builder drafts
- `POST /api/match` — rank snippets against posting text
- `POST /api/compose` — compose a named variant from selected snippet ids,
  with optional YAML, Markdown, and PDF exports
- `GET/DELETE /api/variants[/<name>]`, `POST /api/variants/<name>/render`
- `GET /api/images`, `POST /api/images/upload`, `POST /api/images/fetch` —
  list, upload, or download images/icons into `assets/images/`
- `POST /api/seed` — re-seed the database from YAML + markdown sources
- `POST /api/imports/<token>/confirm` — confirm staged import (`mode`:
  `library`|`master`); master imports update SQLite and can be exported later

## Tests

```
python3 -m pytest
```

### Cucumber / Behave BDD

Gherkin features under `features/` describe product behaviour informed
by the interactive wireframe (`cv/web/wireframe.html`). **Behave always
runs against the shipped Flask app** (test client + isolated SQLite /
import scratch dirs) — never against the wireframe.

Tag `@wip` marks wireframe-informed backlog that is not yet asserted
against the real UI (usually browser-driven flows). Those scenarios are
skipped with a reason so the default suite stays green while gaps stay
visible.

```
pip install -r requirements.txt
behave
# include skipped @wip backlog in the report (already shown by default):
behave --tags=@wip
```
