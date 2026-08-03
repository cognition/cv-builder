"""Tests for ``SnippetImporter`` seeding behaviour."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cvbuilder.database import SnippetDatabase
from cvbuilder.importer import SnippetImporter
from cvbuilder.models import DetailLevel

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


class TestSnippetImporter:
    """Verify YAML and markdown seeding into SQLite."""

    def test_seed_from_yaml_and_markdown(
        self, repo_fixture: Path, tmp_path: Path
    ) -> None:
        """Importer should create bio, skill, experience, and markdown rows."""
        database = SnippetDatabase(tmp_path / "seed.db")
        importer = SnippetImporter(database=database, repo_root=repo_fixture)
        stats = importer.seed()
        assert stats["yaml_bio"] == 1
        assert stats["yaml_skills"] == 2
        assert stats["yaml_experience"] >= 1
        assert stats["markdown"] >= 2

        bios = database.list_snippets(category="bio")
        assert len(bios) == 1
        assert bios[0].variant_for(DetailLevel.STANDARD.value) is not None

        detailed = database.list_snippets(detail_level=DetailLevel.DETAILED.value)
        assert detailed
        assert any(s.category == "experience" for s in detailed)

    def test_seed_is_idempotent(
        self, repo_fixture: Path, tmp_path: Path
    ) -> None:
        """Running seed twice should not inflate snippet counts."""
        database = SnippetDatabase(tmp_path / "seed2.db")
        importer = SnippetImporter(database=database, repo_root=repo_fixture)
        first = importer.seed()
        second = importer.seed()
        assert first == second
        all_snippets = database.list_snippets()
        assert len(all_snippets) == sum(first.values())
