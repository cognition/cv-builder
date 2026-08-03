"""Tests for ``SnippetDatabase`` CRUD and filtering."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cvbuilder.database import SnippetDatabase
from cvbuilder.models import DetailLevel, Snippet, SnippetVariant

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


class TestSnippetDatabase:
    """Verify schema creation, upserts, and list filters."""

    def test_create_and_get_snippet(self, snippet_db: SnippetDatabase) -> None:
        """Creating a snippet with a variant should round-trip."""
        snippet_id = snippet_db.create_snippet(
            Snippet(
                category="bio",
                heading="Intro",
                tags=["bio"],
                source_path="test#bio",
                content_hash="abc",
            )
        )
        snippet_db.upsert_variant(
            SnippetVariant(
                snippet_id=snippet_id,
                detail_level=DetailLevel.STANDARD.value,
                content="Hello world",
            )
        )
        loaded = snippet_db.get_snippet(snippet_id)
        assert loaded is not None
        assert loaded.heading == "Intro"
        assert len(loaded.variants) == 1
        assert loaded.variants[0].content == "Hello world"

    def test_upsert_by_source_is_idempotent(
        self, snippet_db: SnippetDatabase
    ) -> None:
        """Re-upserting the same source/hash should not duplicate rows."""
        snippet = Snippet(
            category="experience",
            company="Acme",
            heading="Platform",
            tags=["experience"],
            source_path="data.yaml#exp[0]",
            content_hash="hash1",
        )
        variant = SnippetVariant(
            detail_level=DetailLevel.STANDARD.value,
            content="Built things",
        )
        first = snippet_db.upsert_by_source(snippet, variant)
        second = snippet_db.upsert_by_source(snippet, variant)
        assert first == second
        results = snippet_db.list_snippets(category="experience")
        assert len(results) == 1

    def test_list_filters_by_search_and_tag(
        self, snippet_db: SnippetDatabase
    ) -> None:
        """Search and tag filters should narrow results."""
        sid = snippet_db.create_snippet(
            Snippet(
                category="skill",
                heading="Python",
                tags=["skill", "technical"],
                source_path="skills#0",
                content_hash="s0",
            )
        )
        snippet_db.upsert_variant(
            SnippetVariant(
                snippet_id=sid,
                detail_level=DetailLevel.BRIEF.value,
                content="Python scripting",
            )
        )
        by_search = snippet_db.list_snippets(search="python")
        assert len(by_search) == 1
        by_tag = snippet_db.list_snippets(tag="technical")
        assert len(by_tag) == 1
        missing = snippet_db.list_snippets(tag="missing")
        assert missing == []

    def test_delete_snippet(self, snippet_db: SnippetDatabase) -> None:
        """Deleting a snippet should remove it and report success."""
        sid = snippet_db.create_snippet(
            Snippet(category="part", heading="X", tags=[])
        )
        assert snippet_db.delete_snippet(sid) is True
        assert snippet_db.get_snippet(sid) is None
        assert snippet_db.delete_snippet(sid) is False

    def test_delete_variant(self, snippet_db: SnippetDatabase) -> None:
        """Deleting one detail level should leave other variants intact."""
        sid = snippet_db.create_snippet(
            Snippet(category="bio", heading="Intro", tags=["bio"])
        )
        snippet_db.upsert_variant(
            SnippetVariant(
                snippet_id=sid,
                detail_level=DetailLevel.BRIEF.value,
                content="Short",
            )
        )
        snippet_db.upsert_variant(
            SnippetVariant(
                snippet_id=sid,
                detail_level=DetailLevel.STANDARD.value,
                content="Longer",
            )
        )
        assert snippet_db.delete_variant(sid, DetailLevel.BRIEF.value) is True
        loaded = snippet_db.get_snippet(sid)
        assert loaded is not None
        assert loaded.variant_for(DetailLevel.BRIEF.value) is None
        assert loaded.variant_for(DetailLevel.STANDARD.value) is not None
