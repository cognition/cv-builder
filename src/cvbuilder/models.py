"""Typed models for the CV snippet library and composition drafts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class DetailLevel(str, Enum):
    """Supported levels of descriptive detail for a snippet variant."""

    BRIEF = "brief"
    STANDARD = "standard"
    DETAILED = "detailed"


@dataclass
class SnippetVariant:
    """One detail-level rendering of a snippet's content."""

    detail_level: str
    content: str
    snippet_id: Optional[int] = None
    id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class Snippet:
    """A reusable CV content unit with optional detail-level variants."""

    category: str
    company: Optional[str] = None
    role: Optional[str] = None
    heading: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    source_path: Optional[str] = None
    content_hash: Optional[str] = None
    id: Optional[int] = None
    variants: list[SnippetVariant] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "id": self.id,
            "category": self.category,
            "company": self.company,
            "role": self.role,
            "heading": self.heading,
            "tags": list(self.tags),
            "source_path": self.source_path,
            "content_hash": self.content_hash,
            "variants": [variant.to_dict() for variant in self.variants],
        }

    def variant_for(self, detail_level: str) -> Optional[SnippetVariant]:
        """Return the variant matching ``detail_level``, if present."""
        for variant in self.variants:
            if variant.detail_level == detail_level:
                return variant
        return None


@dataclass
class SelectionItem:
    """One selected snippet variant for composing a custom CV."""

    snippet_id: int
    detail_level: str = DetailLevel.STANDARD.value
    section: Optional[str] = None


@dataclass
class CvDraft:
    """An ordered selection of snippets that will become a CV variant."""

    name: str
    selections: list[SelectionItem] = field(default_factory=list)
    person_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class QuestionSource:
    """A document (job posting, questionnaire, or competency matrix) that
    application questions were extracted from."""

    title: str
    source_type: str = "form"  # "job" | "form" | "matrix"
    id: Optional[int] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "id": self.id,
            "title": self.title,
            "source_type": self.source_type,
            "created_at": self.created_at,
        }


@dataclass
class QuestionEvidence:
    """One snippet variant linked as evidence for a question's answer."""

    snippet_id: int
    detail_level: str = DetailLevel.STANDARD.value
    heading: Optional[str] = None
    company: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return asdict(self)


@dataclass
class Question:
    """A single application question and its (possibly empty) answer."""

    prompt: str
    source_id: Optional[int] = None
    source_title: Optional[str] = None
    source_type: Optional[str] = None
    answer: str = ""
    id: Optional[int] = None
    created_at: Optional[str] = None
    evidence: list[QuestionEvidence] = field(default_factory=list)

    @property
    def status(self) -> str:
        """Derive a workflow status from answer text + linked evidence.

        Not stored — computed so it can never drift from the underlying
        data: "complete" once there's an answer, "needs_evidence" when
        there's neither an answer nor evidence, "in_progress" once
        evidence exists but no answer has been written yet.
        """
        if self.answer.strip():
            return "complete"
        if self.evidence:
            return "in_progress"
        return "needs_evidence"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "id": self.id,
            "source_id": self.source_id,
            "source_title": self.source_title,
            "source_type": self.source_type,
            "prompt": self.prompt,
            "answer": self.answer,
            "status": self.status,
            "created_at": self.created_at,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass
class Draft:
    """A named, persisted builder selection saved for later reuse."""

    name: str
    selections: list[dict[str, Any]] = field(default_factory=list)
    id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "id": self.id,
            "name": self.name,
            "selections": list(self.selections),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ResumeImport:
    """A resume file uploaded for import, and what it produced."""

    filename: str
    file_type: str
    stored_path: str
    snippet_count: int = 0
    id: Optional[int] = None
    created_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "id": self.id,
            "filename": self.filename,
            "file_type": self.file_type,
            "snippet_count": self.snippet_count,
            "created_at": self.created_at,
        }
