"""Tests for applying Tailor selections into the Working Draft CV."""

from __future__ import annotations

from pathlib import Path

import pytest

from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.importer import SnippetImporter
from cvbuilder.models import DetailLevel
from cvbuilder.working_draft import WorkingDraftApplier


def _applier(
    tmp_path: Path, repo_root: Path
) -> tuple[WorkingDraftApplier, DocumentStore, SnippetDatabase]:
    """Create an applier with a seeded library and working document."""
    database = SnippetDatabase(tmp_path / "snippets.db")
    SnippetImporter(database=database, repo_root=repo_root).seed()
    store = DocumentStore(database)
    store.upsert_working(
        "person:\n  first_name: Homer\n  last_name: Simpson\n"
        "bio: []\nskills:\n  technical: []\n  functional: []\n"
        "experience: []\neducation: []\n"
    )
    return WorkingDraftApplier(database, store, repo_root), store, database


class TestWorkingDraftApplier:
    """Apply Tailor selections into the DB working document."""

    def test_apply_updates_working_yaml_without_variants(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """Working blob updates; no variant documents are created."""
        applier, store, database = _applier(tmp_path, repo_fixture)
        bios = database.list_snippets(category="bio")
        assert bios
        before_variants = store.list_variants()
        selections = [
            {
                "snippet_id": bios[0].id,
                "detail_level": DetailLevel.STANDARD.value,
                "section": "bio",
            }
        ]
        result = applier.apply_selections(selections)
        assert result["ok"] is True
        working = store.get_working()
        assert working is not None
        assert "Homer" in working.content_yaml
        variant = bios[0].variant_for(DetailLevel.STANDARD.value)
        assert variant is not None
        assert variant.content.strip()[:40] in working.content_yaml
        assert store.list_variants() == before_variants

    def test_apply_rejects_empty_selections(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """Empty selection list must raise ValueError."""
        applier, _store, _database = _applier(tmp_path, repo_fixture)
        with pytest.raises(ValueError, match="selections"):
            applier.apply_selections([])
