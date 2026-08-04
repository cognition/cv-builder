"""Tests for structural editing helpers in ``cvweb``."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

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
from cvbuilder import new_item_content  # noqa: E402


class TestStructureOps:
    """Verify insert/delete/move against nested YAML sequences."""

    def test_insert_append_and_index(self) -> None:
        """Insert should append by default and honour an explicit index."""
        data: dict[str, Any] = {"bio": ["one", "two"]}
        cvweb.insert_item(data, "bio", value="three")
        assert list(data["bio"]) == ["one", "two", "three"]
        cvweb.insert_item(data, "bio", index=1, value="mid")
        assert list(data["bio"]) == ["one", "mid", "two", "three"]

    def test_delete_item(self) -> None:
        """Delete should remove the addressed list element."""
        data: dict[str, Any] = {"skills": {"technical": ["a", "b", "c"]}}
        cvweb.delete_item(data, "skills.technical[1]")
        assert list(data["skills"]["technical"]) == ["a", "c"]

    def test_move_item(self) -> None:
        """Move should reorder within bounds and reject out-of-range offsets."""
        data: dict[str, Any] = {"education": ["x", "y", "z"]}
        cvweb.move_item(data, "education[0]", 1)
        assert list(data["education"]) == ["y", "x", "z"]
        with pytest.raises(ValueError):
            cvweb.move_item(data, "education[0]", -1)

    def test_insert_experience_default(self) -> None:
        """Inserting into experience without a value should create a job shell."""
        data: dict[str, Any] = {"experience": []}
        cvweb.insert_item(data, "experience")
        assert len(data["experience"]) == 1
        job = data["experience"][0]
        assert job["company"] == new_item_content.JOB["company"]
        assert job["subsections"]
        assert job["subsections"][0]["heading"] == new_item_content.NEW_JOB_SUBSECTION_HEADING

    def test_insert_side_panel_default(self) -> None:
        """Inserting into panels should create the list and a panel shell."""
        data: dict[str, Any] = {}
        cvweb.insert_item(data, "panels")
        assert len(data["panels"]) == 1
        panel = data["panels"][0]
        assert panel["title"] == new_item_content.PANEL["title"]
        assert list(panel["items"]) == [new_item_content.GENERIC_ITEM]

    def test_replace_item(self) -> None:
        """Replace should overwrite the addressed node in place."""
        data: dict[str, Any] = {"bio": ["one", "two"]}
        cvweb.replace_item(data, "bio[1]", "swapped")
        assert list(data["bio"]) == ["one", "swapped"]

    def test_subsection_from_text_parses_blocks(self) -> None:
        """Paragraph blocks and ``- `` bullets should map back to structure."""
        sub = cvweb.subsection_from_text(
            "Heading", "Para one.\n\n- b1\n- b2"
        )
        assert sub["heading"] == "Heading"
        assert list(sub["paragraphs"]) == ["Para one."]
        assert list(sub["bullets"]) == ["b1", "b2"]

    def test_subsection_from_text_optional_parts(self) -> None:
        """Blank heading and missing bullets should be omitted."""
        sub = cvweb.subsection_from_text("  ", "Only paragraph.")
        assert "heading" not in sub
        assert "bullets" not in sub
        assert list(sub["paragraphs"]) == ["Only paragraph."]

    def test_insert_panel_item_default(self) -> None:
        """Inserting into a panel's items should default to a plain string."""
        data: dict[str, Any] = {"panels": [{"title": "Certs", "items": ["one"]}]}
        cvweb.insert_item(data, "panels[0].items")
        assert list(data["panels"][0]["items"]) == ["one", new_item_content.GENERIC_ITEM]


class TestDefaultInsertValueContent:
    """Every ``_default_insert_value`` shape should read its wording from
    ``cvbuilder.new_item_content`` rather than embedding it — these pin
    that wiring for list paths not already covered above."""

    def test_bullets_and_paragraphs_default_to_generic_item(self) -> None:
        assert (
            cvweb._default_insert_value("experience[0].subsections[0].bullets", None)
            == new_item_content.GENERIC_ITEM
        )
        assert (
            cvweb._default_insert_value(
                "experience[0].subsections[0].paragraphs", None
            )
            == new_item_content.GENERIC_ITEM
        )

    def test_skills_default_to_skill_wording(self) -> None:
        assert cvweb._default_insert_value("skills.technical", None) == new_item_content.SKILL
        assert cvweb._default_insert_value("skills.functional", None) == new_item_content.SKILL

    def test_bio_defaults_to_bio_paragraph_wording(self) -> None:
        assert (
            str(cvweb._default_insert_value("bio", None)) == new_item_content.BIO_PARAGRAPH
        )

    def test_education_defaults_to_education_entry_wording(self) -> None:
        assert (
            cvweb._default_insert_value("education", None)
            == new_item_content.EDUCATION_ENTRY
        )

    def test_subsection_defaults_to_new_subsection_wording(self) -> None:
        subsection = cvweb._default_insert_value("experience[0].subsections", None)
        assert subsection["heading"] == new_item_content.NEW_SUBSECTION_HEADING
        assert list(subsection["bullets"]) == [new_item_content.BULLET]

    def test_explicit_value_bypasses_defaults(self) -> None:
        assert cvweb._default_insert_value("bio", "explicit") == "explicit"

    def test_person_profiles_defaults_to_profile_shape(self) -> None:
        profile = cvweb._default_insert_value("person.profiles", None)
        assert profile["provider"] == new_item_content.PROFILE["provider"]
        assert profile["handle"] == new_item_content.PROFILE["handle"]
        assert profile["visible"] is True
