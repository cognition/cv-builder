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
