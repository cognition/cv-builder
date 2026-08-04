"""Unit tests for mapping ParsedResume into master data.yaml documents."""

from __future__ import annotations

from typing import Any

from cvbuilder.resume_extractor import ParsedExperience, ParsedResume
from cvbuilder.resume_to_master import apply_resume_to_master


def _base_doc() -> dict[str, Any]:
    return {
        "person": {"first_name": "Jordan", "last_name": "Rivers"},
        "panels": [{"title": "Keep me"}],
        "bio": ["Old bio"],
        "experience": [{"company": "Example Company", "role": "Example"}],
        "skills": {"technical": ["Old"], "functional": ["Keep?"]},
        "education": ["Old Uni"],
        "extra_key": "untouched",
    }


class TestApplyResumeToMaster:
    """Mapper behaviour for master-CV import."""

    def test_preserves_person_panels_and_unknown_keys(self) -> None:
        resume = ParsedResume(profile=["New bio"])
        result = apply_resume_to_master(
            _base_doc(), resume, {"profile", "experience", "skills", "education"}
        )
        assert result["person"] == {"first_name": "Jordan", "last_name": "Rivers"}
        assert result["panels"] == [{"title": "Keep me"}]
        assert result["extra_key"] == "untouched"

    def test_maps_all_enabled_sections(self) -> None:
        resume = ParsedResume(
            profile=["Leader in platforms."],
            experience=[
                ParsedExperience(
                    heading="Staff @ Acme",
                    role="Staff",
                    company="Acme",
                    bullets=["Shipped Kubernetes"],
                )
            ],
            skills=["Kubernetes", "Python"],
            education=["BSc CS"],
        )
        result = apply_resume_to_master(
            _base_doc(), resume, {"profile", "experience", "skills", "education"}
        )
        assert result["bio"] == ["Leader in platforms."]
        assert result["experience"] == [
            {
                "company": "Acme",
                "role": "Staff",
                "dates": "",
                "location": "",
                "subsections": [
                    {"heading": "Highlights", "bullets": ["Shipped Kubernetes"]}
                ],
            }
        ]
        assert result["skills"] == {
            "technical": ["Kubernetes", "Python"],
            "functional": [],
        }
        assert result["education"] == ["BSc CS"]

    def test_disabled_section_left_unchanged(self) -> None:
        resume = ParsedResume(skills=["New"])
        result = apply_resume_to_master(_base_doc(), resume, {"skills"})
        assert result["bio"] == ["Old bio"]
        assert result["experience"][0]["company"] == "Example Company"
        assert result["education"] == ["Old Uni"]
        assert result["skills"]["technical"] == ["New"]

    def test_empty_enabled_section_clears_field(self) -> None:
        resume = ParsedResume()
        result = apply_resume_to_master(_base_doc(), resume, {"experience"})
        assert result["experience"] == []
        assert result["bio"] == ["Old bio"]

    def test_experience_without_bullets_uses_heading_bullet(self) -> None:
        resume = ParsedResume(
            experience=[
                ParsedExperience(heading="Solo Consultant", role="Consultant", company="")
            ]
        )
        result = apply_resume_to_master(_base_doc(), resume, {"experience"})
        bullets = result["experience"][0]["subsections"][0]["bullets"]
        assert bullets == ["Solo Consultant"]
