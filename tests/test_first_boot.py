"""Unit tests for first-boot blank vs demo database preparation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.first_boot import FirstBoot

if TYPE_CHECKING:
    pass


def _mini_repo(tmp_path: Path) -> Path:
    """Create a tiny repo with Homer-like YAML and one markdown snippet."""
    repo = tmp_path / "repo"
    (repo / "cv" / "web").mkdir(parents=True)
    (repo / "content" / "parts").mkdir(parents=True)
    (repo / "cv" / "web" / "data.yaml").write_text(
        "person:\n  first_name: Homer\nbio:\n  - Safety first.\n"
        "skills:\n  technical: []\n  functional: []\n"
        "experience: []\neducation: []\n",
        encoding="utf-8",
    )
    (repo / "content" / "parts" / "intro.md").write_text(
        "# Intro\n\n## Alternate bio\n\nA longer intro paragraph.\n",
        encoding="utf-8",
    )
    return repo


class TestFirstBoot:
    """Blank vs demo first-boot preparation."""

    def test_blank_creates_schema_with_zero_snippets(
        self, tmp_path: Path
    ) -> None:
        """DEMO-off path creates DB schema and no snippets."""
        repo = _mini_repo(tmp_path)
        db_path = tmp_path / "data" / "snippets.db"
        result = FirstBoot.prepare_database(db_path, repo, demo=False)
        assert result["demo"] is False
        assert result["snippet_total"] == 0
        assert db_path.is_file()
        database = SnippetDatabase(db_path)
        assert database.list_snippets() == []
        assert DocumentStore(database).get_working() is None

    def test_demo_seeds_snippets_from_yaml(
        self, tmp_path: Path
    ) -> None:
        """DEMO-on path seeds at least the YAML bio snippet."""
        repo = _mini_repo(tmp_path)
        db_path = tmp_path / "data" / "snippets.db"
        result = FirstBoot.prepare_database(db_path, repo, demo=True)
        assert result["demo"] is True
        assert result["snippet_total"] >= 1
        database = SnippetDatabase(db_path)
        snippets = database.list_snippets()
        assert len(snippets) >= 1
