"""Tests for Markdown export of CV documents."""

from __future__ import annotations

from cvbuilder.markdown_export import MarkdownExporter


class TestMarkdownExporter:
    """Exercise Markdown rendering for CV document dictionaries."""

    def test_includes_name_bio_and_sections(self) -> None:
        """Rendered Markdown should include core CV sections."""
        text = MarkdownExporter().render(
            {
                "person": {"first_name": "Homer", "last_name": "Simpson"},
                "bio": ["Safety first."],
                "skills": {"technical": ["Reacteurs"], "functional": []},
                "experience": [
                    {
                        "company": "Springfield Nuclear",
                        "role": "Safety Inspector",
                        "subsections": [
                            {
                                "heading": "Operations",
                                "bullets": ["Prevented a meltdown."],
                            }
                        ],
                    }
                ],
                "education": ["Nuclear physics correspondence course"],
            }
        )

        assert "# Homer Simpson" in text
        assert "## Profile" in text
        assert "Safety first." in text
        assert "## Skills" in text
        assert "- Reacteurs" in text
        assert "## Experience" in text
        assert "Springfield Nuclear" in text
        assert "## Education" in text
