"""Tests for editor undo/redo history stored in SQLite."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


def _store(tmp_path: Path) -> DocumentStore:
    """Create an initialised document store for history tests."""
    database = SnippetDatabase(tmp_path / "snippets.db")
    database.ensure_schema()
    return DocumentStore(database)


def _master_text(store: DocumentStore) -> str:
    """Return the current master YAML text from the store."""
    document = store.get_master()
    assert document is not None
    return document.content_yaml


class TestEditHistory:
    """Verify snapshot push / undo / redo against master cv_documents."""

    def test_undo_redo_round_trip(self, tmp_path: Path) -> None:
        """Undo should restore the prior YAML; redo should re-apply it."""
        store = _store(tmp_path)
        document = store.upsert_master("bio:\n  - one\n")
        assert document.id is not None

        store.push_before_change(document.id, "edit", _master_text(store))
        store.upsert_master("bio:\n  - two\n")
        assert store.history_status(document.id)["can_undo"] is True
        assert store.history_status(document.id)["can_redo"] is False

        result = store.undo(document.id)
        assert _master_text(store) == "bio:\n  - one\n"
        assert result["can_redo"] is True

        store.redo(document.id)
        assert _master_text(store) == "bio:\n  - two\n"
        assert store.history_status(document.id)["can_undo"] is True

    def test_new_change_clears_redo(self, tmp_path: Path) -> None:
        """A fresh change after undo should discard the redo stack."""
        store = _store(tmp_path)
        document = store.upsert_master("v: 1\n")
        assert document.id is not None

        store.push_before_change(document.id, "a", _master_text(store))
        store.upsert_master("v: 2\n")
        store.undo(document.id)
        assert store.history_status(document.id)["can_redo"] is True

        store.push_before_change(document.id, "b", _master_text(store))
        store.upsert_master("v: 3\n")
        assert store.history_status(document.id)["can_redo"] is False

    def test_undo_empty_returns_unchanged_status(self, tmp_path: Path) -> None:
        """Undo with an empty stack should leave history unavailable."""
        store = _store(tmp_path)
        document = store.upsert_master("v: 1\n")
        assert document.id is not None

        result = store.undo(document.id)

        assert result["can_undo"] is False
        assert result["can_redo"] is False
        assert _master_text(store) == "v: 1\n"

    def test_ten_deep_undo_and_redo(self, tmp_path: Path) -> None:
        """At least 10 undos should be possible, and 10 redos back to head."""
        store = _store(tmp_path)
        document = store.upsert_master("v: 0\n")
        assert document.id is not None

        for i in range(1, 11):
            store.push_before_change(document.id, f"edit-{i}", _master_text(store))
            store.upsert_master(f"v: {i}\n")

        for i in range(10, 0, -1):
            store.undo(document.id)
            assert _master_text(store) == f"v: {i - 1}\n"
        assert store.history_status(document.id)["can_undo"] is False

        for i in range(1, 11):
            store.redo(document.id)
            assert _master_text(store) == f"v: {i}\n"
        assert store.history_status(document.id)["can_redo"] is False

    def test_change_after_partial_redo_discards_remaining_redos(
        self, tmp_path: Path
    ) -> None:
        """Undo 8, redo 6, then edit: the 2 still-ahead states are lost.

        Net position after undo(8)/redo(6) is head-2 (two snapshots — the
        ones for the last two undone-but-not-redone edits — still sit on
        the redo stack, reachable by redoing further). A fresh edit from
        here becomes the new head and discards those, exactly like a
        normal browser undo/redo stack: redo is only valid until the next
        change branches off from a point behind head.
        """
        store = _store(tmp_path)
        document = store.upsert_master("v: 0\n")
        assert document.id is not None

        for i in range(1, 11):
            store.push_before_change(document.id, f"edit-{i}", _master_text(store))
            store.upsert_master(f"v: {i}\n")

        for _ in range(8):
            store.undo(document.id)
        assert _master_text(store) == "v: 2\n"

        for _ in range(6):
            store.redo(document.id)
        assert _master_text(store) == "v: 8\n"
        assert store.history_status(document.id)["redo_count"] == 2

        store.push_before_change(document.id, "branch", _master_text(store))
        store.upsert_master("v: NEW\n")

        assert store.history_status(document.id)["can_redo"] is False
        store.redo(document.id)
        assert _master_text(store) == "v: NEW\n"

        # v9 and v10 are gone for good — undoing from the new head walks
        # straight back through v8, v7, ... never revisiting them.
        store.undo(document.id)
        assert _master_text(store) == "v: 8\n"
