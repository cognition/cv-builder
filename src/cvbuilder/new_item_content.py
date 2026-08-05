"""Placeholder wording used when inserting a brand-new, unfilled item.

Pure content, no structural logic: every value here is text a user would
see and immediately overwrite (a fresh bullet, a fresh job, a fresh side
panel). Kept separate from ``cvweb._default_insert_value``, which decides
*which* of these applies to a given ``data.yaml`` list path but shouldn't
also be the place that dictates the wording — that way the wording can be
changed (or translated, or made less terse) without touching insertion
logic, and the logic can be changed without wading through prose strings.
"""

from __future__ import annotations

GENERIC_ITEM = "New item"
SKILL = "New skill"
BIO_PARAGRAPH = "New bio paragraph."
EDUCATION_ENTRY = "New education entry"
BULLET = "New bullet"

# A brand-new job's first subsection, and a brand-new subsection on its
# own, intentionally use different default headings — "Highlights" reads
# naturally as the first subsection of a freshly-added job, whereas a
# subsection added later has no such context.
NEW_JOB_SUBSECTION_HEADING = "Highlights"
NEW_SUBSECTION_HEADING = "New subsection"

JOB = {
    "company": "New Company",
    "role": "New Role",
    "dates": "",
    "location": "",
}

PANEL = {
    "title": "New Panel",
}

PROFILE = {
    "provider": "website",
    "handle": "New profile",
    "url": "",
    "visible": True,
}
