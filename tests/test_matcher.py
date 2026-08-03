"""Tests for keyword-based ``SnippetMatcher`` ranking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cvbuilder.database import SnippetDatabase
from cvbuilder.matcher import SnippetMatcher
from cvbuilder.models import DetailLevel, Snippet, SnippetVariant

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


class TestSnippetMatcher:
    """Verify tokenisation and weighted ranking."""

    def test_tokenize_strips_stopwords(self) -> None:
        """Common stopwords should be removed from the term set."""
        terms = SnippetMatcher.tokenize(
            "The role requires Python and Kubernetes experience"
        )
        assert "python" in terms
        assert "kubernetes" in terms
        assert "the" not in terms
        assert "and" not in terms
        assert "experience" not in terms

    def test_match_ranks_tag_hits_highest(
        self, snippet_db: SnippetDatabase
    ) -> None:
        """A tag match should outrank a content-only match."""
        sid_tag = snippet_db.create_snippet(
            Snippet(
                category="experience",
                heading="Platform",
                tags=["kubernetes", "devops"],
            )
        )
        snippet_db.upsert_variant(
            SnippetVariant(
                snippet_id=sid_tag,
                detail_level=DetailLevel.STANDARD.value,
                content="Led delivery work.",
            )
        )
        sid_content = snippet_db.create_snippet(
            Snippet(
                category="experience",
                heading="Other",
                tags=["general"],
            )
        )
        snippet_db.upsert_variant(
            SnippetVariant(
                snippet_id=sid_content,
                detail_level=DetailLevel.STANDARD.value,
                content="Worked with kubernetes clusters daily.",
            )
        )
        matcher = SnippetMatcher(snippet_db)
        results = matcher.match("Looking for Kubernetes expertise", limit=10)
        assert results
        assert results[0].snippet.id == sid_tag
        assert "kubernetes" in results[0].matched_terms

    def test_match_empty_text(self, snippet_db: SnippetDatabase) -> None:
        """Empty or stopword-only text should return no matches."""
        matcher = SnippetMatcher(snippet_db)
        assert matcher.match("the and of") == []
