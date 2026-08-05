"""Schema tests for CV documents, history, and pins tables."""

from __future__ import annotations

from pathlib import Path

from cvbuilder.database import SnippetDatabase


class TestDocumentSchema:
    """Ensure document-related tables exist after ensure_schema."""

    def test_ensure_schema_creates_document_tables(self, tmp_path: Path) -> None:
        """cv_documents, cv_history, and cv_pins must exist."""
        database = SnippetDatabase(tmp_path / "snippets.db")
        database.ensure_schema()
        with database.connect() as connection:
            names = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        assert "cv_documents" in names
        assert "cv_history" in names
        assert "cv_pins" in names

    def test_cv_pins_excludes_tailor_selections_json(self, tmp_path: Path) -> None:
        """Task 2 pins must not include Tailor selections_json."""
        database = SnippetDatabase(tmp_path / "snippets.db")
        database.ensure_schema()
        with database.connect() as connection:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(cv_pins)")
            }
        assert "selections_json" not in columns
