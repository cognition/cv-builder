"""SQLite persistence for CV snippets and their detail-level variants."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterable, Optional

from cvbuilder.models import (
    Draft,
    Question,
    QuestionEvidence,
    QuestionSource,
    ResumeImport,
    Snippet,
    SnippetVariant,
)

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

CREATE TABLE IF NOT EXISTS question_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'form',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    answer TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(source_id) REFERENCES question_sources(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS question_evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL,
    snippet_id INTEGER NOT NULL,
    detail_level TEXT NOT NULL DEFAULT 'standard',
    UNIQUE(question_id, snippet_id),
    FOREIGN KEY(question_id) REFERENCES questions(id) ON DELETE CASCADE,
    FOREIGN KEY(snippet_id) REFERENCES snippets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS resume_imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    snippet_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_snippets_category ON snippets(category);
CREATE INDEX IF NOT EXISTS idx_snippets_company ON snippets(company);
CREATE INDEX IF NOT EXISTS idx_variants_level ON snippet_variants(detail_level);
CREATE INDEX IF NOT EXISTS idx_drafts_name ON drafts(name);
CREATE INDEX IF NOT EXISTS idx_questions_source ON questions(source_id);
CREATE INDEX IF NOT EXISTS idx_question_evidence_question ON question_evidence(question_id);
CREATE INDEX IF NOT EXISTS idx_resume_imports_created ON resume_imports(created_at);

CREATE TABLE IF NOT EXISTS cv_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    name TEXT,
    content_yaml TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_cv_documents_variant_name
    ON cv_documents(name) WHERE kind = 'variant';

CREATE UNIQUE INDEX IF NOT EXISTS idx_cv_documents_one_master
    ON cv_documents(kind) WHERE kind = 'master';

CREATE UNIQUE INDEX IF NOT EXISTS idx_cv_documents_one_working
    ON cv_documents(kind) WHERE kind = 'working';

CREATE TABLE IF NOT EXISTS cv_history (
    document_id INTEGER PRIMARY KEY,
    undo_json TEXT NOT NULL DEFAULT '[]',
    redo_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(document_id) REFERENCES cv_documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cv_pins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    label TEXT NOT NULL,
    content_yaml TEXT NOT NULL,
    undo_json TEXT NOT NULL DEFAULT '[]',
    redo_json TEXT NOT NULL DEFAULT '[]',
    selections_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(document_id) REFERENCES cv_documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cv_pins_document ON cv_pins(document_id);
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
            self._migrate_document_schema(connection)

    @staticmethod
    def _migrate_document_schema(connection: sqlite3.Connection) -> None:
        """Apply additive migrations for CV document tables.

        Args:
            connection: Open SQLite connection with row access.
        """
        pin_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(cv_pins)")
        }
        if "selections_json" not in pin_columns:
            connection.execute(
                """
                ALTER TABLE cv_pins
                ADD COLUMN selections_json TEXT NOT NULL DEFAULT '[]'
                """
            )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_cv_documents_one_working
                ON cv_documents(kind) WHERE kind = 'working'
            """
        )

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

    # ---------- application questions ----------

    def create_question_source(self, source: QuestionSource) -> int:
        """Insert a question source and return its id.

        Args:
            source: Source metadata (title + type).

        Returns:
            The new source's primary key.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO question_sources (title, source_type, created_at)
                VALUES (?, ?, datetime('now'))
                """,
                (source.title, source.source_type),
            )
            return int(cursor.lastrowid)

    def list_question_sources(self) -> list[QuestionSource]:
        """Return all question sources, newest first."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM question_sources ORDER BY created_at DESC, id DESC"
            ).fetchall()
            return [self._row_to_source(row) for row in rows]

    def get_question_source(self, source_id: int) -> Optional[QuestionSource]:
        """Load one question source by id."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM question_sources WHERE id = ?", (source_id,)
            ).fetchone()
            return self._row_to_source(row) if row else None

    def delete_question_source(self, source_id: int) -> bool:
        """Delete a question source and its questions/evidence.

        Args:
            source_id: Primary key of the source.

        Returns:
            True if a row was deleted.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM question_sources WHERE id = ?", (source_id,)
            )
            return cursor.rowcount > 0

    def create_question(self, question: Question) -> int:
        """Insert a question under an existing source and return its id.

        Args:
            question: Question with a populated ``source_id`` and ``prompt``.

        Returns:
            The new question's primary key.

        Raises:
            ValueError: If ``source_id`` or ``prompt`` is missing.
        """
        if question.source_id is None:
            raise ValueError("question.source_id is required")
        if not question.prompt.strip():
            raise ValueError("question.prompt is required")
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO questions (source_id, prompt, answer, created_at)
                VALUES (?, ?, ?, datetime('now'))
                """,
                (question.source_id, question.prompt.strip(), question.answer or ""),
            )
            return int(cursor.lastrowid)

    def list_questions(self, source_id: Optional[int] = None) -> list[Question]:
        """List questions, optionally scoped to one source.

        Args:
            source_id: If given, only return questions under this source.

        Returns:
            Questions with source metadata and linked evidence attached.
        """
        clause = "WHERE q.source_id = ?" if source_id is not None else ""
        params: list[Any] = [source_id] if source_id is not None else []
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT q.*, src.title AS source_title, src.source_type AS source_type
                FROM questions q
                JOIN question_sources src ON src.id = q.source_id
                {clause}
                ORDER BY q.created_at ASC, q.id ASC
                """,
                params,
            ).fetchall()
            question_ids = [int(row["id"]) for row in rows]
            evidence_by_question = self._load_evidence(connection, question_ids)
            return [
                self._row_to_question(row, evidence_by_question.get(int(row["id"]), []))
                for row in rows
            ]

    def get_question(self, question_id: int) -> Optional[Question]:
        """Load one question with source metadata and evidence."""
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT q.*, src.title AS source_title, src.source_type AS source_type
                FROM questions q
                JOIN question_sources src ON src.id = q.source_id
                WHERE q.id = ?
                """,
                (question_id,),
            ).fetchone()
            if row is None:
                return None
            evidence = self._load_evidence(connection, [question_id]).get(question_id, [])
            return self._row_to_question(row, evidence)

    def update_question_answer(self, question_id: int, answer: str) -> bool:
        """Update a question's saved answer text.

        Args:
            question_id: Primary key of the question.
            answer: New answer text.

        Returns:
            True if a row was updated.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE questions SET answer = ? WHERE id = ?",
                (answer, question_id),
            )
            return cursor.rowcount > 0

    def delete_question(self, question_id: int) -> bool:
        """Delete a question and its evidence links."""
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM questions WHERE id = ?", (question_id,)
            )
            return cursor.rowcount > 0

    def add_question_evidence(
        self, question_id: int, snippet_id: int, detail_level: str = "standard"
    ) -> None:
        """Link a snippet as evidence for a question (idempotent).

        Args:
            question_id: Question to attach evidence to.
            snippet_id: Snippet being cited as evidence.
            detail_level: Which variant of the snippet is being cited.
        """
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO question_evidence (question_id, snippet_id, detail_level)
                VALUES (?, ?, ?)
                ON CONFLICT(question_id, snippet_id) DO UPDATE SET
                    detail_level = excluded.detail_level
                """,
                (question_id, snippet_id, detail_level),
            )

    def remove_question_evidence(self, question_id: int, snippet_id: int) -> bool:
        """Unlink a snippet from a question's evidence.

        Returns:
            True if a row was deleted.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM question_evidence
                WHERE question_id = ? AND snippet_id = ?
                """,
                (question_id, snippet_id),
            )
            return cursor.rowcount > 0

    def create_resume_import(self, resume_import: ResumeImport) -> int:
        """Insert a resume-import record and return its id.

        Args:
            resume_import: Metadata for the uploaded file, including how
                many snippets it produced.

        Returns:
            The new record's primary key.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO resume_imports
                    (filename, file_type, stored_path, snippet_count, created_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                """,
                (
                    resume_import.filename,
                    resume_import.file_type,
                    resume_import.stored_path,
                    resume_import.snippet_count,
                ),
            )
            return int(cursor.lastrowid)

    def list_resume_imports(self) -> list[ResumeImport]:
        """Return all resume imports, newest first."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM resume_imports ORDER BY created_at DESC, id DESC"
            ).fetchall()
            return [self._row_to_resume_import(row) for row in rows]

    def get_resume_import(self, import_id: int) -> Optional[ResumeImport]:
        """Load one resume-import record by id."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM resume_imports WHERE id = ?", (import_id,)
            ).fetchone()
            return self._row_to_resume_import(row) if row else None

    def delete_resume_import(self, import_id: int) -> bool:
        """Delete a resume-import record (the stored file is not touched).

        Returns:
            True if a row was deleted.
        """
        with self.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM resume_imports WHERE id = ?", (import_id,)
            )
            return cursor.rowcount > 0

    def existing_content_hashes(self, hashes: list[str]) -> set[str]:
        """Return which of ``hashes`` already exist on a stored snippet.

        Used to flag likely-duplicate content in the import review UI
        before it's created as a new snippet.
        """
        hashes = [value for value in hashes if value]
        if not hashes:
            return set()
        placeholders = ",".join("?" for _ in hashes)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT content_hash FROM snippets
                WHERE content_hash IN ({placeholders})
                """,
                hashes,
            ).fetchall()
            return {str(row["content_hash"]) for row in rows}

    def _load_evidence(
        self, connection: sqlite3.Connection, question_ids: Iterable[int]
    ) -> dict[int, list[QuestionEvidence]]:
        """Load evidence links (with snippet heading/company) for questions."""
        ids = list(question_ids)
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            f"""
            SELECT qe.question_id, qe.snippet_id, qe.detail_level,
                   s.heading AS heading, s.company AS company
            FROM question_evidence qe
            JOIN snippets s ON s.id = qe.snippet_id
            WHERE qe.question_id IN ({placeholders})
            ORDER BY qe.id ASC
            """,
            ids,
        ).fetchall()
        result: dict[int, list[QuestionEvidence]] = {}
        for row in rows:
            qid = int(row["question_id"])
            result.setdefault(qid, []).append(
                QuestionEvidence(
                    snippet_id=int(row["snippet_id"]),
                    detail_level=str(row["detail_level"]),
                    heading=row["heading"],
                    company=row["company"],
                )
            )
        return result

    @staticmethod
    def _row_to_source(row: sqlite3.Row) -> QuestionSource:
        """Convert a question_sources row into a QuestionSource model."""
        return QuestionSource(
            id=int(row["id"]),
            title=str(row["title"]),
            source_type=str(row["source_type"]),
            created_at=str(row["created_at"]) if row["created_at"] else None,
        )

    @staticmethod
    def _row_to_question(
        row: sqlite3.Row, evidence: list[QuestionEvidence]
    ) -> Question:
        """Convert a questions row (joined with its source) into a Question."""
        return Question(
            id=int(row["id"]),
            source_id=int(row["source_id"]),
            source_title=str(row["source_title"]),
            source_type=str(row["source_type"]),
            prompt=str(row["prompt"]),
            answer=str(row["answer"] or ""),
            created_at=str(row["created_at"]) if row["created_at"] else None,
            evidence=evidence,
        )

    @staticmethod
    def _row_to_resume_import(row: sqlite3.Row) -> ResumeImport:
        """Convert a resume_imports row into a ResumeImport model."""
        return ResumeImport(
            id=int(row["id"]),
            filename=str(row["filename"]),
            file_type=str(row["file_type"]),
            stored_path=str(row["stored_path"]),
            snippet_count=int(row["snippet_count"]),
            created_at=str(row["created_at"]) if row["created_at"] else None,
        )

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
