"""Shared pytest fixtures for the CV builder tests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _pytest.fixtures import FixtureRequest
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


@pytest.fixture
def repo_fixture(tmp_path: Path) -> Path:
    """Create a minimal repository tree for importer/composer tests.

    Args:
        tmp_path: Pytest temporary directory.

    Returns:
        Path to the fake repository root.
    """
    web = tmp_path / "cv" / "web"
    web.mkdir(parents=True)
    content_exp = tmp_path / "content" / "work-experience"
    content_parts = tmp_path / "content" / "parts"
    content_exp.mkdir(parents=True)
    content_parts.mkdir(parents=True)

    (web / "data.yaml").write_text(
        """
person:
  name: Test Person
  tagline: Builder
  quote: Test quote
  photo: "../../assets/images/test.jpg"
  email: test@example.com
  mobile: "555-0100"
  github: {handle: tester, url: "https://example.com/gh"}
  linkedin: {handle: tester, url: "https://example.com/li"}
  strengths: ["Learner"]

skills:
  technical:
    - Python
  functional:
    - Mentoring

bio:
  - >
    First bio paragraph about the candidate.

experience:
  - company: Acme Corp
    role: Engineer
    dates: "2020 – 2022"
    location: Ottawa
    subsections:
      - heading: Platform Work
        bullets:
          - Built pipelines.
          - Mentored juniors.

education:
  - B.Sc. Computer Science
""".strip()
        + "\n",
        encoding="utf-8",
    )

    (content_exp / "acme.md").write_text(
        """# Acme Corp

## Deep Dive

Detailed migration notes and stakeholder interviews.
""",
        encoding="utf-8",
    )
    (content_parts / "intro.md").write_text(
        """# Intro

Reusable intro block for cover letters.
""",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def snippet_db(tmp_path: Path):
    """Provide an initialised ``SnippetDatabase`` in a temp file.

    Args:
        tmp_path: Pytest temporary directory.

    Yields:
        A ready-to-use SnippetDatabase.
    """
    from cvbuilder.database import SnippetDatabase

    database = SnippetDatabase(tmp_path / "snippets.db")
    database.ensure_schema()
    return database
