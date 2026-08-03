"""Tests for editor undo/redo history."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import cvweb  # noqa: E402  # pylint: disable=wrong-import-position


class TestEditHistory:
    """Verify snapshot push / undo / redo against a temp data file."""

    def test_undo_redo_round_trip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Undo should restore the prior YAML; redo should re-apply it."""
        data_file = tmp_path / "data.yaml"
        data_file.write_text("bio:\n  - one\n", encoding="utf-8")
        history_path = tmp_path / "history.json"
        monkeypatch.setattr(cvweb, "DATA_FILE", data_file)
        history = cvweb.EditHistory(path=history_path, max_entries=10)

        history.push_before_change("edit")
        data_file.write_text("bio:\n  - two\n", encoding="utf-8")
        assert history.status()["can_undo"] is True
        assert history.status()["can_redo"] is False

        result = history.undo()
        assert data_file.read_text(encoding="utf-8") == "bio:\n  - one\n"
        assert result["can_redo"] is True
        assert result["label"] == "edit"

        history.redo()
        assert data_file.read_text(encoding="utf-8") == "bio:\n  - two\n"
        assert history.status()["can_undo"] is True

    def test_new_change_clears_redo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fresh change after undo should discard the redo stack."""
        data_file = tmp_path / "data.yaml"
        data_file.write_text("v: 1\n", encoding="utf-8")
        monkeypatch.setattr(cvweb, "DATA_FILE", data_file)
        history = cvweb.EditHistory(path=tmp_path / "h.json")

        history.push_before_change("a")
        data_file.write_text("v: 2\n", encoding="utf-8")
        history.undo()
        assert history.status()["can_redo"] is True

        history.push_before_change("b")
        data_file.write_text("v: 3\n", encoding="utf-8")
        assert history.status()["can_redo"] is False

    def test_undo_empty_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Undo with an empty stack should raise ValueError."""
        data_file = tmp_path / "data.yaml"
        data_file.write_text("v: 1\n", encoding="utf-8")
        monkeypatch.setattr(cvweb, "DATA_FILE", data_file)
        history = cvweb.EditHistory(path=tmp_path / "h.json")
        with pytest.raises(ValueError):
            history.undo()

    def test_ten_deep_undo_and_redo(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """At least 10 undos should be possible, and 10 redos back to head."""
        data_file = tmp_path / "data.yaml"
        data_file.write_text("v: 0\n", encoding="utf-8")
        monkeypatch.setattr(cvweb, "DATA_FILE", data_file)
        history = cvweb.EditHistory(path=tmp_path / "h.json")

        for i in range(1, 11):
            history.push_before_change(f"edit-{i}")
            data_file.write_text(f"v: {i}\n", encoding="utf-8")

        for i in range(10, 0, -1):
            history.undo()
            assert data_file.read_text(encoding="utf-8") == f"v: {i - 1}\n"
        assert history.status()["can_undo"] is False

        for i in range(1, 11):
            history.redo()
            assert data_file.read_text(encoding="utf-8") == f"v: {i}\n"
        assert history.status()["can_redo"] is False

    def test_change_after_partial_redo_discards_remaining_redos(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Undo 8, redo 6, then edit: the 2 still-ahead states are lost.

        Net position after undo(8)/redo(6) is head-2 (two snapshots — the
        ones for the last two undone-but-not-redone edits — still sit on
        the redo stack, reachable by redoing further). A fresh edit from
        here becomes the new head and discards those, exactly like a
        normal browser undo/redo stack: redo is only valid until the next
        change branches off from a point behind head.
        """
        data_file = tmp_path / "data.yaml"
        data_file.write_text("v: 0\n", encoding="utf-8")
        monkeypatch.setattr(cvweb, "DATA_FILE", data_file)
        history = cvweb.EditHistory(path=tmp_path / "h.json")

        for i in range(1, 11):
            history.push_before_change(f"edit-{i}")
            data_file.write_text(f"v: {i}\n", encoding="utf-8")

        for _ in range(8):
            history.undo()
        assert data_file.read_text(encoding="utf-8") == "v: 2\n"

        for _ in range(6):
            history.redo()
        assert data_file.read_text(encoding="utf-8") == "v: 8\n"
        assert history.status()["redo_depth"] == 2  # v9 and v10 still redoable

        history.push_before_change("branch")
        data_file.write_text("v: NEW\n", encoding="utf-8")

        assert history.status()["can_redo"] is False
        with pytest.raises(ValueError):
            history.redo()

        # v9 and v10 are gone for good — undoing from the new head walks
        # straight back through v8, v7, ... never revisiting them.
        history.undo()
        assert data_file.read_text(encoding="utf-8") == "v: 8\n"
