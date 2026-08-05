# PDF preview chrome (Close / Expand / Pop out)

**Date:** 2026-08-05  
**Status:** Approved for implementation  
**Version:** feature bump to `0.2.19.0`

## Problem

Tailor (and Versions) use a fixed corner `#preview-pane` with no way to
dismiss, enlarge, or open the PDF outside the app. Working Draft has a
close control but no Expand / Pop out. Users need the same window chrome
everywhere.

## Decision

Shared toolbar on every `#preview-pane`:

| Control | Behaviour |
|--------|-----------|
| **Close** | Remove `open` / `expanded`; clear iframe to `about:blank`; restore Workspace chrome |
| **Expand** | Toggle full-viewport overlay (`position: fixed; inset: 0`) covering sidebar |
| **Pop out** | `window.open` the current PDF URL in a new tab |
| **Escape** | Collapse if expanded; otherwise Close |

Default sizes stay page-specific (corner floater on Tailor/Versions;
in-column drawer on Working Draft). Expand always becomes the same
fullscreen overlay.

## Implementation notes

- Markup: toolbar + iframe inside `#preview-pane` on Tailor, Versions,
  Working Draft (`master.html`).
- Shared init script: `cv/web/src/preview-pane.js`.
- Theme CSS for floater + expanded; Working Draft `master.css` overrides
  so `.expanded` wins over the absolute drawer rules.
- Feature bump `0.2.19.0`.
