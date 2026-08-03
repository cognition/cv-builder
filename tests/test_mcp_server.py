"""Tests for the MCP server tool functions in ``cvbuilder.mcp_server``."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from ruamel.yaml import YAML

from cvbuilder import mcp_server

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


@pytest.fixture(autouse=True)
def _snippets_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every tool call at an isolated, empty database."""
    db_path = tmp_path / "snippets.db"
    monkeypatch.setenv("SNIPPETS_DB", str(db_path))
    return db_path


class TestSnippetTools:
    """CRUD tools for individual snippets and their variants."""

    def test_create_list_get_snippet(self) -> None:
        """A created snippet should be listed and fetchable by id."""
        created = mcp_server.create_snippet(
            category="skill",
            content="- Python\n- SQL",
            detail_level="standard",
            role="technical",
            tags=["python", "sql"],
        )
        assert created["id"] is not None
        assert created["variants"][0]["content"] == "- Python\n- SQL"

        listed = mcp_server.list_snippets(category="skill")
        assert [s["id"] for s in listed] == [created["id"]]

        fetched = mcp_server.get_snippet(created["id"])
        assert fetched["tags"] == ["python", "sql"]

    def test_get_snippet_missing_raises(self) -> None:
        """Fetching a nonexistent snippet id should raise ValueError."""
        with pytest.raises(ValueError):
            mcp_server.get_snippet(999)

    def test_update_snippet_partial_fields(self) -> None:
        """Omitted fields on update should keep their current value."""
        created = mcp_server.create_snippet(
            category="experience", content="Did things.", company="Acme"
        )
        updated = mcp_server.update_snippet(created["id"], heading="New Heading")
        assert updated["company"] == "Acme"
        assert updated["heading"] == "New Heading"

    def test_add_and_delete_snippet_variant(self) -> None:
        """A second detail level should attach, then be removable."""
        created = mcp_server.create_snippet(category="bio", content="Short bio.")
        with_detailed = mcp_server.add_snippet_variant(
            created["id"], "detailed", "Much longer bio."
        )
        levels = {v["detail_level"] for v in with_detailed["variants"]}
        assert levels == {"standard", "detailed"}

        assert mcp_server.delete_snippet_variant(created["id"], "detailed") is True
        remaining = mcp_server.get_snippet(created["id"])
        assert {v["detail_level"] for v in remaining["variants"]} == {"standard"}

    def test_delete_snippet(self) -> None:
        """Deleting a snippet should remove it from listings."""
        created = mcp_server.create_snippet(category="bio", content="Bio text.")
        assert mcp_server.delete_snippet(created["id"]) is True
        assert mcp_server.list_snippets() == []


class TestMatchJobPosting:
    """Keyword matching against a posting."""

    def test_match_ranks_tagged_snippet_first(self) -> None:
        """A snippet tagged with a posting keyword should rank above one without."""
        relevant = mcp_server.create_snippet(
            category="skill", content="Kubernetes at scale.", tags=["kubernetes"]
        )
        mcp_server.create_snippet(category="skill", content="Unrelated content.")

        results = mcp_server.match_job_posting(
            "We need strong Kubernetes experience.", limit=5
        )
        assert results
        assert results[0]["snippet_id"] == relevant["id"]


class TestDraftTools:
    """Named, persisted builder selections."""

    def test_save_list_get_delete_draft(self) -> None:
        """A saved draft should round-trip through list/get/delete."""
        selections = [{"snippet_id": 1, "detail_level": "standard"}]
        saved = mcp_server.save_draft("my-draft", selections)
        assert saved["name"] == "my-draft"

        assert [d["name"] for d in mcp_server.list_drafts()] == ["my-draft"]
        assert mcp_server.get_draft("my-draft")["selections"] == selections
        assert mcp_server.delete_draft("my-draft") is True
        assert mcp_server.list_drafts() == []

    def test_get_draft_missing_raises(self) -> None:
        """Fetching a nonexistent draft should raise ValueError."""
        with pytest.raises(ValueError):
            mcp_server.get_draft("does-not-exist")


class TestReseedAndCompose:
    """Tools that touch the repository tree (importer + composer)."""

    def test_reseed_snippets(
        self, repo_fixture: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reseeding should import snippets from the fixture repo's content."""
        monkeypatch.setattr(mcp_server, "REPO_ROOT", repo_fixture)
        stats = mcp_server.reseed_snippets()
        assert stats["yaml_bio"] >= 1
        assert mcp_server.list_snippets()

    def test_compose_cv_writes_data_yaml(
        self, repo_fixture: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Composing without PDF rendering should write a valid data.yaml."""
        monkeypatch.setattr(mcp_server, "REPO_ROOT", repo_fixture)
        mcp_server.reseed_snippets()
        bio = mcp_server.list_snippets(category="bio")[0]

        result = mcp_server.compose_cv(
            name="mcp-test-variant",
            selections=[
                {
                    "snippet_id": bio["id"],
                    "detail_level": "standard",
                    "section": "bio",
                }
            ],
            render_pdf=False,
        )
        assert result["ok"] is True
        assert result["pdf"] is None

        data_path = repo_fixture / result["data_yaml"]
        assert data_path.is_file()
        yaml = YAML(typ="safe")
        with data_path.open(encoding="utf-8") as handle:
            document = yaml.load(handle)
        assert document["bio"]

        variants = mcp_server.list_variants()
        assert any(v["name"] == "mcp-test-variant" for v in variants)
