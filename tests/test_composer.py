"""Tests for ``CvComposer`` document assembly."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from ruamel.yaml import YAML

from cvbuilder.composer import CvComposer
from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.importer import SnippetImporter
from cvbuilder.models import DetailLevel

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


class TestCvComposer:
    """Verify composed data.yaml shape from selected snippets."""

    def test_compose_writes_valid_data_yaml(
        self,
        repo_fixture: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Composer should write a data.yaml with bio, skills, and experience."""
        database = SnippetDatabase(tmp_path / "compose.db")
        SnippetImporter(database=database, repo_root=repo_fixture).seed()
        composer = CvComposer(database=database, repo_root=repo_fixture)

        def _fake_export(
            document: dict[str, Any], pdf_path: Path
        ) -> None:
            """Skip Chrome and just touch the PDF path."""
            assert isinstance(document, dict)
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(b"%PDF-1.4 fake")

        monkeypatch.setattr(composer, "_export_pdf", _fake_export)

        bios = database.list_snippets(category="bio")
        skills = database.list_snippets(category="skill")
        experience = database.list_snippets(
            category="experience", detail_level=DetailLevel.STANDARD.value
        )
        selections = [
            {
                "snippet_id": bios[0].id,
                "detail_level": DetailLevel.STANDARD.value,
                "section": "bio",
            },
            {
                "snippet_id": skills[0].id,
                "detail_level": DetailLevel.STANDARD.value,
                "section": "skill",
            },
            {
                "snippet_id": experience[0].id,
                "detail_level": DetailLevel.STANDARD.value,
                "section": "experience",
            },
        ]
        result = composer.compose(
            name="test-variant",
            selections=selections,
            render_pdf=True,
            export_yaml=True,
        )
        assert result["ok"] is True
        data_path = repo_fixture / result["data_yaml"]
        assert data_path.is_file()
        yaml = YAML(typ="safe")
        with data_path.open(encoding="utf-8") as handle:
            document = yaml.load(handle)
        assert document["person"]["first_name"] == "Test"
        assert document["person"]["last_name"] == "Person"
        assert document["bio"]
        assert document["skills"]["technical"] or document["skills"]["functional"]
        assert document["experience"]
        assert (repo_fixture / result["pdf"]).is_file()

    def test_compose_stores_variant_in_database_without_yaml(
        self,
        repo_fixture: Path,
        tmp_path: Path,
    ) -> None:
        """Default compose should save the variant document without exporting YAML."""
        database = SnippetDatabase(tmp_path / "compose.db")
        SnippetImporter(database=database, repo_root=repo_fixture).seed()
        composer = CvComposer(database=database, repo_root=repo_fixture)

        bio = database.list_snippets(category="bio")[0]
        selections = [
            {
                "snippet_id": bio.id,
                "detail_level": DetailLevel.STANDARD.value,
                "section": "bio",
            }
        ]
        result = composer.compose(
            name="oncall",
            selections=selections,
            render_pdf=False,
            export_yaml=False,
        )

        assert result["ok"] is True
        assert result["pdf"] is None
        assert (
            repo_fixture / "cv" / "variants" / "oncall" / "data.yaml"
        ).exists() is False
        store = DocumentStore(database)
        variant = store.get_variant("oncall")
        assert variant is not None
        assert "person" in variant.content_yaml
        assert "First bio paragraph" in variant.content_yaml

    def test_compose_rejects_empty_name(
        self, repo_fixture: Path, snippet_db: SnippetDatabase
    ) -> None:
        """An empty variant name should raise ValueError."""
        composer = CvComposer(database=snippet_db, repo_root=repo_fixture)
        with pytest.raises(ValueError):
            composer.compose(name="!!!", selections=[{"snippet_id": 1}])
