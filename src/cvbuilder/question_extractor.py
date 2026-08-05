"""Turn pasted text into a list of application-question prompts.

Deterministic and local, matching the rest of this codebase's approach
(see :mod:`cvbuilder.matcher`) — no external AI calls. Two heuristics,
picked by source type:

- ``form`` / ``matrix`` (questionnaires, competency matrices): the
  author already wrote one question or criterion per line, so each
  non-empty line becomes a prompt verbatim.
- ``job`` (job postings): postings are prose with embedded requirement
  bullets, not literal questions, so bullet/numbered lines are pulled
  out and reframed as "Describe your experience with: <requirement>."
  If no bullets are found, sentences containing common requirement
  language ("experience", "years", "proficiency", ...) are used as a
  fallback so short, unbulleted postings still produce something.
"""

from __future__ import annotations

import re

_BULLET_RE = re.compile(r"^\s*(?:[-*•‣]|\d+[.)]|[a-zA-Z][.)])\s+(.*\S)\s*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_REQUIREMENT_HINTS = (
    "experience",
    "years",
    "proficiency",
    "familiarity",
    "knowledge of",
    "ability to",
    "background in",
    "skilled",
    "expertise",
)
MAX_QUESTIONS = 30


def extract_questions(text: str, source_type: str) -> list[str]:
    """Extract candidate question/criterion prompts from pasted text.

    Args:
        text: Raw pasted text (job posting, questionnaire, or matrix).
        source_type: One of "job", "form", "matrix".

    Returns:
        Ordered, de-duplicated prompts (capped at ``MAX_QUESTIONS``).
    """
    if source_type == "job":
        prompts = _extract_from_job_posting(text)
    else:
        prompts = _extract_line_by_line(text)
    seen: set[str] = set()
    unique: list[str] = []
    for prompt in prompts:
        key = prompt.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(prompt)
        if len(unique) >= MAX_QUESTIONS:
            break
    return unique


def _extract_line_by_line(text: str) -> list[str]:
    """Each non-empty line becomes one prompt, stripped of bullet markers."""
    prompts = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        bullet_match = _BULLET_RE.match(line)
        prompts.append(bullet_match.group(1) if bullet_match else line)
    return prompts


def _extract_from_job_posting(text: str) -> list[str]:
    """Pull bullet requirements (or hint-matching sentences) from a posting."""
    bullets: list[str] = []
    for raw_line in text.splitlines():
        match = _BULLET_RE.match(raw_line.strip())
        if match:
            bullets.append(match.group(1))
    if bullets:
        return [f"Describe your experience with: {bullet}" for bullet in bullets]

    sentences = _SENTENCE_SPLIT_RE.split(" ".join(text.split()))
    hints: list[str] = []
    for sentence in sentences:
        clean = sentence.strip()
        if not clean:
            continue
        lowered = clean.lower()
        if any(hint in lowered for hint in _REQUIREMENT_HINTS):
            hints.append(f"Describe your experience with: {clean}")
    return hints
