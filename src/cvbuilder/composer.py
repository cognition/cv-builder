"""Compose selected snippet variants into DB-backed CV documents."""

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
from cvbuilder.document_store import DocumentStore
from cvbuilder.models import DetailLevel, SelectionItem
from cvbuilder.paths import DataPaths

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
        self.variants_dir = DataPaths(self.repo_root).variants

    def compose(
        self,
        name: str,
        selections: list[dict[str, Any]] | list[SelectionItem],
        render_pdf: bool = False,
        export_yaml: bool = False,
    ) -> dict[str, Any]:
        """Upsert a variant document in the database.

        When ``export_yaml`` is True, also write
        ``cv/variants/<name>/data.yaml``. When ``render_pdf`` is True, also
        write the variant PDF.

        Args:
            name: Variant folder name under ``cv/variants/``.
            selections: Ordered list of selection dicts or ``SelectionItem``s.
                Each item needs ``snippet_id`` and optional ``detail_level`` /
                ``section``.
            render_pdf: When True, also write a PDF beside the data.yaml.
            export_yaml: When True, also export the variant YAML file.

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
        document_yaml = self._dump_yaml(document)
        DocumentStore(self.database).upsert_variant(safe_name, document_yaml)

        out_dir = self.variants_dir / safe_name
        data_path: Optional[Path] = None
        if export_yaml:
            out_dir.mkdir(parents=True, exist_ok=True)
            data_path = out_dir / "data.yaml"
            data_path.write_text(document_yaml, encoding="utf-8")

        pdf_path: Optional[Path] = None
        if render_pdf:
            out_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = out_dir / f"{safe_name}.pdf"
            self._export_pdf(document, pdf_path)

        return {
            "ok": True,
            "name": safe_name,
            "data_yaml": (
                str(data_path.relative_to(self.repo_root)) if data_path else None
            ),
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
        """Assemble a document dict from selections without writing stores.

        Args:
            base: Starting data.yaml-shaped mapping (person fields preserved).
            selections: Ordered Tailor selections.

        Returns:
            A composed document dictionary.
        """
        items = self._normalise_selections(selections)
        return self._build_document(base, items)

    def base_document_shell(self, content_yaml: str) -> dict[str, Any]:
        """Build an empty-content shell preserving person and education.

        Args:
            content_yaml: Current working document YAML text.

        Returns:
            A mapping ready for ``build_document_from_selections``.

        Raises:
            ValueError: If the YAML is not a mapping.
        """
        data = _YAML.load(content_yaml) or {}
        if not isinstance(data, dict):
            raise ValueError("CV document YAML must be a mapping")
        return {
            "person": deepcopy(data.get("person") or {}),
            "skills": {"technical": [], "functional": []},
            "bio": [],
            "experience": [],
            "education": list(data.get("education") or []),
        }

    def dump_document_yaml(self, document: dict[str, Any]) -> str:
        """Serialise a document mapping to YAML text."""
        return self._dump_yaml(document)

    def load_document_yaml(self, content_yaml: str) -> dict[str, Any]:
        """Parse a full Working Draft YAML mapping without clearing sections.

        Args:
            content_yaml: Current working document YAML text.

        Returns:
            The parsed document mapping.

        Raises:
            ValueError: If the YAML is not a mapping.
        """
        data = _YAML.load(content_yaml) or {}
        if not isinstance(data, dict):
            raise ValueError("CV document YAML must be a mapping")
        return data

    def merge_selections_into_document(
        self,
        document: dict[str, Any],
        selections: list[dict[str, Any]] | list[SelectionItem],
    ) -> tuple[int, list[dict[str, Any]]]:
        """Append selection content into an existing document mapping.

        Existing person fields and sections are preserved. Duplicate content
        (exact stripped text match) is skipped. When a different detail level
        of the same snippet is already present, the new content is still added
        and conflict highlight payloads are returned.

        Args:
            document: Mutable data.yaml-shaped mapping to update in place.
            selections: Ordered Tailor-style selections to merge.

        Returns:
            ``(added_count, conflict_highlights)`` where highlights use marks
            ``existing`` (sibling already on the draft) and ``new`` (just added).

        Raises:
            ValueError: If a snippet id is missing.
            KeyError: If a requested detail level has no content.
        """
        items = self._normalise_selections(selections)
        added = 0
        conflicts: list[dict[str, Any]] = []
        for item in items:
            sibling_highlights = self._sibling_conflict_highlights(document, item)
            if self._merge_one_selection(document, item):
                added += 1
                conflicts.extend(sibling_highlights)
        return added, conflicts

    def remove_needles_from_document(
        self, document: dict[str, Any], needles: list[str]
    ) -> int:
        """Remove leaf values matching any needle from the document.

        Args:
            document: Mutable CV document mapping.
            needles: Exact stripped strings to remove from lists/subsections.

        Returns:
            Count of removed leaf values.
        """
        targets = {needle.strip() for needle in needles if needle and needle.strip()}
        if not targets:
            return 0
        removed = 0
        for key in ("bio", "education"):
            values = list(document.get(key) or [])
            kept = [value for value in values if str(value).strip() not in targets]
            removed += len(values) - len(kept)
            document[key] = kept
        skills = dict(document.get("skills") or {})
        for skill_key in ("technical", "functional"):
            values = list(skills.get(skill_key) or [])
            kept = [value for value in values if str(value).strip() not in targets]
            removed += len(values) - len(kept)
            skills[skill_key] = kept
        document["skills"] = skills
        experience = list(document.get("experience") or [])
        for job in experience:
            if not isinstance(job, dict):
                continue
            subsections = list(job.get("subsections") or [])
            kept_subs: list[Any] = []
            for subsection in subsections:
                if not isinstance(subsection, dict):
                    kept_subs.append(subsection)
                    continue
                cleaned, sub_removed = self._strip_needles_from_subsection(
                    subsection, targets
                )
                removed += sub_removed
                if cleaned is not None:
                    kept_subs.append(cleaned)
            job["subsections"] = kept_subs
        document["experience"] = experience
        return removed

    def _sibling_conflict_highlights(
        self, document: dict[str, Any], item: SelectionItem
    ) -> list[dict[str, Any]]:
        """Build highlight rows when another detail level is already on the draft."""
        snippet = self.database.get_snippet(item.snippet_id)
        if snippet is None:
            raise ValueError(f"snippet {item.snippet_id} not found")
        new_variant = snippet.variant_for(item.detail_level)
        if new_variant is None:
            available = [variant.detail_level for variant in snippet.variants]
            raise KeyError(
                f"snippet {item.snippet_id} has no "
                f"{item.detail_level!r} variant "
                f"(available: {available})"
            )
        new_content = new_variant.content.strip()
        if not new_content or self._document_contains_content(document, new_content):
            return []
        highlights: list[dict[str, Any]] = []
        found_sibling = False
        for variant in snippet.variants:
            if variant.detail_level == item.detail_level:
                continue
            sibling_content = variant.content.strip()
            if not sibling_content:
                continue
            if not self._document_contains_content(document, sibling_content):
                continue
            found_sibling = True
            for needle in self._needles_for_content(sibling_content):
                highlights.append(
                    {
                        "mark": "existing",
                        "needle": needle,
                        "snippet_id": item.snippet_id,
                        "detail_level": variant.detail_level,
                    }
                )
        if not found_sibling:
            return []
        for needle in self._needles_for_content(new_content):
            highlights.append(
                {
                    "mark": "new",
                    "needle": needle,
                    "snippet_id": item.snippet_id,
                    "detail_level": item.detail_level,
                }
            )
        return highlights

    def _document_contains_content(
        self, document: dict[str, Any], content: str
    ) -> bool:
        """True when any needle from ``content`` already appears in the document."""
        content = content.strip()
        if not content:
            return False
        if self._text_in_list(content, list(document.get("bio") or [])):
            return True
        skills = document.get("skills") or {}
        if self._text_in_list(content, list(skills.get("technical") or [])):
            return True
        if self._text_in_list(content, list(skills.get("functional") or [])):
            return True
        if self._text_in_list(content, list(document.get("education") or [])):
            return True
        for needle in self._needles_for_content(content):
            if self._document_contains_needle(document, needle):
                return True
        bullets, paragraphs = self._split_content_blocks(content)
        probe = {
            "heading": "",
            "paragraphs": paragraphs,
            "bullets": bullets,
        }
        marker = self._subsection_marker(probe)
        for job in document.get("experience") or []:
            if not isinstance(job, dict):
                continue
            for subsection in job.get("subsections") or []:
                if (
                    isinstance(subsection, dict)
                    and self._subsection_marker(subsection) == marker
                ):
                    return True
        return False

    def _document_contains_needle(
        self, document: dict[str, Any], needle: str
    ) -> bool:
        """True when ``needle`` matches a bio/skill/education/experience leaf."""
        needle = needle.strip()
        if not needle:
            return False
        for key in ("bio", "education"):
            if self._text_in_list(needle, list(document.get(key) or [])):
                return True
        skills = document.get("skills") or {}
        for skill_key in ("technical", "functional"):
            if self._text_in_list(needle, list(skills.get(skill_key) or [])):
                return True
        for job in document.get("experience") or []:
            if not isinstance(job, dict):
                continue
            for subsection in job.get("subsections") or []:
                if not isinstance(subsection, dict):
                    continue
                heading = str(subsection.get("heading") or "").strip()
                if heading and heading == needle:
                    return True
                for value in list(subsection.get("paragraphs") or []):
                    if str(value).strip() == needle:
                        return True
                for value in list(subsection.get("bullets") or []):
                    if str(value).strip() == needle:
                        return True
        return False

    @staticmethod
    def _needles_for_content(content: str) -> list[str]:
        """Return distinctive leaf strings used for conflict highlighting."""
        content = content.strip()
        if not content:
            return []
        bullets, paragraphs = CvComposer._split_content_blocks(content)
        needles = [block.strip() for block in paragraphs if block.strip()]
        needles.extend(bullet.strip() for bullet in bullets if bullet.strip())
        if needles:
            return needles
        return [content]

    @staticmethod
    def _strip_needles_from_subsection(
        subsection: dict[str, Any], targets: set[str]
    ) -> tuple[Optional[dict[str, Any]], int]:
        """Remove matching leaves from a subsection; drop it when empty."""
        removed = 0
        cleaned = dict(subsection)
        paragraphs = [
            value
            for value in list(cleaned.get("paragraphs") or [])
            if str(value).strip() not in targets
        ]
        removed += len(list(cleaned.get("paragraphs") or [])) - len(paragraphs)
        bullets = [
            value
            for value in list(cleaned.get("bullets") or [])
            if str(value).strip() not in targets
        ]
        removed += len(list(cleaned.get("bullets") or [])) - len(bullets)
        heading = str(cleaned.get("heading") or "").strip()
        if heading and heading in targets:
            cleaned.pop("heading", None)
            removed += 1
        if paragraphs:
            cleaned["paragraphs"] = paragraphs
        else:
            cleaned.pop("paragraphs", None)
        if bullets:
            cleaned["bullets"] = bullets
        else:
            cleaned.pop("bullets", None)
        if not cleaned.get("heading") and not cleaned.get("paragraphs") and not cleaned.get(
            "bullets"
        ):
            return None, removed
        return cleaned, removed

    def _merge_one_selection(
        self, document: dict[str, Any], item: SelectionItem
    ) -> bool:
        """Merge one selection into ``document``. Return True if content added."""
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
        if not content:
            return False

        if section == "bio":
            bio = list(document.get("bio") or [])
            if self._text_in_list(content, bio):
                return False
            bio.append(FoldedScalarString(content))
            document["bio"] = bio
            return True

        if section == "skill":
            skills = dict(document.get("skills") or {})
            technical = list(skills.get("technical") or [])
            functional = list(skills.get("functional") or [])
            skill_kind = (snippet.role or "technical").lower()
            target = functional if "functional" in skill_kind else technical
            if self._text_in_list(content, target):
                return False
            target.append(content)
            if "functional" in skill_kind:
                skills["functional"] = target
            else:
                skills["technical"] = target
            document["skills"] = skills
            return True

        if section in {"experience", "requirement"}:
            return self._merge_experience_entry(document, snippet, content)

        if section in {"part", "education"}:
            education = list(document.get("education") or [])
            if self._text_in_list(content, education):
                return False
            education.append(content)
            document["education"] = education
            return True

        return self._merge_experience_entry(
            document,
            snippet,
            content,
            company_override="General",
            heading_override=snippet.heading or section,
        )

    def _merge_experience_entry(
        self,
        document: dict[str, Any],
        snippet: Any,
        content: str,
        *,
        company_override: Optional[str] = None,
        heading_override: Optional[str] = None,
    ) -> bool:
        """Append an experience subsection under a company job block."""
        company = company_override or snippet.company or "General"
        experience = list(document.get("experience") or [])
        job: Optional[dict[str, Any]] = None
        for entry in experience:
            if isinstance(entry, dict) and entry.get("company") == company:
                job = entry
                break
        if job is None:
            job = {
                "company": company,
                "role": snippet.role or "",
                "subsections": [],
            }
            experience.append(job)
        elif snippet.role and not job.get("role"):
            job["role"] = snippet.role

        bullets, paragraphs = self._split_content_blocks(content)
        subsection: dict[str, Any] = {}
        heading = heading_override if heading_override is not None else snippet.heading
        if heading:
            subsection["heading"] = heading
        if paragraphs:
            subsection["paragraphs"] = [FoldedScalarString(p) for p in paragraphs]
        if bullets:
            subsection["bullets"] = bullets
        if not subsection:
            return False

        existing = list(job.get("subsections") or [])
        marker = self._subsection_marker(subsection)
        for current in existing:
            if isinstance(current, dict) and self._subsection_marker(current) == marker:
                return False
        existing.append(subsection)
        job["subsections"] = existing
        document["experience"] = experience
        return True

    @staticmethod
    def _text_in_list(content: str, values: list[Any]) -> bool:
        """True when ``content`` already appears (stripped) in ``values``."""
        needle = content.strip()
        for value in values:
            if str(value).strip() == needle:
                return True
        return False

    @staticmethod
    def _subsection_marker(subsection: dict[str, Any]) -> str:
        """Build a stable string marker for experience subsection dedupe."""
        heading = str(subsection.get("heading") or "")
        paragraphs = subsection.get("paragraphs") or []
        bullets = subsection.get("bullets") or []
        para_text = "\n".join(str(item).strip() for item in paragraphs)
        bullet_text = "\n".join(str(item).strip() for item in bullets)
        return f"{heading}|{para_text}|{bullet_text}"

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
        """Load the base person/header fields from the DB-backed master CV."""
        store = DocumentStore(self.database)
        store.bootstrap_from_filesystem(self.repo_root)
        master = store.get_master()
        if master is None:
            raise FileNotFoundError("Master CV document is not available")
        data = _YAML.load(master.content_yaml) or {}
        if not isinstance(data, dict):
            raise ValueError("Master CV YAML must be a mapping")
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
    def _dump_yaml(document: dict[str, Any]) -> str:
        """Serialise a YAML document to text."""
        buffer = StringIO()
        _YAML.dump(document, buffer)
        return buffer.getvalue()

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
