# Library → Working Draft merge

**Date:** 2026-08-05  
**Status:** Approved for implementation  
**Version:** feature bump to `0.2.16.0`

## Problem

The Content library (“Your career content”) is CRUD-only. Users need
to add a snippet into the Working Draft CV without going through Tailor,
and without wiping existing Working Draft content.

## Decision

**Merge, do not rebuild.** `POST /api/working-draft/add-snippets` appends
selected snippet content into the matching section of the current Working
Draft YAML. History is pushed first.

## UI

Each library card gains **Add to Working Draft** (detail level = current
library detail-level control, default standard). Toast on success;
link/hint to open `/edit`.

## Out of scope

Selections tracking / Tailor draft sync; remove-from-working; bulk
select UI beyond one/few cards.
