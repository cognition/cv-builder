"""Content library audit and batch populate/refine operations."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Optional

from cvbuilder.database import SnippetDatabase
from cvbuilder.models import DetailLevel, Snippet, SnippetVariant

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

    def upsert_snippets(
        self,
        snippets: list[dict[str, Any]],
        dry_run: bool = True,
    ) -> dict[str, Any]:
        """Batch create or update snippets from structured items.

        Args:
            snippets: Items with optional ``id``, metadata, and ``variants``.
            dry_run: When True (default), plan only; do not write.

        Returns:
            Plan or apply result with created/updated/errors and counts.
        """
        created: list[dict[str, Any]] = []
        updated: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for index, raw in enumerate(snippets):
            try:
                item = self._normalise_upsert_item(raw)
            except ValueError as exc:
                errors.append({"index": index, "message": str(exc)})
                continue

            snippet_id = item.get("id")
            if snippet_id is None:
                summary = self._summarise_item(item)
                if dry_run:
                    created.append(
                        {
                            "id": None,
                            "planned_index": index,
                            "category": item["category"],
                            "summary": summary,
                        }
                    )
                else:
                    new_id = self._apply_create(item)
                    created.append(
                        {
                            "id": new_id,
                            "planned_index": index,
                            "category": item["category"],
                            "summary": summary,
                        }
                    )
            else:
                existing = self._database.get_snippet(int(snippet_id))
                if existing is None:
                    errors.append(
                        {
                            "index": index,
                            "message": f"snippet {snippet_id} not found",
                        }
                    )
                    continue
                summary = self._summarise_item(item, existing=existing)
                if not dry_run:
                    self._apply_update(existing, item)
                updated.append({"id": int(snippet_id), "summary": summary})

        return {
            "dry_run": dry_run,
            "created": created,
            "updated": updated,
            "errors": errors,
            "counts": {
                "created": len(created),
                "updated": len(updated),
                "errors": len(errors),
            },
        }

    def _normalise_upsert_item(self, raw: Any) -> dict[str, Any]:
        """Validate and normalise one upsert payload item.

        Args:
            raw: Untyped item from the batch payload.

        Returns:
            Normalised item dict ready for create or update.

        Raises:
            ValueError: When the item is invalid.
        """
        if not isinstance(raw, dict):
            raise ValueError("snippet item must be an object")
        snippet_id = raw.get("id")
        category = raw.get("category")
        variants_raw = raw.get("variants") or {}
        if not isinstance(variants_raw, dict):
            raise ValueError("variants must be an object")
        variants: dict[str, str] = {}
        for level, content in variants_raw.items():
            if level not in DETAIL_LEVELS:
                raise ValueError(f"invalid detail level {level!r}")
            text = str(content).strip() if content is not None else ""
            if not text:
                raise ValueError(f"variant {level!r} content is empty")
            variants[str(level)] = str(content)

        if snippet_id is None:
            if category is None or not str(category).strip():
                raise ValueError("category is required when creating")
            if str(category) not in VALID_CATEGORIES:
                raise ValueError(f"invalid category {category!r}")
            if not variants:
                raise ValueError("at least one variant is required when creating")
        else:
            if category is not None and str(category) not in VALID_CATEGORIES:
                raise ValueError(f"invalid category {category!r}")

        tags = raw.get("tags")
        parsed_tags: Optional[list[str]]
        if tags is None:
            parsed_tags = None
        elif isinstance(tags, list):
            parsed_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
        elif isinstance(tags, str):
            parsed_tags = [part.strip() for part in tags.split(",") if part.strip()]
        else:
            raise ValueError("tags must be a list or comma-separated string")

        return {
            "id": int(snippet_id) if snippet_id is not None else None,
            "category": str(category) if category is not None else None,
            "company": raw.get("company"),
            "role": raw.get("role"),
            "heading": raw.get("heading"),
            "tags": parsed_tags,
            "variants": variants,
            "has_company": "company" in raw,
            "has_role": "role" in raw,
            "has_heading": "heading" in raw,
        }

    def _summarise_item(
        self,
        item: dict[str, Any],
        existing: Optional[Snippet] = None,
    ) -> str:
        """Build a short human-readable summary for plan/result rows.

        Args:
            item: Normalised upsert item.
            existing: Existing snippet when updating.

        Returns:
            Pipe-separated summary string.
        """
        category = item.get("category") or (
            existing.category if existing is not None else "?"
        )
        heading = item.get("heading")
        if heading is None and existing is not None:
            heading = existing.heading
        company = item.get("company")
        if company is None and existing is not None:
            company = existing.company
        bits = [str(category)]
        if company:
            bits.append(str(company))
        if heading:
            bits.append(str(heading))
        levels = sorted(item.get("variants") or {})
        if levels:
            bits.append("variants=" + ",".join(levels))
        return " | ".join(bits)

    def _apply_create(self, item: dict[str, Any]) -> int:
        """Persist a new snippet and its variants.

        Args:
            item: Normalised create item.

        Returns:
            New snippet primary key.
        """
        snippet_id = self._database.create_snippet(
            Snippet(
                category=str(item["category"]),
                company=item.get("company"),
                role=item.get("role"),
                heading=item.get("heading"),
                tags=list(item["tags"] or []),
            )
        )
        for level, content in item["variants"].items():
            self._database.upsert_variant(
                SnippetVariant(
                    snippet_id=snippet_id,
                    detail_level=level,
                    content=content,
                )
            )
        return snippet_id

    def _apply_update(self, existing: Snippet, item: dict[str, Any]) -> None:
        """Apply metadata and variant upserts to an existing snippet.

        Args:
            existing: Snippet loaded from the database.
            item: Normalised update item.
        """
        if item.get("category") is not None:
            existing.category = str(item["category"])
        if item.get("has_company"):
            existing.company = item.get("company")
        if item.get("has_role"):
            existing.role = item.get("role")
        if item.get("has_heading"):
            existing.heading = item.get("heading")
        if item.get("tags") is not None:
            existing.tags = list(item["tags"] or [])
        self._database.update_snippet(existing)
        assert existing.id is not None
        for level, content in item["variants"].items():
            self._database.upsert_variant(
                SnippetVariant(
                    snippet_id=int(existing.id),
                    detail_level=level,
                    content=content,
                )
            )
