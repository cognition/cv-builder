"""Tests for applying Tailor selections into the Working Draft CV."""

from __future__ import annotations

from pathlib import Path

import pytest

from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.importer import SnippetImporter
from cvbuilder.models import DetailLevel, Snippet, SnippetVariant
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


def _bio_with_levels(database: SnippetDatabase, content_hash: str) -> int:
    """Create a bio snippet with brief and standard variants."""
    snippet_id = database.create_snippet(
        Snippet(
            category="bio",
            heading="Intro",
            tags=["test"],
            source_path=None,
            content_hash=content_hash,
        )
    )
    database.upsert_variant(
        SnippetVariant(
            snippet_id=snippet_id,
            detail_level=DetailLevel.BRIEF.value,
            content="Brief sibling bio line.",
        )
    )
    database.upsert_variant(
        SnippetVariant(
            snippet_id=snippet_id,
            detail_level=DetailLevel.STANDARD.value,
            content="Standard sibling bio line.",
        )
    )
    return snippet_id


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

    def test_apply_skips_missing_snippet_ids(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """Stale snippet ids are skipped; valid ones still update the draft."""
        applier, store, database = _applier(tmp_path, repo_fixture)
        bios = database.list_snippets(category="bio")
        assert bios and bios[0].id is not None
        result = applier.apply_selections(
            [
                {
                    "snippet_id": 999_001,
                    "detail_level": DetailLevel.STANDARD.value,
                    "section": "bio",
                },
                {
                    "snippet_id": bios[0].id,
                    "detail_level": DetailLevel.STANDARD.value,
                    "section": "bio",
                },
            ]
        )
        assert result["ok"] is True
        assert result["selection_count"] == 1
        assert len(result["skipped"]) == 1
        assert result["skipped"][0]["snippet_id"] == 999_001
        working = store.get_working()
        assert working is not None
        variant = bios[0].variant_for(DetailLevel.STANDARD.value)
        assert variant is not None
        assert variant.content.strip()[:40] in working.content_yaml

    def test_apply_rejects_when_every_snippet_is_missing(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """Apply with only missing ids must fail clearly."""
        applier, _store, _database = _applier(tmp_path, repo_fixture)
        with pytest.raises(ValueError, match="snippet 999001 not found"):
            applier.apply_selections(
                [
                    {
                        "snippet_id": 999_001,
                        "detail_level": DetailLevel.STANDARD.value,
                        "section": "bio",
                    }
                ]
            )

    def test_merge_appends_without_wiping_existing(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """Merge keeps existing bio text and appends another bio snippet."""
        applier, store, database = _applier(tmp_path, repo_fixture)
        bios = database.list_snippets(category="bio")
        assert len(bios) >= 1
        store.upsert_working(
            "person:\n  first_name: Homer\n"
            "bio:\n  - Keep this existing bio line.\n"
            "skills:\n  technical: []\n  functional: []\n"
            "experience: []\neducation: []\n"
        )
        result = applier.merge_selections(
            [
                {
                    "snippet_id": bios[0].id,
                    "detail_level": DetailLevel.STANDARD.value,
                    "section": "bio",
                }
            ]
        )
        assert result["added_count"] == 1
        working = store.get_working()
        assert working is not None
        assert "Keep this existing bio line." in working.content_yaml
        variant = bios[0].variant_for(DetailLevel.STANDARD.value)
        assert variant is not None
        assert variant.content.strip()[:40] in working.content_yaml

    def test_merge_skips_duplicate_content(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """Merging the same bio twice should skip the second merge."""
        applier, _store, database = _applier(tmp_path, repo_fixture)
        bios = database.list_snippets(category="bio")
        selection = {
            "snippet_id": bios[0].id,
            "detail_level": DetailLevel.STANDARD.value,
            "section": "bio",
        }
        first = applier.merge_selections([selection])
        second = applier.merge_selections([selection])
        assert first["added_count"] == 1
        assert second["added_count"] == 0
        assert second["skipped_count"] == 1

    def test_merge_warns_on_sibling_detail_level(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """Adding another detail level keeps both and records highlights."""
        applier, store, database = _applier(tmp_path, repo_fixture)
        snippet_id = _bio_with_levels(database, "conflict-demo")
        applier.merge_selections(
            [
                {
                    "snippet_id": snippet_id,
                    "detail_level": DetailLevel.STANDARD.value,
                    "section": "bio",
                }
            ]
        )
        result = applier.merge_selections(
            [
                {
                    "snippet_id": snippet_id,
                    "detail_level": DetailLevel.BRIEF.value,
                    "section": "bio",
                }
            ]
        )
        assert result["added_count"] == 1
        assert result["warning"]
        marks = {item["mark"] for item in result["conflicts"]}
        assert marks == {"existing", "new"}
        working = store.get_working()
        assert working is not None
        assert "Standard sibling bio line." in working.content_yaml
        assert "Brief sibling bio line." in working.content_yaml
        assert len(store.list_conflict_highlights(working.id)) >= 2

    def test_resolve_keep_existing_removes_new(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """keep_existing drops the red/new needles and clears highlights."""
        applier, store, database = _applier(tmp_path, repo_fixture)
        snippet_id = database.create_snippet(
            Snippet(
                category="bio",
                heading="Intro",
                tags=["test"],
                source_path=None,
                content_hash="conflict-resolve",
            )
        )
        database.upsert_variant(
            SnippetVariant(
                snippet_id=snippet_id,
                detail_level=DetailLevel.BRIEF.value,
                content="Keep blue existing bio.",
            )
        )
        database.upsert_variant(
            SnippetVariant(
                snippet_id=snippet_id,
                detail_level=DetailLevel.STANDARD.value,
                content="Drop red new bio.",
            )
        )
        applier.merge_selections(
            [
                {
                    "snippet_id": snippet_id,
                    "detail_level": DetailLevel.BRIEF.value,
                    "section": "bio",
                }
            ]
        )
        applier.merge_selections(
            [
                {
                    "snippet_id": snippet_id,
                    "detail_level": DetailLevel.STANDARD.value,
                    "section": "bio",
                }
            ]
        )
        resolved = applier.resolve_conflicts("keep_existing")
        assert resolved["ok"] is True
        working = store.get_working()
        assert working is not None
        assert "Keep blue existing bio." in working.content_yaml
        assert "Drop red new bio." not in working.content_yaml
        assert store.list_conflict_highlights(working.id) == []

    def test_load_variant_replaces_content_keeps_person(
        self, tmp_path: Path, repo_fixture: Path
    ) -> None:
        """Loading a version replaces body sections but keeps Working Draft person."""
        applier, store, _database = _applier(tmp_path, repo_fixture)
        store.upsert_working(
            "person:\n  first_name: Ramon\n  last_name: Brooker\n"
            "bio:\n  - Old working bio.\n"
            "skills:\n  technical:\n    - Old skill\n  functional: []\n"
            "experience: []\neducation:\n  - Old school\n"
        )
        store.upsert_variant(
            "app-ready",
            "person:\n  first_name: Homer\n  last_name: Simpson\n"
            "bio:\n  - Version bio line.\n"
            "skills:\n  technical:\n    - Version skill\n  functional: []\n"
            "experience:\n  - company: Version Co\n    role: Tester\n"
            "    subsections: []\n"
            "education:\n  - Version University\n"
            "panels: []\n",
        )
        result = applier.load_variant("app-ready")
        assert result["ok"] is True
        assert result["name"] == "app-ready"
        working = store.get_working()
        assert working is not None
        assert "first_name: Ramon" in working.content_yaml
        assert "last_name: Brooker" in working.content_yaml
        assert "Homer" not in working.content_yaml
        assert "Version bio line." in working.content_yaml
        assert "Version skill" in working.content_yaml
        assert "Version Co" in working.content_yaml
        assert "Version University" in working.content_yaml
        assert "Old working bio." not in working.content_yaml
        assert "Old skill" not in working.content_yaml

    def test_load_variant_missing_raises(self, tmp_path: Path, repo_fixture: Path) -> None:
        """Missing version name raises KeyError."""
        applier, _store, _database = _applier(tmp_path, repo_fixture)
        with pytest.raises(KeyError, match="missing-version"):
            applier.load_variant("missing-version")
