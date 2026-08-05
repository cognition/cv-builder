"""Content library audit and batch populate/refine operations."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Optional

from cvbuilder.database import SnippetDatabase
from cvbuilder.models import DetailLevel

VALID_CATEGORIES: frozenset[str] = frozenset(
    {"bio", "skill", "experience", "education", "part", "requirement"}
)
DETAIL_LEVELS: tuple[str, ...] = tuple(level.value for level in DetailLevel)
MIN_VARIANT_CHARS: int = 20
MAX_VARIANT_CHARS: int = 8000


class LibraryOps:
    """Audit and batch mutate the snippet Content library."""

    def __init__(self, database: SnippetDatabase) -> None:
        """Bind to an open snippet database.

        Args:
            database: SnippetDatabase used for reads and writes.
        """
        self._database = database

    def audit(
        self,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        search: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return a health report for filtered snippets.

        Args:
            category: Optional exact category filter.
            tag: Optional tag filter.
            search: Optional substring search filter.

        Returns:
            Report with counts, missing levels, empty tags, sparse headings,
            length outliers, and duplicate candidates.
        """
        snippets = self._database.list_snippets(
            category=category, tag=tag, search=search
        )
        counts: dict[str, int] = defaultdict(int)
        missing_detail_levels: list[dict[str, Any]] = []
        empty_tags: list[dict[str, Any]] = []
        sparse_headings: list[dict[str, Any]] = []
        length_outliers: list[dict[str, Any]] = []
        content_hashes: dict[str, list[int]] = defaultdict(list)
        company_role: dict[tuple[str, str], list[int]] = defaultdict(list)

        for snippet in snippets:
            counts[snippet.category] += 1
            present = {variant.detail_level for variant in snippet.variants}
            missing = [level for level in DETAIL_LEVELS if level not in present]
            if missing:
                missing_detail_levels.append(
                    {
                        "id": snippet.id,
                        "category": snippet.category,
                        "missing": missing,
                    }
                )
            if not snippet.tags:
                empty_tags.append({"id": snippet.id, "category": snippet.category})
            if snippet.category in {"experience", "education"}:
                heading = (snippet.heading or "").strip()
                if not heading:
                    sparse_headings.append(
                        {
                            "id": snippet.id,
                            "category": snippet.category,
                            "heading": snippet.heading,
                        }
                    )
            company = (snippet.company or "").strip().casefold()
            role = (snippet.role or "").strip().casefold()
            if snippet.category == "experience" and company and role and snippet.id is not None:
                company_role[(company, role)].append(int(snippet.id))
            for variant in snippet.variants:
                text = variant.content or ""
                length = len(text.strip())
                if length < MIN_VARIANT_CHARS:
                    length_outliers.append(
                        {
                            "id": snippet.id,
                            "detail_level": variant.detail_level,
                            "chars": length,
                            "reason": "too_short",
                        }
                    )
                elif length > MAX_VARIANT_CHARS:
                    length_outliers.append(
                        {
                            "id": snippet.id,
                            "detail_level": variant.detail_level,
                            "chars": length,
                            "reason": "too_long",
                        }
                    )
                stripped = text.strip()
                if stripped and snippet.id is not None:
                    digest = hashlib.sha256(stripped.encode("utf-8")).hexdigest()
                    content_hashes[digest].append(int(snippet.id))

        duplicate_candidates: list[dict[str, Any]] = []
        for (company, role), ids in company_role.items():
            unique_ids = sorted(set(ids))
            if len(unique_ids) >= 2:
                duplicate_candidates.append(
                    {
                        "ids": unique_ids,
                        "reason": "same_company_role",
                        "company": company,
                        "role": role,
                    }
                )
        for digest, ids in content_hashes.items():
            unique_ids = sorted(set(ids))
            if len(unique_ids) >= 2:
                duplicate_candidates.append(
                    {
                        "ids": unique_ids,
                        "reason": "identical_content",
                        "content_hash": digest[:12],
                    }
                )

        return {
            "counts_by_category": dict(counts),
            "missing_detail_levels": missing_detail_levels,
            "empty_tags": empty_tags,
            "sparse_headings": sparse_headings,
            "length_outliers": length_outliers,
            "duplicate_candidates": duplicate_candidates,
        }
