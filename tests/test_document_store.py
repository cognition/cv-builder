"""Unit tests for DocumentStore CRUD, history, and pins."""

from __future__ import annotations

import json
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
        assert master.kind == "master"
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

    def test_restore_pin_creates_before_restore_pin(self, tmp_path: Path) -> None:
        """Restoring a pin preserves the pre-restore state as a labelled pin."""
        store = _store(tmp_path)
        doc = store.upsert_master("bio:\n  - pinned\n")
        pin = store.create_pin(doc.id, "checkpoint")
        store.upsert_master("bio:\n  - later\n")

        store.restore_pin(pin.id)

        labels = [saved_pin.label for saved_pin in store.list_pins(doc.id)]
        assert f"before-restore:{pin.id}" in labels

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

    def test_corrupt_history_logs_warning_and_resets_both_stacks(
        self, tmp_path: Path, caplog: LogCaptureFixture
    ) -> None:
        """Either corrupt history stack resets undo and redo with a warning."""
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
                (
                    doc.id,
                    "{bad json",
                    '[{"label": "redo", "text": "bio:\\n  - redo\\n"}]',
                ),
            )

        with caplog.at_level(logging.WARNING):
            status = store.history_status(doc.id)

        assert status["undo_count"] == 0
        assert status["redo_count"] == 0
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

    def test_upsert_working_alias_persists_master_kind(self, tmp_path: Path) -> None:
        """The compatibility alias still stores the approved master kind."""
        store = _store(tmp_path)
        doc = store.upsert_working("person:\n  first_name: Homer\nbio:\n  - hi\n")
        assert doc.kind == "master"
        assert store.get_working() is not None
        assert "Homer" in store.get_working().content_yaml

    def test_create_pin_contains_content_and_history_only(self, tmp_path: Path) -> None:
        """Pin payloads freeze content plus undo/redo stacks only."""
        store = _store(tmp_path)
        doc = store.upsert_master("bio:\n  - pinned\n")
        store.push_before_change(doc.id, "edit", "bio:\n  - before\n")

        pin = store.create_pin(doc.id, "checkpoint")

        payload = pin.to_dict()
        assert payload["content_yaml"] == "bio:\n  - pinned\n"
        assert payload["undo"] == [{"label": "edit", "text": "bio:\n  - before\n"}]
        assert "selections" not in payload


class TestBootstrap:
    """One-time import from on-disk YAML into the database."""

    def test_bootstrap_imports_master_and_variants(self, tmp_path: Path) -> None:
        """Import master YAML and named variant YAML files."""
        repo = tmp_path / "repo"
        (repo / "cv" / "web").mkdir(parents=True)
        (repo / "cv" / "variants" / "demo").mkdir(parents=True)
        (repo / "cv" / "web" / "data.yaml").write_text(
            "bio:\n  - master\n", encoding="utf-8"
        )
        (repo / "cv" / "variants" / "demo" / "data.yaml").write_text(
            "bio:\n  - variant\n", encoding="utf-8"
        )
        store = _store(tmp_path)
        result = store.bootstrap_from_filesystem(repo)
        assert result["master"] == 1
        assert result["variants"] == 1
        master = store.get_master()
        assert master is not None
        assert "master" in master.content_yaml
        assert store.get_variant("demo") is not None

    def test_bootstrap_is_noop_when_master_exists(self, tmp_path: Path) -> None:
        """Existing master content prevents any filesystem import."""
        repo = tmp_path / "repo"
        (repo / "cv" / "web").mkdir(parents=True)
        (repo / "cv" / "web" / "data.yaml").write_text(
            "bio:\n  - file\n", encoding="utf-8"
        )
        store = _store(tmp_path)
        store.upsert_master("bio:\n  - db\n")
        result = store.bootstrap_from_filesystem(repo)
        assert result["master"] == 0
        master = store.get_master()
        assert master is not None
        assert "db" in master.content_yaml

    def test_bootstrap_imports_master_history(self, tmp_path: Path) -> None:
        """Import legacy master history when the DB history is empty."""
        repo = tmp_path / "repo"
        history_path = repo / "data" / "edit-history.json"
        (repo / "cv" / "web").mkdir(parents=True)
        history_path.parent.mkdir(parents=True)
        (repo / "cv" / "web" / "data.yaml").write_text(
            "bio:\n  - current\n", encoding="utf-8"
        )
        history_path.write_text(
            json.dumps(
                {
                    "undo": [{"label": "legacy", "text": "bio:\n  - old\n"}],
                    "redo": [{"label": "legacy-redo", "text": "bio:\n  - new\n"}],
                }
            ),
            encoding="utf-8",
        )
        store = _store(tmp_path)

        result = store.bootstrap_from_filesystem(repo)

        master = store.get_master()
        assert master is not None
        assert result["history"] == 1
        assert store.history_status(master.id)["undo_count"] == 1
        assert store.history_status(master.id)["redo_count"] == 1
