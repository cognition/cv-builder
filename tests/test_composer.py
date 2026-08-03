"""Tests for ``CvComposer`` document assembly."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from ruamel.yaml import YAML

from cvbuilder.composer import CvComposer
from cvbuilder.database import SnippetDatabase
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
        result = composer.compose(name="test-variant", selections=selections)
        assert result["ok"] is True
        data_path = repo_fixture / result["data_yaml"]
        assert data_path.is_file()
        yaml = YAML(typ="safe")
        with data_path.open(encoding="utf-8") as handle:
            document = yaml.load(handle)
        assert document["person"]["name"] == "Test Person"
        assert document["bio"]
        assert document["skills"]["technical"] or document["skills"]["functional"]
        assert document["experience"]
        assert (repo_fixture / result["pdf"]).is_file()

    def test_compose_rejects_empty_name(
        self, repo_fixture: Path, snippet_db: SnippetDatabase
    ) -> None:
        """An empty variant name should raise ValueError."""
        composer = CvComposer(database=snippet_db, repo_root=repo_fixture)
        with pytest.raises(ValueError):
            composer.compose(name="!!!", selections=[{"snippet_id": 1}])
