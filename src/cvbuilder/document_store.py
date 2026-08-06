"""Database-backed CV document storage with history and pins."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from cvbuilder.database import SnippetDatabase
from cvbuilder.models import CvDocument, CvHistoryState, CvPin

LOGGER = logging.getLogger(__name__)


class DocumentStore:
    """Database-backed CV documents with transitory undo history and pins."""

    MAX_HISTORY = 50

    def __init__(self, database: SnippetDatabase) -> None:
        """Initialise the document store.

        Args:
            database: SQLite database wrapper with the CV document schema.
        """
        self.database = database

    def bootstrap_from_filesystem(
        self,
        repo_root: Path,
        *,
        history_path: Optional[Path] = None,
    ) -> dict[str, Any]:
        """Import master/variants/history once when DB documents are empty.

        Returns counts: ``{"master": 0|1, "variants": N, "history": 0|1}``.
        No-ops when a master document already exists.
        """
        if os.environ.get("SKIP_FS_BOOTSTRAP") == "1":
            return {"master": 0, "variants": 0, "history": 0}
        if self.get_master() is not None:
            return {"master": 0, "variants": 0, "history": 0}

        counts: dict[str, Any] = {"master": 0, "variants": 0, "history": 0}
        master_path = repo_root / "cv" / "web" / "data.yaml"
        master: Optional[CvDocument] = None
        if master_path.exists():
            master = self.upsert_master(master_path.read_text(encoding="utf-8"))
            counts["master"] = 1

        variants_path = repo_root / "cv" / "variants"
        if variants_path.exists():
            for variant_path in sorted(variants_path.glob("*/data.yaml")):
                self.upsert_variant(
                    variant_path.parent.name,
                    variant_path.read_text(encoding="utf-8"),
                )
                counts["variants"] += 1

        if master is not None and self._bootstrap_history(repo_root, master, history_path):
            counts["history"] = 1
        return counts

    def get_master(self) -> Optional[CvDocument]:
        """Return the master CV document, if one exists."""
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM cv_documents
                WHERE kind = 'master'
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()
            return self._row_to_document(row) if row else None

    def get_working(self) -> Optional[CvDocument]:
        """Return the master CV document for compatibility with older callers."""
        return self.get_master()

    def get_variant(self, name: str) -> Optional[CvDocument]:
        """Return the named variant CV document, if one exists."""
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM cv_documents
                WHERE kind = 'variant' AND name = ?
                """,
                (name,),
            ).fetchone()
            return self._row_to_document(row) if row else None

    def list_variants(self) -> list[CvDocument]:
        """Return all variant CV documents ordered by name."""
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM cv_documents
                WHERE kind = 'variant'
                ORDER BY name ASC
                """
            ).fetchall()
            return [self._row_to_document(row) for row in rows]

    def upsert_master(self, content_yaml: str) -> CvDocument:
        """Create or update the single master CV document."""
        with self.database.connect() as connection:
            existing = connection.execute(
                """
                SELECT id FROM cv_documents
                WHERE kind = 'master'
                ORDER BY id ASC
                LIMIT 1
                """
            ).fetchone()
            if existing:
                document_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE cv_documents
                    SET content_yaml = ?,
                        name = NULL,
                        updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (content_yaml, document_id),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO cv_documents
                        (kind, name, content_yaml, updated_at)
                    VALUES ('master', NULL, ?, datetime('now'))
                    """,
                    (content_yaml,),
                )
                document_id = int(cursor.lastrowid)
            return self._require_document(connection, document_id)

    def upsert_working(self, content_yaml: str) -> CvDocument:
        """Create or update the master CV document for older callers."""
        return self.upsert_master(content_yaml)

    def upsert_variant(self, name: str, content_yaml: str) -> CvDocument:
        """Create or update a named variant CV document."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("variant name is required")
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO cv_documents (kind, name, content_yaml, updated_at)
                VALUES ('variant', ?, ?, datetime('now'))
                ON CONFLICT(name) WHERE kind = 'variant' DO UPDATE SET
                    content_yaml = excluded.content_yaml,
                    updated_at = datetime('now')
                """,
                (clean_name, content_yaml),
            )
            row = connection.execute(
                """
                SELECT * FROM cv_documents
                WHERE kind = 'variant' AND name = ?
                """,
                (clean_name,),
            ).fetchone()
            if row is None:
                raise KeyError(f"CV variant {clean_name!r} was not saved")
            return self._row_to_document(row)

    def delete_variant(self, name: str) -> None:
        """Delete a named variant CV document."""
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM cv_documents
                WHERE kind = 'variant' AND name = ?
                """,
                (name,),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"CV variant {name!r} was not found")

    def history_status(self, document_id: int) -> dict[str, Any]:
        """Return counts and availability for a document's undo/redo history."""
        with self.database.connect() as connection:
            self._require_document(connection, document_id)
            history = self._load_history(connection, document_id)
        return self._history_status(history)

    def push_before_change(self, document_id: int, label: str, text: str) -> None:
        """Push a pre-change text snapshot onto the undo stack."""
        with self.database.connect() as connection:
            self._require_document(connection, document_id)
            history = self._load_history(connection, document_id)
            history.undo.append({"label": label, "text": text})
            history.undo = history.undo[-self.MAX_HISTORY :]
            history.redo = []
            self._save_history(connection, history)

    def undo(self, document_id: int) -> dict[str, Any]:
        """Restore the latest undo entry and move current content to redo."""
        with self.database.connect() as connection:
            document = self._require_document(connection, document_id)
            history = self._load_history(connection, document_id)
            if not history.undo:
                return self._history_status(history)
            entry = history.undo.pop()
            history.redo.append(
                {"label": entry.get("label", "redo"), "text": document.content_yaml}
            )
            history.redo = history.redo[-self.MAX_HISTORY :]
            self._update_document_content(connection, document_id, entry["text"])
            self._save_history(connection, history)
            return self._history_status(history)

    def redo(self, document_id: int) -> dict[str, Any]:
        """Restore the latest redo entry and move current content to undo."""
        with self.database.connect() as connection:
            document = self._require_document(connection, document_id)
            history = self._load_history(connection, document_id)
            if not history.redo:
                return self._history_status(history)
            entry = history.redo.pop()
            history.undo.append(
                {"label": entry.get("label", "undo"), "text": document.content_yaml}
            )
            history.undo = history.undo[-self.MAX_HISTORY :]
            self._update_document_content(connection, document_id, entry["text"])
            self._save_history(connection, history)
            return self._history_status(history)

    def create_pin(self, document_id: int, label: str) -> CvPin:
        """Create a named snapshot of a document and its history stacks."""
        clean_label = label.strip()
        if not clean_label:
            raise ValueError("pin label is required")
        with self.database.connect() as connection:
            document = self._require_document(connection, document_id)
            history = self._load_history(connection, document_id)
            return self._insert_pin(
                connection,
                document_id=document_id,
                label=clean_label,
                content_yaml=document.content_yaml,
                undo=history.undo,
                redo=history.redo,
            )

    def list_pins(self, document_id: int) -> list[CvPin]:
        """Return pins for a document, newest first."""
        with self.database.connect() as connection:
            self._require_document(connection, document_id)
            rows = connection.execute(
                """
                SELECT * FROM cv_pins
                WHERE document_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (document_id,),
            ).fetchall()
            return [self._row_to_pin(row) for row in rows]

    def restore_pin(self, pin_id: int) -> CvPin:
        """Restore pinned content and history, after pinning current state."""
        with self.database.connect() as connection:
            pin = self._require_pin(connection, pin_id)
            document = self._require_document(connection, pin.document_id)
            history = self._load_history(connection, pin.document_id)
            self._insert_pin(
                connection,
                document_id=pin.document_id,
                label=f"before-restore:{pin_id}",
                content_yaml=document.content_yaml,
                undo=history.undo,
                redo=history.redo,
            )
            self._update_document_content(connection, pin.document_id, pin.content_yaml)
            self._save_history(
                connection,
                CvHistoryState(
                    document_id=pin.document_id,
                    undo=pin.undo[-self.MAX_HISTORY :],
                    redo=pin.redo[-self.MAX_HISTORY :],
                ),
            )
            return pin

    def delete_pin(self, pin_id: int) -> None:
        """Delete a saved pin."""
        with self.database.connect() as connection:
            cursor = connection.execute("DELETE FROM cv_pins WHERE id = ?", (pin_id,))
            if cursor.rowcount == 0:
                raise KeyError(f"CV pin {pin_id} was not found")

    def _insert_pin(
        self,
        connection: sqlite3.Connection,
        document_id: int,
        label: str,
        content_yaml: str,
        undo: list[dict[str, str]],
        redo: list[dict[str, str]],
    ) -> CvPin:
        """Insert and return a pin snapshot."""
        cursor = connection.execute(
            """
            INSERT INTO cv_pins
                (
                    document_id,
                    label,
                    content_yaml,
                    undo_json,
                    redo_json,
                    created_at
                )
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (
                document_id,
                label,
                content_yaml,
                json.dumps(undo[-self.MAX_HISTORY :]),
                json.dumps(redo[-self.MAX_HISTORY :]),
            ),
        )
        return self._require_pin(connection, int(cursor.lastrowid))

    def _load_history(
        self, connection: sqlite3.Connection, document_id: int
    ) -> CvHistoryState:
        """Load history for a document, returning empty stacks when absent."""
        row = connection.execute(
            """
            SELECT * FROM cv_history
            WHERE document_id = ?
            """,
            (document_id,),
        ).fetchone()
        if row is None:
            return CvHistoryState(document_id=document_id, undo=[], redo=[])
        undo, redo = self._parse_stacks(
            row["undo_json"],
            row["redo_json"],
            document_id=document_id,
        )
        return CvHistoryState(
            document_id=document_id,
            undo=undo,
            redo=redo,
            updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        )

    def _save_history(
        self, connection: sqlite3.Connection, history: CvHistoryState
    ) -> None:
        """Persist a document's history stacks."""
        connection.execute(
            """
            INSERT INTO cv_history
                (document_id, undo_json, redo_json, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(document_id) DO UPDATE SET
                undo_json = excluded.undo_json,
                redo_json = excluded.redo_json,
                updated_at = datetime('now')
            """,
            (
                history.document_id,
                json.dumps(history.undo[-self.MAX_HISTORY :]),
                json.dumps(history.redo[-self.MAX_HISTORY :]),
            ),
        )

    def _bootstrap_history(
        self,
        repo_root: Path,
        master: CvDocument,
        history_path: Optional[Path],
    ) -> bool:
        """Import legacy history stacks for the master document when available."""
        if master.id is None:
            raise ValueError("master document id is required")
        path = history_path or repo_root / "data" / "edit-history.json"
        try:
            if not path.exists():
                return False
        except OSError as error:
            LOGGER.warning("Unable to inspect CV edit history at %s: %s", path, error)
            return False
        with self.database.connect() as connection:
            history = self._load_history(connection, master.id)
            if history.undo or history.redo:
                return False
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                LOGGER.warning(
                    "Unable to import CV edit history from %s: %s", path, error
                )
                return False
            if not isinstance(payload, dict):
                return False
            imported = CvHistoryState(
                document_id=master.id,
                undo=self._history_stack_from_payload(payload.get("undo")),
                redo=self._history_stack_from_payload(payload.get("redo")),
            )
            if not imported.undo and not imported.redo:
                return False
            self._save_history(connection, imported)
            return True

    @staticmethod
    def _history_stack_from_payload(raw_stack: object) -> list[dict[str, str]]:
        """Convert a legacy history stack payload into stored stack entries."""
        if not isinstance(raw_stack, list):
            return []
        stack: list[dict[str, str]] = []
        for entry in raw_stack:
            if isinstance(entry, dict) and "text" in entry:
                stack.append(
                    {
                        "label": str(entry.get("label", "")),
                        "text": str(entry["text"]),
                    }
                )
        return stack

    def _update_document_content(
        self, connection: sqlite3.Connection, document_id: int, content_yaml: str
    ) -> None:
        """Update document content by id."""
        cursor = connection.execute(
            """
            UPDATE cv_documents
            SET content_yaml = ?, updated_at = datetime('now')
            WHERE id = ?
            """,
            (content_yaml, document_id),
        )
        if cursor.rowcount == 0:
            raise KeyError(f"CV document {document_id} was not found")

    @staticmethod
    def _history_status(history: CvHistoryState) -> dict[str, Any]:
        """Return public history status fields for a history state."""
        undo_count = len(history.undo)
        redo_count = len(history.redo)
        return {
            "can_undo": undo_count > 0,
            "can_redo": redo_count > 0,
            "undo_count": undo_count,
            "redo_count": redo_count,
        }

    @staticmethod
    def _parse_stack_payload(
        raw_value: object, document_id: int
    ) -> Optional[list[dict[str, str]]]:
        """Parse a history stack JSON payload into label/text dictionaries."""
        try:
            parsed = json.loads(str(raw_value or "[]"))
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            return None
        if not isinstance(parsed, list):
            return None
        stack: list[dict[str, str]] = []
        for item in parsed:
            if isinstance(item, dict) and "text" in item:
                stack.append(
                    {
                        "label": str(item.get("label", "")),
                        "text": str(item["text"]),
                    }
                )
        return stack

    @staticmethod
    def _parse_stacks(
        undo_json: object, redo_json: object, document_id: int
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """Parse undo/redo stacks, resetting both if either payload is corrupt."""
        undo = DocumentStore._parse_stack_payload(undo_json, document_id)
        redo = DocumentStore._parse_stack_payload(redo_json, document_id)
        if undo is None or redo is None:
            LOGGER.warning(
                "Corrupt CV history for document %s; resetting stacks", document_id
            )
            return [], []
        return undo, redo

    @staticmethod
    def _row_to_document(row: sqlite3.Row) -> CvDocument:
        """Convert a cv_documents row into a CvDocument model."""
        return CvDocument(
            id=int(row["id"]),
            kind=str(row["kind"]),
            name=str(row["name"]) if row["name"] is not None else None,
            content_yaml=str(row["content_yaml"]),
            updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        )

    @staticmethod
    def _row_to_pin(row: sqlite3.Row) -> CvPin:
        """Convert a cv_pins row into a CvPin model."""
        document_id = int(row["document_id"])
        undo, redo = DocumentStore._parse_stacks(
            row["undo_json"],
            row["redo_json"],
            document_id=document_id,
        )
        return CvPin(
            id=int(row["id"]),
            document_id=document_id,
            label=str(row["label"]),
            content_yaml=str(row["content_yaml"]),
            undo=undo,
            redo=redo,
            created_at=str(row["created_at"]) if row["created_at"] else None,
        )

    def _require_document(
        self, connection: sqlite3.Connection, document_id: Optional[int]
    ) -> CvDocument:
        """Return a document by id or raise KeyError."""
        if document_id is None:
            raise ValueError("document id is required")
        row = connection.execute(
            """
            SELECT * FROM cv_documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"CV document {document_id} was not found")
        return self._row_to_document(row)

    def _require_pin(self, connection: sqlite3.Connection, pin_id: Optional[int]) -> CvPin:
        """Return a pin by id or raise KeyError."""
        if pin_id is None:
            raise ValueError("pin id is required")
        row = connection.execute(
            """
            SELECT * FROM cv_pins
            WHERE id = ?
            """,
            (pin_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"CV pin {pin_id} was not found")
        return self._row_to_pin(row)
