"""Unit tests for DocumentStore CRUD, history, and pins."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore

if TYPE_CHECKING:
    from _pytest.logging import LogCaptureFixture


def _store(tmp_path: Path) -> DocumentStore:
    """Create an initialised document store for tests."""
    database = SnippetDatabase(tmp_path / "snippets.db")
    database.ensure_schema()
    return DocumentStore(database)


class TestDocumentStore:
    """Core document and history behaviour."""

    def test_upsert_and_get_master(self, tmp_path: Path) -> None:
        """Master content can be created and loaded."""
        store = _store(tmp_path)
        store.upsert_master("bio:\n  - hello\n")
        master = store.get_master()
        assert master is not None
        assert "hello" in master.content_yaml

    def test_undo_redo_round_trip(self, tmp_path: Path) -> None:
        """Undo restores prior content and redo reapplies the undone content."""
        store = _store(tmp_path)
        doc = store.upsert_master("bio:\n  - one\n")
        store.push_before_change(doc.id, "edit", doc.content_yaml)
        store.upsert_master("bio:\n  - two\n")
        result = store.undo(doc.id)
        undone = store.get_master()
        assert undone is not None
        assert "one" in undone.content_yaml
        assert result["can_redo"] is True
        store.redo(doc.id)
        redone = store.get_master()
        assert redone is not None
        assert "two" in redone.content_yaml

    def test_pin_restore_brings_content_and_stacks(self, tmp_path: Path) -> None:
        """Restoring a pin brings back its content and leaves undo available."""
        store = _store(tmp_path)
        doc = store.upsert_master("bio:\n  - pinned\n")
        store.push_before_change(doc.id, "edit", "bio:\n  - pinned\n")
        store.upsert_master("bio:\n  - intermediate\n")
        pin = store.create_pin(doc.id, "checkpoint")
        master = store.get_master()
        assert master is not None
        store.push_before_change(doc.id, "edit", master.content_yaml)
        store.upsert_master("bio:\n  - later\n")
        store.restore_pin(pin.id)
        restored = store.get_master()
        assert restored is not None
        assert "intermediate" in restored.content_yaml
        status = store.history_status(doc.id)
        assert status["can_undo"] is True

    def test_variant_upsert_and_list(self, tmp_path: Path) -> None:
        """Variants can be saved and listed by name."""
        store = _store(tmp_path)
        store.upsert_variant("nuclear-oncall", "person:\n  first_name: Homer\n")
        names = [v.name for v in store.list_variants()]
        assert names == ["nuclear-oncall"]

    def test_delete_variant_removes_named_variant(self, tmp_path: Path) -> None:
        """Deleting a variant removes only that named variant."""
        store = _store(tmp_path)
        store.upsert_variant("a", "bio:\n  - a\n")
        store.upsert_variant("b", "bio:\n  - b\n")

        store.delete_variant("a")

        assert store.get_variant("a") is None
        assert store.get_variant("b") is not None

    def test_history_is_capped_to_max_history(self, tmp_path: Path) -> None:
        """Undo entries are capped at DocumentStore.MAX_HISTORY."""
        store = _store(tmp_path)
        doc = store.upsert_master("bio:\n  - current\n")

        for index in range(DocumentStore.MAX_HISTORY + 5):
            store.push_before_change(doc.id, f"edit-{index}", f"bio:\n  - {index}\n")

        status = store.history_status(doc.id)
        assert status["undo_count"] == DocumentStore.MAX_HISTORY
        store.undo(doc.id)
        master = store.get_master()
        assert master is not None
        assert f"- {DocumentStore.MAX_HISTORY + 4}" in master.content_yaml

    def test_corrupt_history_logs_warning_and_resets(
        self, tmp_path: Path, caplog: LogCaptureFixture
    ) -> None:
        """Corrupt history JSON is treated as empty history with a warning."""
        store = _store(tmp_path)
        doc = store.upsert_master("bio:\n  - stable\n")
        assert doc.id is not None
        with store.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO cv_history (document_id, undo_json, redo_json)
                VALUES (?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    undo_json = excluded.undo_json,
                    redo_json = excluded.redo_json
                """,
                (doc.id, "{bad json", "[]"),
            )

        with caplog.at_level(logging.WARNING):
            status = store.history_status(doc.id)

        assert status["undo_count"] == 0
        assert "Corrupt CV history" in caplog.text

    def test_missing_document_operations_raise_key_error(self, tmp_path: Path) -> None:
        """History and pin operations fail clearly for unknown documents."""
        store = _store(tmp_path)

        with pytest.raises(KeyError):
            store.push_before_change(999, "edit", "bio:\n  - missing\n")
        with pytest.raises(KeyError):
            store.create_pin(999, "checkpoint")
        with pytest.raises(KeyError):
            store.restore_pin(999)

    def test_upsert_working_and_pin_with_selections(self, tmp_path: Path) -> None:
        """Working doc + pin must round-trip Tailor selections."""
        store = _store(tmp_path)
        doc = store.upsert_working("person:\n  first_name: Homer\nbio:\n  - hi\n")
        assert doc.kind == "working"
        pin = store.create_pin(
            doc.id,
            "ircc-v1",
            selections=[{"snippet_id": 1, "detail_level": "standard"}],
        )
        assert pin.selections == [{"snippet_id": 1, "detail_level": "standard"}]
        listed = store.list_pins(doc.id)
        assert listed[0].selections[0]["snippet_id"] == 1
        assert store.get_working() is not None
        assert "Homer" in store.get_working().content_yaml

    def test_get_working_reads_legacy_master_row(self, tmp_path: Path) -> None:
        """A kind=master row is still found as the working document."""
        store = _store(tmp_path)
        with store.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO cv_documents (kind, name, content_yaml, updated_at)
                VALUES ('master', NULL, ?, datetime('now'))
                """,
                ("bio:\n  - legacy\n",),
            )
        working = store.get_working()
        assert working is not None
        assert "legacy" in working.content_yaml
