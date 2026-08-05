"""Seed the snippet database from structured YAML and markdown content."""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from pathlib import Path
from typing import Any, Optional

from ruamel.yaml import YAML

from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.models import DetailLevel, Snippet, SnippetVariant

LOGGER = logging.getLogger(__name__)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_YAML = YAML(typ="safe")


class SnippetImporter:
    """Import CV snippets from ``data.yaml`` and ``content/**/*.md``."""

    def __init__(
        self,
        database: SnippetDatabase,
        repo_root: Path,
        content_yaml: Optional[str] = None,
    ) -> None:
        """Initialise the importer.

        Args:
            database: Target snippet database.
            repo_root: Repository root path.
            content_yaml: Optional master YAML content to seed instead of storage.
        """
        self.database = database
        self.repo_root = Path(repo_root)
        self.content_yaml = content_yaml
        self.data_file = self.repo_root / "cv" / "web" / "data.yaml"
        self.content_dir = self.repo_root / "content"

    def seed(self) -> dict[str, int]:
        """Seed the database from all known sources.

        Returns:
            Counts of snippets upserted per source family.
        """
        self.database.ensure_schema()
        stats = {
            "yaml_bio": 0,
            "yaml_skills": 0,
            "yaml_experience": 0,
            "yaml_education": 0,
            "markdown": 0,
        }
        data = self._load_master_yaml()
        if data is not None:
            stats["yaml_bio"] = self._import_bio(data)
            stats["yaml_skills"] = self._import_skills(data)
            stats["yaml_experience"] = self._import_experience(data)
            stats["yaml_education"] = self._import_education(data)
        stats["markdown"] = self._import_markdown_tree()
        return stats

    def _load_master_yaml(self) -> Optional[dict[str, Any]]:
        """Load master YAML from explicit content, DB storage, or filesystem."""
        if self.content_yaml is not None:
            return self._load_yaml_text(self.content_yaml, "provided master YAML")

        document = DocumentStore(self.database).get_master()
        if document is not None:
            return self._load_yaml_text(document.content_yaml, "database master document")

        if self.data_file.is_file():
            return self._load_yaml(self.data_file)

        LOGGER.warning("Missing data file: %s", self.data_file)
        return None

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        """Load a YAML mapping from disk."""
        with path.open(encoding="utf-8") as handle:
            loaded = _YAML.load(handle) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Expected mapping in {path}")
        return loaded

    def _load_yaml_text(self, content_yaml: str, source: str) -> dict[str, Any]:
        """Load a YAML mapping from text content."""
        loaded = _YAML.load(content_yaml) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Expected mapping in {source}")
        return loaded

    def _import_bio(self, data: dict[str, Any]) -> int:
        """Import bio paragraphs as standard-level snippets."""
        bio = data.get("bio") or []
        count = 0
        for index, paragraph in enumerate(bio):
            text = self._as_text(paragraph)
            if not text:
                continue
            source = f"cv/web/data.yaml#bio[{index}]"
            self._upsert(
                category="bio",
                heading=f"Bio paragraph {index + 1}",
                tags=["bio", "yaml"],
                source_path=source,
                content=text,
                detail_level=DetailLevel.STANDARD.value,
            )
            count += 1
        return count

    def _import_skills(self, data: dict[str, Any]) -> int:
        """Import technical and functional skills as standard-level snippets."""
        skills = data.get("skills") or {}
        count = 0
        for kind in ("technical", "functional"):
            items = skills.get(kind) or []
            for index, skill in enumerate(items):
                text = self._as_text(skill)
                if not text:
                    continue
                source = f"cv/web/data.yaml#skills.{kind}[{index}]"
                self._upsert(
                    category="skill",
                    heading=text,
                    tags=["skill", kind, "yaml"],
                    source_path=source,
                    content=text,
                    detail_level=DetailLevel.STANDARD.value,
                    company=None,
                    role=kind,
                )
                count += 1
        return count

    def _import_experience(self, data: dict[str, Any]) -> int:
        """Import experience subsections as standard-level snippets."""
        experience = data.get("experience") or []
        count = 0
        for job_index, job in enumerate(experience):
            if not isinstance(job, dict):
                continue
            company = self._as_text(job.get("company")) or None
            role = self._as_text(job.get("role")) or None
            intro = self._as_text(job.get("intro"))
            if intro:
                source = f"cv/web/data.yaml#experience[{job_index}].intro"
                self._upsert(
                    category="experience",
                    company=company,
                    role=role,
                    heading="Intro",
                    tags=self._experience_tags(company),
                    source_path=source,
                    content=intro,
                    detail_level=DetailLevel.STANDARD.value,
                )
                count += 1
            subsections = job.get("subsections") or []
            for sub_index, sub in enumerate(subsections):
                if not isinstance(sub, dict):
                    continue
                heading = self._as_text(sub.get("heading")) or f"Subsection {sub_index + 1}"
                content = self._format_subsection(sub)
                if not content:
                    continue
                source = (
                    f"cv/web/data.yaml#experience[{job_index}]"
                    f".subsections[{sub_index}]"
                )
                self._upsert(
                    category="experience",
                    company=company,
                    role=role,
                    heading=heading,
                    tags=self._experience_tags(company, heading),
                    source_path=source,
                    content=content,
                    detail_level=DetailLevel.STANDARD.value,
                )
                count += 1
        return count

    def _import_education(self, data: dict[str, Any]) -> int:
        """Import education entries as standard-level snippets."""
        education = data.get("education") or []
        count = 0
        for index, entry in enumerate(education):
            text = self._as_text(entry)
            if not text:
                continue
            source = f"cv/web/data.yaml#education[{index}]"
            self._upsert(
                category="part",
                heading="Education",
                tags=["education", "yaml"],
                source_path=source,
                content=text,
                detail_level=DetailLevel.STANDARD.value,
            )
            count += 1
        return count

    def _import_markdown_tree(self) -> int:
        """Import heading-delimited sections from content markdown files."""
        if not self.content_dir.is_dir():
            LOGGER.warning("Missing content directory: %s", self.content_dir)
            return 0
        count = 0
        for path in sorted(self.content_dir.rglob("*.md")):
            count += self._import_markdown_file(path)
        return count

    def _import_markdown_file(self, path: Path) -> int:
        """Import one markdown file as one or more detailed snippets."""
        relative = path.relative_to(self.repo_root).as_posix()
        category = self._category_for_content_path(relative)
        text = path.read_text(encoding="utf-8")
        sections = self._split_markdown_sections(text)
        company = self._company_from_filename(path)
        count = 0
        if not sections:
            cleaned = text.strip()
            if cleaned:
                self._upsert(
                    category=category,
                    company=company,
                    heading=path.stem.replace("-", " ").title(),
                    tags=self._markdown_tags(category, company),
                    source_path=relative,
                    content=cleaned,
                    detail_level=DetailLevel.DETAILED.value,
                )
                count += 1
            return count
        for heading, body in sections:
            body_text = body.strip()
            if not body_text:
                continue
            source = f"{relative}#{self._slug(heading)}"
            self._upsert(
                category=category,
                company=company if category == "experience" else None,
                heading=heading,
                tags=self._markdown_tags(category, company, heading),
                source_path=source,
                content=body_text,
                detail_level=DetailLevel.DETAILED.value,
            )
            count += 1
        return count

    def _upsert(
        self,
        *,
        category: str,
        heading: Optional[str],
        tags: list[str],
        source_path: str,
        content: str,
        detail_level: str,
        company: Optional[str] = None,
        role: Optional[str] = None,
    ) -> None:
        """Upsert a snippet + variant keyed by source path and content hash."""
        content_hash = self._hash_content(content)
        snippet = Snippet(
            category=category,
            company=company,
            role=role,
            heading=heading,
            tags=tags,
            source_path=source_path,
            content_hash=content_hash,
        )
        variant = SnippetVariant(
            detail_level=detail_level,
            content=content,
        )
        self.database.upsert_by_source(snippet, variant)

    @staticmethod
    def _format_subsection(sub: dict[str, Any]) -> str:
        """Flatten a subsection dict into plain text for storage."""
        parts: list[str] = []
        intro = SnippetImporter._as_text(sub.get("intro"))
        if intro:
            parts.append(intro)
        for paragraph in sub.get("paragraphs") or []:
            text = SnippetImporter._as_text(paragraph)
            if text:
                parts.append(text)
        bullets = sub.get("bullets") or []
        for bullet in bullets:
            text = SnippetImporter._as_text(bullet)
            if text:
                parts.append(f"- {text}")
        return "\n\n".join(parts).strip()

    @staticmethod
    def _split_markdown_sections(text: str) -> list[tuple[str, str]]:
        """Split markdown into (heading, body) pairs on ATX headings."""
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            return []
        sections: list[tuple[str, str]] = []
        for index, match in enumerate(matches):
            heading = match.group(2).strip()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            sections.append((heading, body))
        return sections

    @staticmethod
    def _category_for_content_path(relative: str) -> str:
        """Map a content/ relative path to a snippet category."""
        if relative.startswith("content/work-experience/"):
            return "experience"
        if relative.startswith("content/requirements/"):
            return "requirement"
        return "part"

    @staticmethod
    def _company_from_filename(path: Path) -> Optional[str]:
        """Derive a company-ish label from a work-experience filename."""
        if "work-experience" not in path.parts:
            return None
        stem = path.stem.replace("-", " ").replace("_", " ").strip()
        return stem.title() if stem else None

    @staticmethod
    def _experience_tags(
        company: Optional[str], heading: Optional[str] = None
    ) -> list[str]:
        """Build tags for an experience snippet."""
        tags = ["experience", "yaml"]
        if company:
            tags.append(company.lower())
        if heading:
            tags.append(heading.lower())
        return tags

    @staticmethod
    def _markdown_tags(
        category: str,
        company: Optional[str] = None,
        heading: Optional[str] = None,
    ) -> list[str]:
        """Build tags for a markdown-sourced snippet."""
        tags = [category, "markdown"]
        if company:
            tags.append(company.lower())
        if heading:
            tags.append(heading.lower())
        return tags

    @staticmethod
    def _slug(value: str) -> str:
        """Create a simple slug for source-path anchors."""
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return slug or "section"

    @staticmethod
    def _hash_content(content: str) -> str:
        """Return a stable SHA-256 hex digest of normalised content."""
        normalised = "\n".join(line.rstrip() for line in content.strip().splitlines())
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()

    @staticmethod
    def _as_text(value: Any) -> str:
        """Coerce a YAML scalar to a stripped string."""
        if value is None:
            return ""
        return str(value).strip()


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point: seed ``data/snippets.db`` from the repository."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = list(argv if argv is not None else sys.argv[1:])
    repo_root = Path(__file__).resolve().parents[2]
    db_path = Path(args[0]) if args else repo_root / "data" / "snippets.db"
    database = SnippetDatabase(db_path)
    importer = SnippetImporter(database=database, repo_root=repo_root)
    stats = importer.seed()
    total = sum(stats.values())
    print(f"Seeded {total} snippets into {db_path}")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
