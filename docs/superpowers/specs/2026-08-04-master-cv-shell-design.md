# Master CV inside the Studio shell

**Date:** 2026-08-04
**Repo:** `cv-builder`
**Status:** Draft for review
**Route:** `/cv/web/edit` ("Master CV")

## Problem

Every Studio page except Master CV uses the shared shell
(`cv/web/src/shell/base.html` + left nav). `/cv/web/edit` still renders
`cvweb.render_html(edit_mode=True)` — a full-bleed printable CV document
with its own `<html>`/`<body>`, editor toolbar, and preview pane. Opening
Master CV drops the left navigation; users cannot move to Tailor, Library,
etc. without using browser history or a hard URL.

## Goals

- Master CV editing happens **inside** CV Studio: left nav always visible,
  Master CV marked active.
- Keep the existing **contenteditable CV document** as the editing surface
  (same look, paths, and structural controls).
- Move primary actions (**Save & Preview**, status, and any undo/redo
  exposed in chrome) into the Studio sticky header's `header_actions`
  slot.
- PDF preview becomes an **overlay/drawer** that does not hide or push
  away the Studio sidebar.
- PDF **export / print** continues to produce a standalone CV HTML
  document with **no** Studio chrome.

## Non-goals

- Redesigning Master CV as a form-style editor (Personal details already
  covers identity; Library covers snippets).
- Changing `/api/save`, `/api/structure`, `/api/history`, or contenteditable
  data-path semantics.
- Implementing the multi-template / folder-per-template picker (separate
  design) — leave header space so a template picker can land later.
- Retiring `cv/web/wireframe.html`.

## Decisions (confirmed)

| Topic | Choice |
| --- | --- |
| Editing surface | Keep contenteditable CV document |
| Chrome | Wrap in Studio shell (nav + header) |
| Primary actions | Studio sticky header `header_actions` |
| Structural +/−/reorder | Stay on the document (existing editor.js) |
| PDF preview | Overlay/drawer over main; sidebar stays |
| Implementation | Shell page + reusable CV body partial; scope CSS under `.cv-document` |

## Approach

Split the current `template.html.j2` into:

1. **`cv/web/cv_body.html.j2`** — the printable/editable CV body
   (`.hero` with CV sidebar + intro, macros for `contenteditable` /
   `data-path`). No `<html>`, no Studio chrome, no editor toolbar.
2. **`cv/web/template.html.j2`** — thin standalone wrapper for PDF
   export: doctype, head (`style.css`), body, `{% include cv_body %}`,
   no edit chrome when `edit_mode` is false (export path).
3. **`cv/web/src/pages/master.html`** — Studio page extending
   `shell/base.html`:
   - `active` / crumb / title set by `edit_page()`
   - `{% block header_actions %}` — Save & Preview, status, undo/redo if
     already wired in editor chrome
   - `{% block content %}` — scrollable `.cv-document` wrapping the
     included body partial with `edit_mode=True`
   - Preview overlay markup + scripts (`editor.js` + small page CSS)

`scripts/serve-editor.py` `edit_page()` switches from
`cvweb.render_html(edit_mode=True)` to `_render_page("pages/master.html",
..., active="master", ...)` while still loading CV data via
`cvweb.load_data()` and rendering the body partial with the same
context keys (`person`, `skills`, `bio`, …).

`cvweb.export_pdf` / `render_html(edit_mode=False)` keep using the
standalone `template.html.j2` wrapper so Chrome print-to-PDF never
embeds the Studio shell.

## CSS scoping

Today `style.css` styles bare `aside`, `main`, `.sidebar`, etc., which
collide with `.shell > aside` and `<main>` once nested.

- Wrap the included body in `<div class="cv-document">…</div>` on the
  Master page (and equivalently on the standalone print wrapper for
  consistency).
- Update `style.css` selectors so document rules are rooted under
  `.cv-document` (e.g. `.cv-document aside.sidebar`, not global
  `aside`). Prefer a mechanical pass over inventing a second stylesheet.
- Studio `theme.css` / `shell.css` remain untouched for chrome; Master
  page may add `cv/web/src/pages/master.css` only for overlay, header
  action layout, and main scroll behaviour.

## Toolbar and preview

**Header actions** (Studio sticky header):

- Primary button: Save & Preview (`#btn-save` or equivalent id kept for
  `editor.js`).
- Status: `#editor-status`.
- Undo / Redo: only if the current editor toolbar already exposes them
  (or if they are trivial to surface from existing `/api/undo` /
  `/api/redo`); do not invent new undo UX in this pass.

**Document controls:** hover add/delete/reorder widgets stay injected by
`editor.js` onto the CV document.

**Preview overlay:**

- `#preview-pane` is `position: fixed` (or absolutely within `main`) as a
  drawer covering the main column only — Studio left nav remains visible
  and usable.
- Includes close control; opening Save & Preview loads the PDF into
  `#preview-frame` as today.
- Overlay must not require hiding `aside.nav`.

## Routing and JS

- URL stays `/cv/web/edit` (nav already points there).
- `editor.js` asset path: serve from `/cv/web/editor.js` (already static
  under `cv/web/`). Adjust any relative assumptions if the page URL
  context changes (prefer root-absolute `/cv/web/...` for CSS/JS).
- Print/export path must not load `editor.js`.

## Testing

- **Behave:** Master CV / shell scenarios assert `/cv/web/edit` returns
  200, contains app shell navigation, and `master` nav item is active
  (extend `features/master_cv.feature` / navigation outline if missing).
- **Pytest:** existing editor save/structure/history API tests stay
  green; if any test asserts raw `render_html(edit_mode=True)` HTML
  shape, update expectations for shell wrap or target the body partial
  instead.
- **Manual / export:** `export_pdf` output must not contain Studio brand
  nav or `.shell`.

## Versioning

Bump the feature component of `VERSION` when this ships
(`Major.Minor.feature.fix`).

## Success criteria

- On `/cv/web/edit`, Studio left nav is always visible; Master CV is
  active; user can navigate to other Studio pages without leaving a
  full-bleed editor.
- In-place editing, Save & Preview, and structural controls still work.
- PDF preview is an overlay; sidebar stays.
- Exported PDF HTML has no Studio chrome.
- No intentional change to `/api/*` contracts.

## Open follow-ups

- Template/layout picker in the header (multi-template design).
- Whether undo/redo already belong in header chrome or remain
  keyboard-only until exposed.
- Narrow-viewport shell collapse already exists in `shell.css`; verify
  Master page scroll + overlay still usable there.
