"""Markdown export for CV document dictionaries."""

from __future__ import annotations

from typing import Any


class MarkdownExporter:
    """Render a CV document dict to Markdown."""

    def render(self, data: dict[str, Any]) -> str:
        """Return Markdown for person, bio, skills, experience, and education."""
        lines: list[str] = [f"# {self._person_name(data)}".rstrip(), ""]
        self._append_profile(lines, data.get("bio"))
        self._append_skills(lines, data.get("skills"))
        self._append_experience(lines, data.get("experience"))
        self._append_education(lines, data.get("education"))
        return "\n".join(lines).rstrip() + "\n"

    def _person_name(self, data: dict[str, Any]) -> str:
        """Return the display name from the person block."""
        person = data.get("person")
        if not isinstance(person, dict):
            return "CV"
        parts = [
            str(person.get("first_name", "")).strip(),
            str(person.get("last_name", "")).strip(),
        ]
        name = " ".join(part for part in parts if part)
        return name or "CV"

    def _append_profile(self, lines: list[str], bio: object) -> None:
        """Append the profile section when bio content is available."""
        items = self._string_items(bio)
        if not items:
            return
        lines.extend(["## Profile", ""])
        for item in items:
            lines.extend([item, ""])

    def _append_skills(self, lines: list[str], skills: object) -> None:
        """Append technical and functional skills."""
        if not isinstance(skills, dict):
            return
        groups = [
            ("Technical", self._string_items(skills.get("technical"))),
            ("Functional", self._string_items(skills.get("functional"))),
        ]
        if not any(items for _, items in groups):
            return
        lines.extend(["## Skills", ""])
        for heading, items in groups:
            if not items:
                continue
            lines.extend([f"### {heading}", ""])
            lines.extend(f"- {item}" for item in items)
            lines.append("")

    def _append_experience(self, lines: list[str], experience: object) -> None:
        """Append work experience entries and their subsections."""
        if not isinstance(experience, list) or not experience:
            return
        lines.extend(["## Experience", ""])
        for job in experience:
            if not isinstance(job, dict):
                continue
            heading = self._job_heading(job)
            if heading:
                lines.extend([f"### {heading}", ""])
            for subsection in job.get("subsections") or []:
                if not isinstance(subsection, dict):
                    continue
                subheading = str(subsection.get("heading", "")).strip()
                if subheading:
                    lines.extend([f"#### {subheading}", ""])
                for paragraph in self._string_items(subsection.get("paragraphs")):
                    lines.extend([paragraph, ""])
                bullets = self._string_items(subsection.get("bullets"))
                if bullets:
                    lines.extend(f"- {bullet}" for bullet in bullets)
                    lines.append("")

    def _append_education(self, lines: list[str], education: object) -> None:
        """Append education entries."""
        items = self._string_items(education)
        if not items:
            return
        lines.extend(["## Education", ""])
        lines.extend(f"- {item}" for item in items)
        lines.append("")

    @staticmethod
    def _job_heading(job: dict[str, Any]) -> str:
        """Return a compact heading for an experience entry."""
        role = str(job.get("role", "")).strip()
        company = str(job.get("company", "")).strip()
        if role and company:
            return f"{role}, {company}"
        return role or company

    @staticmethod
    def _string_items(value: object) -> list[str]:
        """Return a list of non-empty strings from scalar or list-like content."""
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []
