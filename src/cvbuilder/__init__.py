"""SQLite-backed CV snippet library and custom-CV composer."""

from cvbuilder.document_store import DocumentStore
from cvbuilder.models import CvDraft, DetailLevel, Draft, Snippet, SnippetVariant

__all__ = [
    "CvDraft",
    "DetailLevel",
    "DocumentStore",
    "Draft",
    "Snippet",
    "SnippetVariant",
]

__version__ = "0.2.22.0"
