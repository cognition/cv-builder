# Load application-ready CV into Working Draft

**Date:** 2026-08-05  
**Status:** Approved for implementation  
**Version:** feature bump to `0.2.20.0`

## Problem

Composed/application-ready versions live on the Versions page but cannot be
brought back into the Working Draft editor for further editing.

## Decision

**Replace content sections from a named variant; keep person.**

From Versions, **Load into Working Draft** copies the chosen variant’s
bio / skills / experience / education / panels onto the Working Draft
document. The Working Draft `person` block is preserved. History is pushed
first so Undo restores the previous Working Draft.

## API

`POST /api/working-draft/load-variant`

```json
{ "name": "ircc-it04" }
```

Response includes `document_id`, `name`, and `ok`. Missing variant → 404.

## UI

Versions row action: **Load into Working Draft**. Toast on success with a
hint to open Working Draft (`/edit`). Clears conflict highlights.

## Out of scope

Merge mode; confirm dialog; auto-navigation to `/edit`; Tailor draft sync.
