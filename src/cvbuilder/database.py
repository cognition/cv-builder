"""SQLite persistence for CV snippets and their detail-level variants."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterable, Optional

from cvbuilder.models import Draft, Snippet, SnippetVariant

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS snippets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    company TEXT,
    role TEXT,
    heading TEXT,
    tags TEXT NOT NULL DEFAULT '[]',
    source_path TEXT,
    content_hash TEXT,
    UNIQUE(source_path, content_hash)
);

CREATE TABLE IF NOT EXISTS snippet_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snippet_id INTEGER NOT NULL,
    detail_level TEXT NOT NULL,
    content TEXT NOT NULL,
    UNIQUE(snippet_id, detail_level),
    FOREIGN KEY(snippet_id) REFERENCES snippets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    selections_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_snippets_category ON snippets(category);
CREATE INDEX IF NOT EXISTS idx_snippets_company ON snippets(company);
CREATE INDEX IF NOT EXISTS idx_variants_level ON snippet_variants(detail_level);
CREATE INDEX IF NOT EXISTS idx_drafts_name ON drafts(name);
"""


class SnippetDatabase:
    """Manage the SQLite snippet store used by the custom-CV builder."""

    def __init__(self, db_path: Path) -> None:
        """Initialise the database wrapper.

        Args:
            db_path: Path to the SQLite file.
        """
        self.db_path = Path(db_path)

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield a connection with row factory and foreign keys enabled."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except (sqlite3.Error, OSError, ValueError):
            connection.rollback()
            raise
        finally:
            connection.close()

    def ensure_schema(self) -> None:
        """Create tables and indexes if they do not already exist."""
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def create_snippet(self, snippet: Snippet) -> int:
        """Insert a snippet row and return its id.

        Args:
            snippet: Snippet metadata to persist.

        Returns:
            The new snippet primary key.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO snippets
                    (category, company, role, heading, tags, source_path, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snippet.category,
                    snippet.company,
                    snippet.role,
                    snippet.heading,
                    json.dumps(list(snippet.tags)),
                    snippet.source_path,
                    snippet.content_hash,
                ),
            )
            return int(cursor.lastrowid)

    def upsert_by_source(
        self, snippet: Snippet, variant: SnippetVariant
    ) -> int:
        """Insert or refresh a snippet keyed by source_path + content_hash.

        When the same source/hash already exists, metadata is updated and the
        variant for ``variant.detail_level`` is upserted.

        Args:
            snippet: Snippet metadata.
            variant: Variant content to attach.

        Returns:
            The snippet id.
        """
        with self.connect() as connection:
            existing = connection.execute(
                """
                SELECT id FROM snippets
                WHERE source_path IS ? AND content_hash IS ?
                """,
                (snippet.source_path, snippet.content_hash),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO snippets
                        (category, company, role, heading, tags,
                         source_path, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snippet.category,
                        snippet.company,
                        snippet.role,
                        snippet.heading,
                        json.dumps(list(snippet.tags)),
                        snippet.source_path,
                        snippet.content_hash,
                    ),
                )
                snippet_id = int(cursor.lastrowid)
            else:
                snippet_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE snippets
                    SET category = ?, company = ?, role = ?, heading = ?,
                        tags = ?
                    WHERE id = ?
                    """,
                    (
                        snippet.category,
                        snippet.company,
                        snippet.role,
                        snippet.heading,
                        json.dumps(list(snippet.tags)),
                        snippet_id,
                    ),
                )
            connection.execute(
                """
                INSERT INTO snippet_variants (snippet_id, detail_level, content)
                VALUES (?, ?, ?)
                ON CONFLICT(snippet_id, detail_level) DO UPDATE SET
                    content = excluded.content
                """,
                (snippet_id, variant.detail_level, variant.content),
            )
            return snippet_id

    def update_snippet(self, snippet: Snippet) -> None:
        """Update metadata for an existing snippet.

        Args:
            snippet: Snippet with a populated ``id``.

        Raises:
            ValueError: If ``snippet.id`` is missing.
        """
        if snippet.id is None:
            raise ValueError("snippet.id is required for update")
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE snippets
                SET category = ?, company = ?, role = ?, heading = ?,
                    tags = ?, source_path = ?, content_hash = ?
                WHERE id = ?
                """,
                (
                    snippet.category,
                    snippet.company,
                    snippet.role,
                    snippet.heading,
                    json.dumps(list(snippet.tags)),
                    snippet.source_path,
                    snippet.content_hash,
                    snippet.id,
                ),
            )

    def upsert_variant(self, variant: SnippetVariant) -> int:
        """Insert or replace a detail-level variant for a snippet.

        Args:
            variant: Variant with ``snippet_id``, ``detail_level``, ``content``.

        Returns:
            The variant row id.

        Raises:
            ValueError: If ``snippet_id`` is missing.
        """
        if variant.snippet_id is None:
            raise ValueError("variant.snippet_id is required")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO snippet_variants (snippet_id, detail_level, content)
                VALUES (?, ?, ?)
                ON CONFLICT(snippet_id, detail_level) DO UPDATE SET
                    content = excluded.content
                """,
                (variant.snippet_id, variant.detail_level, variant.content),
            )
            # ON CONFLICT may not set lastrowid usefully; fetch explicitly.
            row = connection.execute(
                """
                SELECT id FROM snippet_variants
                WHERE snippet_id = ? AND detail_level = ?
                """,
                (variant.snippet_id, variant.detail_level),
            ).fetchone()
            return int(row["id"]) if row else int(cursor.lastrowid)

    def delete_snippet(self, snippet_id: int) -> bool:
        """Delete a snippet and its variants.

        Args:
            snippet_id: Primary key of the snippet.

        Returns:
            True if a row was deleted.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM snippets WHERE id = ?", (snippet_id,)
            )
            return cursor.rowcount > 0

    def delete_variant(self, snippet_id: int, detail_level: str) -> bool:
        """Delete one detail-level variant for a snippet.

        Args:
            snippet_id: Primary key of the parent snippet.
            detail_level: Level to remove (brief/standard/detailed).

        Returns:
            True if a variant row was deleted.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM snippet_variants
                WHERE snippet_id = ? AND detail_level = ?
                """,
                (snippet_id, detail_level),
            )
            return cursor.rowcount > 0

    def save_draft(self, name: str, selections: list[dict[str, Any]]) -> Draft:
        """Insert or update a named draft selection.

        Args:
            name: Unique draft name.
            selections: Ordered builder selections to persist.

        Returns:
            The saved Draft model.

        Raises:
            ValueError: If ``name`` is empty.
        """
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("draft name is required")
        payload = json.dumps(list(selections))
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO drafts (name, selections_json, created_at, updated_at)
                VALUES (?, ?, datetime('now'), datetime('now'))
                ON CONFLICT(name) DO UPDATE SET
                    selections_json = excluded.selections_json,
                    updated_at = datetime('now')
                """,
                (cleaned, payload),
            )
        draft = self.get_draft(cleaned)
        if draft is None:
            raise RuntimeError(f"failed to save draft {cleaned!r}")
        return draft

    def list_drafts(self) -> list[Draft]:
        """Return all saved drafts ordered by most recently updated."""
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM drafts
                ORDER BY updated_at DESC, name ASC
                """
            ).fetchall()
            return [self._row_to_draft(row) for row in rows]

    def get_draft(self, name: str) -> Optional[Draft]:
        """Load one draft by name.

        Args:
            name: Draft name.

        Returns:
            The draft, or None if not found.
        """
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM drafts WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_draft(row)

    def delete_draft(self, name: str) -> bool:
        """Delete a named draft.

        Args:
            name: Draft name.

        Returns:
            True if a row was deleted.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM drafts WHERE name = ?", (name,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_draft(row: sqlite3.Row) -> Draft:
        """Convert a drafts table row into a Draft model."""
        try:
            selections = list(json.loads(row["selections_json"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            selections = []
        return Draft(
            id=int(row["id"]),
            name=str(row["name"]),
            selections=[s for s in selections if isinstance(s, dict)],
            created_at=str(row["created_at"]) if row["created_at"] else None,
            updated_at=str(row["updated_at"]) if row["updated_at"] else None,
        )

    def get_snippet(self, snippet_id: int) -> Optional[Snippet]:
        """Load one snippet with all of its variants.

        Args:
            snippet_id: Primary key of the snippet.

        Returns:
            The snippet, or None if not found.
        """
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM snippets WHERE id = ?", (snippet_id,)
            ).fetchone()
            if row is None:
                return None
            variants = self._load_variants(connection, [snippet_id])
            return self._row_to_snippet(row, variants.get(snippet_id, []))

    def list_snippets(
        self,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        detail_level: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[Snippet]:
        """List snippets matching optional filters.

        Args:
            category: Exact category match.
            tag: Require this tag (case-insensitive).
            detail_level: Only include variants at this level (snippet still
                returned if it has that variant).
            search: Case-insensitive substring match against heading, company,
                role, and variant content.

        Returns:
            Matching snippets with their variants.
        """
        clauses: list[str] = []
        params: list[Any] = []
        if category:
            clauses.append("s.category = ?")
            params.append(category)
        if search:
            like = f"%{search.lower()}%"
            clauses.append(
                """
                (
                    LOWER(COALESCE(s.heading, '')) LIKE ?
                    OR LOWER(COALESCE(s.company, '')) LIKE ?
                    OR LOWER(COALESCE(s.role, '')) LIKE ?
                    OR EXISTS (
                        SELECT 1 FROM snippet_variants v
                        WHERE v.snippet_id = s.id
                          AND LOWER(v.content) LIKE ?
                    )
                )
                """
            )
            params.extend([like, like, like, like])
        if detail_level:
            clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM snippet_variants v
                    WHERE v.snippet_id = s.id AND v.detail_level = ?
                )
                """
            )
            params.append(detail_level)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT s.* FROM snippets s
            {where}
            ORDER BY s.category, s.company, s.heading, s.id
        """
        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
            snippet_ids = [int(row["id"]) for row in rows]
            variants_by_id = self._load_variants(
                connection, snippet_ids, detail_level=detail_level
            )
            results: list[Snippet] = []
            for row in rows:
                snippet = self._row_to_snippet(
                    row, variants_by_id.get(int(row["id"]), [])
                )
                if tag and tag.lower() not in {t.lower() for t in snippet.tags}:
                    continue
                results.append(snippet)
            return results

    def _load_variants(
        self,
        connection: sqlite3.Connection,
        snippet_ids: Iterable[int],
        detail_level: Optional[str] = None,
    ) -> dict[int, list[SnippetVariant]]:
        """Load variants for the given snippet ids."""
        ids = list(snippet_ids)
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        params: list[Any] = list(ids)
        level_clause = ""
        if detail_level:
            level_clause = "AND detail_level = ?"
            params.append(detail_level)
        rows = connection.execute(
            f"""
            SELECT * FROM snippet_variants
            WHERE snippet_id IN ({placeholders}) {level_clause}
            ORDER BY detail_level
            """,
            params,
        ).fetchall()
        result: dict[int, list[SnippetVariant]] = {}
        for row in rows:
            sid = int(row["snippet_id"])
            result.setdefault(sid, []).append(
                SnippetVariant(
                    id=int(row["id"]),
                    snippet_id=sid,
                    detail_level=str(row["detail_level"]),
                    content=str(row["content"]),
                )
            )
        return result

    @staticmethod
    def _row_to_snippet(
        row: sqlite3.Row, variants: list[SnippetVariant]
    ) -> Snippet:
        """Convert a snippets table row into a Snippet model."""
        tags_raw = row["tags"] or "[]"
        try:
            tags = list(json.loads(tags_raw))
        except (json.JSONDecodeError, TypeError):
            tags = []
        return Snippet(
            id=int(row["id"]),
            category=str(row["category"]),
            company=row["company"],
            role=row["role"],
            heading=row["heading"],
            tags=[str(tag) for tag in tags],
            source_path=row["source_path"],
            content_hash=row["content_hash"],
            variants=variants,
        )
