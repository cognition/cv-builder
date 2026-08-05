"""Tests for Content library audit and batch ops."""

from __future__ import annotations

from pathlib import Path

import pytest

from cvbuilder.database import SnippetDatabase
from cvbuilder.library_ops import LibraryOps
from cvbuilder.models import Snippet, SnippetVariant


@pytest.fixture
def database(tmp_path: Path) -> SnippetDatabase:
    """Isolated empty snippet database."""
    path = tmp_path / "snippets.db"
    db = SnippetDatabase(path)
    db.ensure_schema()
    return db


def _create(
    database: SnippetDatabase,
    *,
    category: str,
    content: str,
    detail_level: str = "standard",
    company: str | None = None,
    role: str | None = None,
    heading: str | None = None,
    tags: list[str] | None = None,
) -> int:
    """Insert one snippet with a single variant; return id."""
    snippet_id = database.create_snippet(
        Snippet(
            category=category,
            company=company,
            role=role,
            heading=heading,
            tags=tags or [],
        )
    )
    database.upsert_variant(
        SnippetVariant(
            snippet_id=snippet_id,
            detail_level=detail_level,
            content=content,
        )
    )
    return snippet_id


class TestAuditLibrary:
    """Read-only library health report."""

    def test_reports_missing_detail_levels(self, database: SnippetDatabase) -> None:
        """Snippets lacking brief/detailed appear under missing_detail_levels."""
        sid = _create(database, category="bio", content="A" * 40)
        report = LibraryOps(database).audit()
        entry = next(e for e in report["missing_detail_levels"] if e["id"] == sid)
        assert set(entry["missing"]) == {"brief", "detailed"}
        assert entry["category"] == "bio"

    def test_reports_empty_tags(self, database: SnippetDatabase) -> None:
        """Untagged snippets appear under empty_tags."""
        sid = _create(database, category="skill", content="A" * 40, tags=[])
        report = LibraryOps(database).audit()
        assert any(e["id"] == sid for e in report["empty_tags"])

    def test_reports_sparse_experience_heading(self, database: SnippetDatabase) -> None:
        """Experience without heading is flagged."""
        sid = _create(
            database,
            category="experience",
            content="A" * 40,
            company="Acme",
            role="Eng",
            heading=None,
        )
        report = LibraryOps(database).audit()
        assert any(e["id"] == sid for e in report["sparse_headings"])

    def test_reports_length_outliers(self, database: SnippetDatabase) -> None:
        """Very short variant content is flagged as too_short."""
        sid = _create(database, category="skill", content="x", tags=["t"])
        report = LibraryOps(database).audit()
        hits = [e for e in report["length_outliers"] if e["id"] == sid]
        assert hits
        assert hits[0]["reason"] == "too_short"

    def test_duplicate_candidates_same_company_role(
        self, database: SnippetDatabase
    ) -> None:
        """Two experience rows with same company+role are duplicate candidates."""
        a = _create(
            database,
            category="experience",
            content="A" * 40,
            company="Acme",
            role="Engineer",
            heading="One",
            tags=["x"],
        )
        b = _create(
            database,
            category="experience",
            content="B" * 40,
            company="Acme",
            role="Engineer",
            heading="Two",
            tags=["x"],
        )
        report = LibraryOps(database).audit()
        found = False
        for group in report["duplicate_candidates"]:
            if set(group["ids"]) == {a, b}:
                assert group["reason"] == "same_company_role"
                found = True
        assert found

    def test_counts_by_category(self, database: SnippetDatabase) -> None:
        """Report includes per-category counts."""
        _create(database, category="bio", content="A" * 40, tags=["a"])
        _create(database, category="skill", content="B" * 40, tags=["b"])
        report = LibraryOps(database).audit()
        assert report["counts_by_category"]["bio"] == 1
        assert report["counts_by_category"]["skill"] == 1


class TestUpsertSnippets:
    """Batch create/update with dry-run default."""

    def test_dry_run_does_not_persist(self, database: SnippetDatabase) -> None:
        """dry_run=True plans a create but leaves the DB empty."""
        ops = LibraryOps(database)
        result = ops.upsert_snippets(
            [
                {
                    "category": "skill",
                    "tags": ["python"],
                    "variants": {"standard": "- Python mastery " + ("x" * 20)},
                }
            ],
            dry_run=True,
        )
        assert result["dry_run"] is True
        assert result["counts"]["created"] == 1
        assert database.list_snippets() == []

    def test_apply_creates_snippet(self, database: SnippetDatabase) -> None:
        """dry_run=False persists a new snippet with variants."""
        ops = LibraryOps(database)
        result = ops.upsert_snippets(
            [
                {
                    "category": "skill",
                    "role": "technical",
                    "tags": ["python"],
                    "variants": {
                        "brief": "- Py " + ("b" * 20),
                        "standard": "- Python " + ("s" * 20),
                    },
                }
            ],
            dry_run=False,
        )
        assert result["dry_run"] is False
        assert result["counts"]["created"] == 1
        created_id = result["created"][0]["id"]
        assert created_id is not None
        fetched = database.get_snippet(created_id)
        assert fetched is not None
        assert {v.detail_level for v in fetched.variants} == {"brief", "standard"}

    def test_apply_updates_metadata_and_variant(
        self, database: SnippetDatabase
    ) -> None:
        """Update by id replaces tags and upserts a variant."""
        sid = _create(
            database,
            category="experience",
            content="A" * 40,
            company="OldCo",
            role="Dev",
            heading="Old",
            tags=["old"],
        )
        result = LibraryOps(database).upsert_snippets(
            [
                {
                    "id": sid,
                    "heading": "New heading",
                    "tags": ["new"],
                    "variants": {"detailed": "- Extra detail " + ("d" * 20)},
                }
            ],
            dry_run=False,
        )
        assert result["counts"]["updated"] == 1
        fetched = database.get_snippet(sid)
        assert fetched is not None
        assert fetched.heading == "New heading"
        assert fetched.tags == ["new"]
        assert fetched.company == "OldCo"
        assert fetched.variant_for("detailed") is not None

    def test_partial_batch_records_errors(self, database: SnippetDatabase) -> None:
        """Invalid items error; valid siblings still apply."""
        result = LibraryOps(database).upsert_snippets(
            [
                {"category": "not-a-category", "variants": {"standard": "A" * 40}},
                {
                    "category": "bio",
                    "tags": ["bio"],
                    "variants": {"standard": "B" * 40},
                },
            ],
            dry_run=False,
        )
        assert result["counts"]["errors"] == 1
        assert result["counts"]["created"] == 1
        assert result["errors"][0]["index"] == 0
        assert len(database.list_snippets()) == 1

    def test_create_requires_variant(self, database: SnippetDatabase) -> None:
        """Create without variants is an error."""
        result = LibraryOps(database).upsert_snippets(
            [{"category": "skill", "tags": ["x"]}],
            dry_run=False,
        )
        assert result["counts"]["errors"] == 1
        assert result["counts"]["created"] == 0


class TestDeleteSnippets:
    """Batch delete with dry-run default."""

    def test_dry_run_does_not_delete(self, database: SnippetDatabase) -> None:
        """dry_run=True lists the id but leaves the row."""
        sid = _create(database, category="bio", content="A" * 40, tags=["t"])
        result = LibraryOps(database).delete_snippets([sid], dry_run=True)
        assert result["dry_run"] is True
        assert result["counts"]["deleted"] == 1
        assert database.get_snippet(sid) is not None

    def test_apply_deletes(self, database: SnippetDatabase) -> None:
        """dry_run=False removes the snippet."""
        sid = _create(database, category="bio", content="A" * 40, tags=["t"])
        result = LibraryOps(database).delete_snippets([sid], dry_run=False)
        assert result["counts"]["deleted"] == 1
        assert database.get_snippet(sid) is None

    def test_unknown_id_is_error(self, database: SnippetDatabase) -> None:
        """Missing ids are recorded as errors."""
        result = LibraryOps(database).delete_snippets([999], dry_run=False)
        assert result["counts"]["errors"] == 1
        assert result["counts"]["deleted"] == 0


class TestAuditRefinePlaybook:
    """Audit → upsert missing brief → audit clears that gap."""

    def test_fill_missing_brief(self, database: SnippetDatabase) -> None:
        """After upserting brief, audit no longer lists that level as missing."""
        sid = _create(database, category="bio", content="A" * 40, tags=["bio"])
        ops = LibraryOps(database)
        before = ops.audit()
        entry = next(e for e in before["missing_detail_levels"] if e["id"] == sid)
        assert "brief" in entry["missing"]

        ops.upsert_snippets(
            [{"id": sid, "variants": {"brief": "Short bio " + ("z" * 20)}}],
            dry_run=False,
        )
        after = ops.audit()
        for entry_after in after["missing_detail_levels"]:
            if entry_after["id"] == sid:
                assert "brief" not in entry_after["missing"]
