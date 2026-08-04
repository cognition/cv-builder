"""Map a parsed resume onto a master CV ``data.yaml`` document."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from cvbuilder.resume_extractor import ParsedExperience, ParsedResume

_MAPPED_SECTIONS = frozenset({"profile", "experience", "skills", "education"})


def apply_resume_to_master(
    current: dict[str, Any],
    resume: ParsedResume,
    enabled_sections: set[str],
) -> dict[str, Any]:
    """Return a deep-copied YAML document with enabled sections replaced.

    Preserves ``person``, ``panels``, and any other unmapped top-level keys.
    Disabled sections leave their existing YAML fields untouched. Enabled
    sections with zero extracted items write an empty structure so old
    placeholder content does not linger.

    Args:
        current: Existing master CV document (``data.yaml`` root).
        resume: Structured extraction from the staged resume file.
        enabled_sections: Subset of ``profile`` / ``experience`` /
            ``skills`` / ``education`` chosen on the review screen.

    Returns:
        A new document dict safe to dump back to ``data.yaml``.
    """
    document = deepcopy(current)
    enabled = enabled_sections & _MAPPED_SECTIONS

    if "profile" in enabled:
        document["bio"] = list(resume.profile)
    if "experience" in enabled:
        document["experience"] = [
            _experience_entry(entry) for entry in resume.experience
        ]
    if "skills" in enabled:
        document["skills"] = {
            "technical": list(resume.skills),
            "functional": [],
        }
    if "education" in enabled:
        document["education"] = list(resume.education)
    return document


def _experience_entry(entry: ParsedExperience) -> dict[str, Any]:
    """Convert one parsed role into a ``data.yaml`` experience block."""
    bullets = list(entry.bullets) if entry.bullets else [entry.heading]
    return {
        "company": entry.company or "",
        "role": entry.role or entry.heading,
        "dates": "",
        "location": "",
        "subsections": [{"heading": "Highlights", "bullets": bullets}],
    }
