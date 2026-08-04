# Wireframe → real UI parity

**Date:** 2026-08-04
**Repo:** `cv-builder`
**Status:** Draft for review

## Problem

`cv/web/wireframe.html` (+ `wireframe*.css/js`) is a static, sample-data
click-through prototype in the new "CV Studio" visual language (green /
gold / blue / cream palette, left-nav app shell, card-based panels). The
real app — `builder.html`/`builder.js`/`builder.css` (snippet library +
job-posting matcher + compose/export), `/cv/web/edit`
(`template.html.j2` + `style.css` + `editor.js`, in-place CV editor),
and `variants.html`/`variants.js` (composed-variant manager) — still
uses the old plain styling and has never been touched by the branding
work (`git show --stat` on the three branding commits touches only
`wireframe-*` files).

Comparing the two side by side surfaces two different kinds of gaps:

1. **Cosmetic / structural drift.** Functionality that already exists
   and works — snippet CRUD, job-posting match & ranking, draft
   assembly, compose-to-PDF, saved drafts, variant list/re-render/delete,
   image upload/fetch (`/api/images*`) — is not styled or laid out like
   the wireframe.
2. **Fictional features.** Several wireframe views (Personal details,
   Import resume, Application questions, and generic multi-provider
   social-profile links) have **zero backend support today** — confirmed
   by inventory of `src/cvbuilder/{models,database,composer,importer,
   matcher}.py` and `scripts/serve-editor.py`'s route table. They're
   sample data and `toast()` calls, nothing more.

Decision (confirmed with the user): split the work into two tracks.
**Track A** reskins and rewires everything that already works, with no
backend changes, and should retire the standalone wireframe prototype
once done. **Track B** is a set of independently-greenlit follow-up
specs to build the fictional pages for real; this document only scopes
them, it does not design their data models in detail.

## Goals

- One consistent visual language (wireframe's palette, shell, and
  component styles) across the editor, builder, and variants pages.
- No loss of existing functionality during the reskin — every current
  API call, keyboard interaction, and edge case (empty states, autosave,
  match ranking, drag-free reorder via ↑/↓, PDF preview) keeps working.
- No page in the shipped app shows fabricated data. Anything the
  wireframe mocked that isn't backed by a real API either isn't built
  yet (Track B) or is rebuilt against the real API (Track A).
- Minimize risk to `/cv/web/edit`, which is the most structurally
  complex page (server-rendered `contenteditable` CV document, not a
  simple form) — restyle its chrome without rewriting its edit engine.

## Repository boundary and source layout

All Track A work — every new file, path, and reference — lives inside
this repo (`cv-builder`) and nowhere else. This repo is self-contained
and must stay that way; nothing in the shipped app should assume, link
to, or depend on a separate "resume" repo/directory existing alongside
it. This isn't hypothetical: the wireframe's own Connect AI page
(`wireframe.html`'s `#mcp` section, "Add it to your assistant" step)
hardcodes an example command as
`claude mcp add cv-builder -- python3 /absolute/path/to/resume/scripts/mcp-server.py`
— a stray `resume` path segment left over from wherever the mockup was
drafted, inconsistent with `README.md`'s real (correct) example, which
uses `/absolute/path/to/cv-builder/scripts/mcp-server.py`. **A8 fixes
this**: the real Connect AI page must source its example paths from
this repo's own conventions (or the README directly, per A8's existing
"sourced from `README.md` so the two never drift" note), never
"resume".

New frontend source produced by Track A does not get bolted onto the
existing flat, ad-hoc `wireframe-*.css/js` naming convention. It lives
under a proper **`cv/web/src/`** directory inside this repo — mirroring
the organization the Python side already has at `src/cvbuilder/` —
holding the shared design-system and shell code as real, named modules
rather than more `wireframe-*` files:

```text
cv/web/src/
  theme.css          # A1 — design tokens + base component styles
  shell/
    nav.html          # A2 — Jinja include: left-nav partial
    header.html        # A2 — Jinja include: sticky header/breadcrumb
    shell.css
  pages/
    home.css / home.js         # A3
    tailor.css / tailor.js     # A4 (builder.js's logic moves/extends here)
    library.css / library.js   # A5
    versions.css / versions.js # A6
    assets.css / assets.js     # A7
    connect-ai.css / connect-ai.js  # A8
```

`cv/web/wireframe.html` and its `wireframe*.css/js` files stay in place
untouched, purely as the **visual template/reference** Track A builds
against — they are not edited or extended further, and get retired in
A9 once every page under `cv/web/src/pages/` reaches parity with what
they mock. Flask's existing catch-all static-file route already serves
any path under `cv/web/`, so `cv/web/src/...` is reachable with no
routing changes; no bundler/build step is introduced by this
reorganization.

## Non-goals (this pass)

- Building Personal details, Import resume, or Application questions as
  real features (Track B — separate specs, separate approval).
- Changing any `/api/*` request/response contracts used by
  `builder.js`, `editor.js`, or `variants.js`.
- Merging this work with the in-flight
  [multiple layouts × content sets](2026-08-03-multiple-templates-design.md)
  spec. That work changes the Editor toolbar (layout/content-set
  pickers) and moves `template.html.j2`/`style.css` under
  `cv/layouts/`. Track A's shell should leave room for that toolbar
  addition but does not implement it.

## Track A — reskin + rewire (no schema or data-model changes)

Track A operates almost entirely on the frontend: HTML structure, CSS,
and the DOM-building logic in `builder.js`/`editor.js`/`variants.js`.
Most of it requires zero changes to `scripts/serve-editor.py`, `scripts/
cvweb.py`, or `src/cvbuilder/*`. The two exceptions are called out
explicitly where they occur: A7 (Assets) proposes an optional
inference/naming convention for photo-vs-logo, and A8 (Connect AI)
proposes an optional real health-check route — both additive, neither
touches a data model or an existing endpoint's contract. Every existing
Python test (`test_api.py`, `test_structure.py`, etc.) should stay
green throughout.

### A1. Design system extraction

Pull the wireframe's design tokens and base component styles into a
shared stylesheet the real pages can import:

- New `cv/web/theme.css`: CSS custom properties from
  `wireframe-cleanup.css`'s `:root` (ink/muted/green/pale/lime→gold/
  blue/cream/focus), typography scale, and the reusable primitives —
  buttons (`.primary`, ghost/text buttons), inputs/textareas/selects,
  badges/pills, card/panel shells, the `.shell` two-column app grid,
  and the sticky header.
- Branding assets (`assets/branding/cv-studio-logo.png`,
  `favicon.png`) already exist; wire them into every real page's
  `<head>`/nav, not just the wireframe.
- Keep this stylesheet separate from `cv/web/style.css` (the *printed
  CV document's* stylesheet) — one is app chrome, the other is CV
  output; they must not merge, especially given the layout-packs spec
  is about to relocate `style.css` under `cv/layouts/<id>/`.

### A2. Shared app shell (nav + header)

Build one shell partial — left `<aside>` nav (Home / Master CV /
Tailor / Content library / Assets / Versions / Connect AI, mirroring
`wireframe.html`'s nav minus the Track B items) and the sticky
`<header>` with breadcrumb/title — and include it on every real page
(`/cv/web/edit`, `/cv/web/build`, `/cv/web/variants`, plus the new Home
route below). Given `/cv/web/edit` is server-rendered via
`cvweb.render_html` and the other two are static HTML files, implement
the shell as a Jinja include used by `cvweb.render_html`'s wrapper and
duplicate (or template) it into `builder.html`/`variants.html` — do
**not** collapse the three pages into one client-routed SPA; that would
mean rewriting the in-place editor's server-rendered document flow for
no functional benefit and real regression risk.

Active nav item reflects the current route server-side (no client JS
needed for that part, unlike the wireframe's `show()`/`data-go`
routing, which only makes sense inside a single static page).

### A3. Home dashboard

New landing route (`/cv/web/` or `/cv/web/home`) matching the
wireframe's Home view, but every number is real:

- Snippet count from `/api/snippets` (or a lightweight count-only
  variant if payload size matters).
- Variant count and recent versions from `/api/variants`, sorted by
  updated time, rendered as the wireframe's version cards (name,
  status inferred from presence of a rendered PDF, updated-at).
- "Tailor a new CV" CTA → Tailor page.
- Drop the wireframe's fabricated "Applications this month" stat (no
  backend concept of "applications") unless/until Track B defines one.

### A4. Tailor flow restyle

Rebuild `builder.html`/`builder.css` markup to match the wireframe's
3-step wizard visuals (job details → choose content → review &
export), but keep it a single scrollable page backed by the existing
`builder.js` logic — the wireframe's 3 separate `.view`s can become 3
sections/states on one page rather than a literal step router, since
the real workflow already flows that way (paste posting → run match →
build draft → compose). Concretely:

- Posting textarea + "Analyze"/"Suggest snippets" restyled as step 1.
- Match results restyled into the wireframe's `.suggestion` checkbox
  rows (`matchMeta`/`matchOrder` already provide score + matched
  terms — this is a pure render change in `renderLibrary()`).
- Draft list restyled into the wireframe's summary panel
  (`.metric`, running snippet/page count) — reuse `renderDraft()`'s
  data, new markup.
- Compose ("Save & Preview PDF") restyled as the review/export step,
  still opening the real PDF in `#preview-pane`.

### A5. Content library restyle

New "browse everything" view, separate from the tailor step's
*suggested* subset — matches the wireframe's Content library page
(variant cards with Brief/Standard/Detailed tabs). Same
`/api/snippets` data as today; add a level-tab control per card (swap
`levelContent()` output on click, same pattern as the wireframe's
`data-brief/-standard/-detailed` attributes) instead of today's single
`<select>`. Snippet create/edit/delete keeps using the existing
`openSnippetForm`/`saveSnippetForm`/`DELETE` calls, restyled as a
drawer/modal instead of an inline form block.

### A6. Versions restyle

Rebuild `variants.html`/`variants.js` markup to match the wireframe's
Versions list (status pill, name, company/updated line, Open button),
same `/api/variants`, `/api/variants/<name>/render`,
`DELETE /api/variants/<name>` calls — render change only.

### A7. Assets page

New view over the **existing** `/api/images`, `/api/images/upload`,
`/api/images/fetch` endpoints — this is the one Track-A page needing a
small, non-breaking backend nicety rather than a new feature:

- Photo vs. logo/icon distinction: infer from whether the image path
  matches `person.photo` in `data.yaml` (→ "photo") vs. everything
  else (→ "logo"); ship this way first. If that proves too coarse,
  the smallest schema-free upgrade is a filename convention
  (`photo-*`/`logo-*`) rather than a new DB table.
- Built-in contact icons (LinkedIn/GitHub/GitLab/Medium/Instagram/
  Email/Website/Phone) are static SVG/CSS, not uploaded — ship as
  inline assets, matching the wireframe's `.social` swatches.
- "Use this asset" wires into the existing `person.photo` field via
  `/api/save` (already supports arbitrary leaf-path writes).

### A8. Connect AI page

Static instructional page — no fabricated "sample data", just the
real, already-documented setup (`docker compose up --build`, the
`claude mcp add` command, the example prompt) sourced from `README.md`
so the two never drift. Copy-to-clipboard buttons are real (same
`navigator.clipboard` pattern as the wireframe). "Test connection" only
ships if a cheap real check exists — e.g. a `HEAD`/`GET` against the
MCP server's own health surface when `ENABLE_MCP=1` — otherwise cut
that button rather than fake success.

### A9. Retire the prototype

Once A1–A8 ship, drop or gate the `/cv/web/wireframe` route
(`serve-editor.py:147`) — either delete `wireframe*.{html,css,js}` or
keep them under a `?prototype=1`-style flag purely as a design
reference, so users can no longer land on a page full of Ramon
Brooker/Calian/TextNow sample data by mistake.

**Suggested order:** A1 → A2 first (everything else depends on the
shell/tokens existing); A3, A6, A5 next (lowest functional risk —
list/browse views over stable read endpoints); A4 next (the most
interactive page — reuses the most existing logic but has the most
markup to rebuild); A7 and A8 can happen in parallel with A4 since
they're independent surfaces; A9 last, after everything else is
confirmed at parity.

## Track B — net-new features (scope only, separate specs)

Each of these needs its own design spec (data model, API surface,
migration) before implementation, the way the multi-layout work got
one. Scoped here only so their existence and rough shape is on record.

- **B1. Personal details.** `data.yaml`'s `person` block currently
  hardcodes `github`/`linkedin` as named fields
  (`cv/web/data.yaml:8-9`, `template.html.j2:23-24`). The wireframe
  wants an arbitrary list of provider/URL/visibility rows plus
  address/privacy fields. Needs: schema change to a generic
  `profiles: [{provider, url, visible}]` list (with a migration for
  the two hardcoded fields), template updates, and either reuse of
  `/api/structure` for list ops or a small dedicated endpoint.
- **B2. Import resume.** No parsing code exists anywhere in the repo
  today. Needs a real extraction pipeline (Markdown/text trivial; PDF
  via the Chrome/Chromium already required for export, or a text-layer
  library; DOCX/PPTX via `python-docx`/`python-pptx`), feeding into
  `SnippetImporter` as a new source type, plus a review/confirm UI.
  This is the largest Track B item.
- **B3. Application questions.** Fully new subsystem: question
  sources (job description / questionnaire / competency matrix),
  questions, saved answers, and evidence links to snippets. Needs new
  DB tables (parallel to `snippets`/`snippet_variants`/`drafts` in
  `database.py`), new API routes, and can reuse `SnippetMatcher`'s
  scoring for "suggest an answer from evidence."

Recommended sequencing if/when greenlit: B1 (small, unblocks the
Personal details page and removes the github/linkedin hardcoding) →
B3 (self-contained, no external parsing dependency) → B2 (largest,
most external-dependency risk).

## Success criteria

- Every real page (`/cv/web/edit`, `/cv/web/build`, `/cv/web/variants`,
  new Home/Assets/Connect-AI views) matches the wireframe's palette,
  shell, and component styling.
- No regressions: existing Python test suite stays green; manual pass
  of match → draft → compose → export, draft save/load/delete,
  snippet CRUD, image upload/fetch, and variant re-render/delete all
  still work post-restyle.
- No page in the shipped app displays sample/fake data.
- `/cv/web/wireframe` no longer reachable as a normal nav destination.

## Open questions deferred to implementation

- Where the Home route lives (`/cv/web/` vs. a new top-level path) and
  whether it becomes the new default landing page for
  `docker compose up`.
- Exact asset "kind" convention for A7 if the `person.photo`-only
  inference proves too coarse in practice.
- Whether A8's "Test connection" ships at all in v1, pending whether a
  cheap real health check exists.
- How Track A's header/shell should reserve space for the layout/
  content-set pickers the multi-layout spec will add to the Editor
  toolbar, so that work doesn't require re-touching the shell again.
