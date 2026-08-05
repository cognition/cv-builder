"""Compose selected snippet variants into a CV data.yaml and PDF."""

from __future__ import annotations

import re
import sys
from copy import deepcopy
from io import StringIO
from pathlib import Path
from typing import Any, Optional

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import FoldedScalarString

from cvbuilder.database import SnippetDatabase
from cvbuilder.models import DetailLevel, SelectionItem

_YAML = YAML()
_YAML.preserve_quotes = True
_YAML.width = 1_000_000
_YAML.indent(mapping=2, sequence=4, offset=2)

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


class CvComposer:
    """Build a named CV variant from ordered snippet selections."""

    def __init__(
        self,
        database: SnippetDatabase,
        repo_root: Path,
    ) -> None:
        """Initialise the composer.

        Args:
            database: Snippet database to read variants from.
            repo_root: Repository root (for base data.yaml and output paths).
        """
        self.database = database
        self.repo_root = Path(repo_root)
        self.base_data_path = self.repo_root / "cv" / "web" / "data.yaml"
        self.variants_dir = self.repo_root / "cv" / "variants"

    def compose(
        self,
        name: str,
        selections: list[dict[str, Any]] | list[SelectionItem],
        render_pdf: bool = True,
    ) -> dict[str, Any]:
        """Compose a CV variant from selected snippets.

        Args:
            name: Variant folder name under ``cv/variants/``.
            selections: Ordered list of selection dicts or ``SelectionItem``s.
                Each item needs ``snippet_id`` and optional ``detail_level`` /
                ``section``.
            render_pdf: When True, also write a PDF beside the data.yaml.

        Returns:
            Paths and summary for the composed variant.

        Raises:
            ValueError: If the name is empty/unsafe or a snippet is missing.
            KeyError: If a requested detail level has no content.
        """
        safe_name = self._safe_name(name)
        if not safe_name:
            raise ValueError("variant name is empty or invalid")

        items = self._normalise_selections(selections)
        base = self._load_base_data()
        document = self._build_document(base, items)

        out_dir = self.variants_dir / safe_name
        out_dir.mkdir(parents=True, exist_ok=True)
        data_path = out_dir / "data.yaml"
        self._write_yaml(data_path, document)

        pdf_path: Optional[Path] = None
        if render_pdf:
            pdf_path = out_dir / f"{safe_name}.pdf"
            self._export_pdf(document, pdf_path)

        return {
            "ok": True,
            "name": safe_name,
            "data_yaml": str(data_path.relative_to(self.repo_root)),
            "pdf": (
                str(pdf_path.relative_to(self.repo_root)) if pdf_path else None
            ),
            "selection_count": len(items),
        }

    def build_document_from_selections(
        self,
        base: dict[str, Any],
        selections: list[dict[str, Any]] | list[SelectionItem],
    ) -> dict[str, Any]:
        """Assemble a document dict from selections without writing files.

        Args:
            base: Starting data.yaml-shaped mapping (person fields preserved).
            selections: Ordered Tailor selections.

        Returns:
            A composed document dictionary.
        """
        items = self._normalise_selections(selections)
        return self._build_document(base, items)

    @staticmethod
    def dumps_yaml(document: dict[str, Any]) -> str:
        """Serialise a document mapping to YAML text."""
        buf = StringIO()
        _YAML.dump(document, buf)
        return buf.getvalue()

    @staticmethod
    def loads_yaml(text: str) -> dict[str, Any]:
        """Parse a YAML document mapping from text.

        Raises:
            ValueError: If the payload is not a mapping.
        """
        data = _YAML.load(StringIO(text)) or {}
        if not isinstance(data, dict):
            raise ValueError("CV document YAML must be a mapping")
        return data

    def _build_document(
        self, base: dict[str, Any], items: list[SelectionItem]
    ) -> dict[str, Any]:
        """Assemble a data.yaml-shaped document from selections."""
        document = deepcopy(base)
        bio: list[Any] = []
        technical: list[str] = []
        functional: list[str] = []
        education: list[str] = []
        # company -> job dict being built
        jobs: dict[str, dict[str, Any]] = {}
        job_order: list[str] = []

        for item in items:
            snippet = self.database.get_snippet(item.snippet_id)
            if snippet is None:
                raise ValueError(f"snippet {item.snippet_id} not found")
            variant = snippet.variant_for(item.detail_level)
            if variant is None:
                available = [v.detail_level for v in snippet.variants]
                raise KeyError(
                    f"snippet {item.snippet_id} has no "
                    f"{item.detail_level!r} variant "
                    f"(available: {available})"
                )
            section = item.section or snippet.category
            content = variant.content.strip()
            if section == "bio":
                bio.append(FoldedScalarString(content))
            elif section == "skill":
                skill_kind = (snippet.role or "technical").lower()
                if "functional" in skill_kind:
                    functional.append(content)
                else:
                    technical.append(content)
            elif section in {"experience", "requirement"}:
                company = snippet.company or "General"
                if company not in jobs:
                    jobs[company] = {
                        "company": company,
                        "role": snippet.role or "",
                        "subsections": [],
                    }
                    job_order.append(company)
                job = jobs[company]
                if snippet.role and not job.get("role"):
                    job["role"] = snippet.role
                bullets, paragraphs = self._split_content_blocks(content)
                subsection: dict[str, Any] = {}
                if snippet.heading:
                    subsection["heading"] = snippet.heading
                if paragraphs:
                    subsection["paragraphs"] = [
                        FoldedScalarString(p) for p in paragraphs
                    ]
                if bullets:
                    subsection["bullets"] = bullets
                if subsection:
                    job["subsections"].append(subsection)
            elif section in {"part", "education"}:
                education.append(content)
            else:
                # Unknown section: park under experience/General.
                company = "General"
                if company not in jobs:
                    jobs[company] = {
                        "company": company,
                        "role": "",
                        "subsections": [],
                    }
                    job_order.append(company)
                jobs[company]["subsections"].append(
                    {
                        "heading": snippet.heading or section,
                        "paragraphs": [FoldedScalarString(content)],
                    }
                )

        if bio:
            document["bio"] = bio
        if technical or functional:
            skills = dict(document.get("skills") or {})
            if technical:
                skills["technical"] = technical
            if functional:
                skills["functional"] = functional
            document["skills"] = skills
        if job_order:
            document["experience"] = [jobs[key] for key in job_order]
        if education:
            document["education"] = education
        return document

    def _export_pdf(self, document: dict[str, Any], pdf_path: Path) -> None:
        """Render ``document`` to PDF via the shared cvweb helper."""
        scripts_dir = str(self.repo_root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import cvweb  # pylint: disable=import-outside-toplevel

        cvweb.export_pdf(pdf_path, data=document)

    def _load_base_data(self) -> dict[str, Any]:
        """Load the base person/header fields from the web CV data.yaml."""
        if not self.base_data_path.is_file():
            raise FileNotFoundError(
                f"base data.yaml not found: {self.base_data_path}"
            )
        with self.base_data_path.open(encoding="utf-8") as handle:
            data = _YAML.load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError("base data.yaml must be a mapping")
        # Keep person + empty shells; content sections are rebuilt.
        return {
            "person": deepcopy(data.get("person") or {}),
            "skills": {"technical": [], "functional": []},
            "bio": [],
            "experience": [],
            "education": list(data.get("education") or []),
        }

    @staticmethod
    def _write_yaml(path: Path, document: dict[str, Any]) -> None:
        """Write a YAML document to disk."""
        with path.open("w", encoding="utf-8") as handle:
            _YAML.dump(document, handle)

    @staticmethod
    def _normalise_selections(
        selections: list[dict[str, Any]] | list[SelectionItem],
    ) -> list[SelectionItem]:
        """Convert raw payload selections into ``SelectionItem`` models."""
        items: list[SelectionItem] = []
        for raw in selections:
            if isinstance(raw, SelectionItem):
                items.append(raw)
                continue
            if not isinstance(raw, dict):
                raise ValueError("each selection must be an object")
            snippet_id = raw.get("snippet_id")
            if snippet_id is None:
                raise ValueError("selection missing snippet_id")
            items.append(
                SelectionItem(
                    snippet_id=int(snippet_id),
                    detail_level=str(
                        raw.get("detail_level", DetailLevel.STANDARD.value)
                    ),
                    section=raw.get("section"),
                )
            )
        return items

    @staticmethod
    def _safe_name(name: str) -> str:
        """Sanitise a variant name for use as a directory name."""
        cleaned = _SAFE_NAME_RE.sub("-", name.strip()).strip("-._")
        return cleaned[:80]

    @staticmethod
    def _split_content_blocks(content: str) -> tuple[list[str], list[str]]:
        """Split stored content into bullet lines and paragraph blocks."""
        bullets: list[str] = []
        paragraphs: list[str] = []
        for block in re.split(r"\n\s*\n", content.strip()):
            lines = [line.rstrip() for line in block.splitlines() if line.strip()]
            if not lines:
                continue
            if all(line.lstrip().startswith(("- ", "* ")) for line in lines):
                for line in lines:
                    bullets.append(line.lstrip()[2:].strip())
            elif len(lines) > 1 and all(
                line.lstrip().startswith(("- ", "* ")) for line in lines[1:]
            ):
                # Heading-ish first line kept as paragraph; rest as bullets.
                paragraphs.append(lines[0])
                for line in lines[1:]:
                    bullets.append(line.lstrip()[2:].strip())
            else:
                paragraphs.append("\n".join(lines))
        return bullets, paragraphs
