# CV Builder

A self-hosted tool for maintaining a CV as structured content instead of a
single hand-formatted document: a browser editor for a data-driven
HTML/CSS resume, a SQLite-backed snippet library for assembling
role-tailored variants, and an MCP server so an LLM can help do the same
thing from a chat client instead of the browser.

Ships with a fully synthetic example person in `cv/web/data.yaml` and
`content/` — replace it with your own before you rely on this for real.
Nothing in this repo is anyone's real personal data.

## Layout

- `cv/web/` — HTML/CSS CV source (`data.yaml`, `template.html.j2`,
  `style.css`, `editor.js`) and the app UI (`cv/web/src/`: shared shell
  + design tokens in `shell/` and `theme.css`, one Jinja page + CSS/JS
  per app-chrome route under `pages/`)
- `content/` — optional additional detail for the snippet library, as
  markdown alongside `data.yaml`:
  - `work-experience/` — one file per employer (`category: experience`,
    company taken from the filename)
  - `parts/` — reusable blocks not tied to an employer, e.g. an alternate
    bio or a longer "detailed" variant of a strength (`category: part`)
  - `requirements/` — pre-written answers to recurring posting
    requirements, for `match_job_posting`/the builder's posting-matcher
    to surface (`category: requirement`)
  - See the example files under each for the heading convention: only
    the *last* heading before a block of prose becomes a snippet
- `src/cvbuilder/` — snippet library (SQLite), importer, matcher, composer,
  and the MCP server
- `scripts/` — CLI entry points (see below)
- `data/` — SQLite snippet database (`snippets.db`, gitignored,
  regenerable) and generated variants live under `cv/variants/`

## Quickstart

```
pip install -r requirements.txt

# Seed the snippet database from cv/web/data.yaml + content/
PYTHONPATH=src python3 scripts/seed-snippets.py

# Run the editor / builder / variants UI
python3 scripts/serve-editor.py        # http://127.0.0.1:5057/cv/web/edit
```

Requires `google-chrome` or `chromium` on PATH for PDF export
(`CHROME_BIN` env var to point at a specific binary).

### Editing in the browser

`scripts/serve-editor.py` serves one app, sharing a common nav/header
shell (`cv/web/src/shell/`) across every page below except `/cv/web/edit`,
which renders the CV document itself:

- **`/cv/web/`** — Home dashboard: live snippet/version counts and
  recent versions.
- **`/cv/web/edit`** — click any text to edit it in place; hover controls
  add/reorder/delete list items (bullets, skills, jobs, subsections,
  education, custom side panels); Save & Preview renders a real PDF.
  Adding a skill/bio paragraph/education entry opens a picker fed from
  the snippet database, with search and duplicate flagging.
- **`/cv/web/build`** ("Tailor") — paste a job posting to re-rank
  snippets by keyword match, choose content, assemble an ordered draft,
  and compose it into a new named variant under `cv/variants/<name>/`.
- **`/cv/web/library`** ("Content library") — browse/search/filter every
  snippet, switch between its brief/standard/detailed variants, and
  create/edit/delete snippets or re-seed the database from source files.
- **`/cv/web/variants`** ("Versions") — preview, re-render, or delete
  composed variant folders.
- **`/cv/web/assets`** — browse/upload photos and logos (backed by the
  `/api/images*` endpoints) and reference the built-in contact icons.
- **`/cv/web/connect`** ("Connect AI") — MCP setup instructions and an
  optional local connectivity check.

### Docker

Runs the editor/builder UI and the MCP server in one container, with the
repo bind-mounted so edits land on the host:

```
docker compose up --build
# home:     http://127.0.0.1:5057/cv/web/
# editor:   http://127.0.0.1:5057/cv/web/edit
# tailor:   http://127.0.0.1:5057/cv/web/build
# library:  http://127.0.0.1:5057/cv/web/library
# variants: http://127.0.0.1:5057/cv/web/variants
# assets:   http://127.0.0.1:5057/cv/web/assets
# connect:  http://127.0.0.1:5057/cv/web/connect
# MCP:      http://127.0.0.1:8765/mcp  (streamable-http)
```

Both ports publish to `127.0.0.1` only. Set `ENABLE_MCP=0` in the compose
`environment` block to run the web UI without the MCP server.

## Connecting an LLM (MCP server)

`src/cvbuilder/mcp_server.py` (run via `scripts/mcp-server.py`) exposes
the snippet library and composer as [MCP](https://modelcontextprotocol.io)
tools: `list_snippets`, `get_snippet`, `create_snippet`, `update_snippet`,
`add_snippet_variant`, `delete_snippet`, `delete_snippet_variant`,
`match_job_posting`, `compose_cv`, `list_variants`, `list_drafts`,
`get_draft`, `save_draft`, `delete_draft`, `reseed_snippets`.

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

- `GET /api/person` — read-only `person` block of `data.yaml` (Assets page)
- `GET/POST/PUT/DELETE /api/snippets` — list/create/update/delete snippets
- `DELETE /api/snippets/<id>/variants/<level>` — remove one detail level
- `POST /api/structure` — insert/delete/move/replace items in `data.yaml`
- `GET /api/history`, `POST /api/undo`, `POST /api/redo` — editor undo/redo
- `GET/PUT/DELETE /api/drafts[/<name>]` — saved builder drafts
- `POST /api/match` — rank snippets against posting text
- `POST /api/compose` — compose a named variant from selected snippet ids
- `GET/DELETE /api/variants[/<name>]`, `POST /api/variants/<name>/render`
- `GET /api/images`, `POST /api/images/upload`, `POST /api/images/fetch` —
  list, upload, or download images/icons into `assets/images/`
- `POST /api/seed` — re-seed the database from YAML + markdown sources

## Tests

```
python3 -m pytest
```

### Cucumber / Behave BDD

Gherkin features under `features/*.feature` describe the shipped CV
Studio app (shell pages + JSON APIs). They run with
[Behave](https://behave.readthedocs.io) against the real Flask app via
its test client (isolated SQLite DB; no wireframe simulation).

The older in-memory wireframe suite lives under `features/wireframe/`
and is excluded by default (`~@wireframe` in `behave.ini`).

```
pip install -r requirements.txt
behave
# wireframe prototype suite (separate step definitions):
behave features/wireframe
```
