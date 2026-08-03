"""Tests for draft persistence in ``SnippetDatabase``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cvbuilder.database import SnippetDatabase

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


class TestDrafts:
    """Verify save/list/get/delete for named builder drafts."""

    def test_save_and_get_draft(self, snippet_db: SnippetDatabase) -> None:
        """Saving a draft should round-trip selections by name."""
        selections = [
            {"snippet_id": 1, "detail_level": "standard", "section": "bio"}
        ]
        saved = snippet_db.save_draft("ircc", selections)
        assert saved.name == "ircc"
        loaded = snippet_db.get_draft("ircc")
        assert loaded is not None
        assert loaded.selections == selections

    def test_save_draft_updates_existing(
        self, snippet_db: SnippetDatabase
    ) -> None:
        """Re-saving the same name should replace selections."""
        snippet_db.save_draft("draft-a", [{"snippet_id": 1}])
        snippet_db.save_draft("draft-a", [{"snippet_id": 2}, {"snippet_id": 3}])
        loaded = snippet_db.get_draft("draft-a")
        assert loaded is not None
        assert len(loaded.selections) == 2
        assert loaded.selections[0]["snippet_id"] == 2

    def test_list_and_delete_draft(self, snippet_db: SnippetDatabase) -> None:
        """Listing and deleting drafts should behave as expected."""
        snippet_db.save_draft("one", [])
        snippet_db.save_draft("two", [{"snippet_id": 9}])
        names = {draft.name for draft in snippet_db.list_drafts()}
        assert names == {"one", "two"}
        assert snippet_db.delete_draft("one") is True
        assert snippet_db.get_draft("one") is None
        assert snippet_db.delete_draft("one") is False

    def test_empty_name_rejected(self, snippet_db: SnippetDatabase) -> None:
        """Blank draft names should raise ValueError."""
        with pytest.raises(ValueError):
            snippet_db.save_draft("   ", [])
