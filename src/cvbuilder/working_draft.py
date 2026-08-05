"""Apply Tailor selections into the Working Draft CV document store."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from cvbuilder.composer import CvComposer
from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.models import DetailLevel


class WorkingDraftApplier:
    """Compose Tailor selections onto the DB working (master) document."""

    def __init__(
        self,
        database: SnippetDatabase,
        store: DocumentStore,
        repo_root: Path,
    ) -> None:
        """Initialise with DB, document store, and repo root for composer.

        Args:
            database: Snippet library used when resolving selections.
            store: Document store holding the working CV YAML.
            repo_root: Repository root passed through to ``CvComposer``.
        """
        self.database = database
        self.store = store
        self.composer = CvComposer(database=database, repo_root=repo_root)

    def apply_selections(
        self,
        selections: list[dict[str, Any]],
        *,
        history_label: str = "apply-draft",
        pin_label: Optional[str] = None,
    ) -> dict[str, Any]:
        """Push history, compose onto working YAML, save; optional pin.

        Missing snippet ids or detail levels are skipped with a warning payload
        so a stale Tailor draft after reseeding does not block valid items.

        Args:
            selections: Ordered Tailor selections to apply.
            history_label: Undo label recorded before the change.
            pin_label: When set, freeze the result as a pin after save.

        Returns:
            Summary including document id, selection count, skipped items,
            and optional pin.

        Raises:
            ValueError: Empty usable selections or missing working document.
            KeyError: Missing snippet detail level after filtering.
        """
        if not selections:
            raise ValueError("selections must be a non-empty list")
        usable, skipped = self._partition_usable_selections(selections)
        if not usable:
            reasons = [
                f"snippet {item['snippet_id']} {item['reason']}" for item in skipped
            ]
            raise ValueError("; ".join(reasons) or "selections must be a non-empty list")
        working = self.store.get_working()
        if working is None or working.id is None:
            raise ValueError("working draft document is missing")
        base = self.composer.base_document_shell(working.content_yaml)
        document = self.composer.build_document_from_selections(base, usable)
        new_yaml = self.composer.dump_document_yaml(document)
        self.store.push_before_change(
            working.id, history_label, working.content_yaml
        )
        saved = self.store.upsert_working(new_yaml)
        pin_payload: Optional[dict[str, Any]] = None
        if pin_label and str(pin_label).strip():
            pin = self.store.create_pin(saved.id, str(pin_label).strip())
            pin_payload = {
                "id": pin.id,
                "label": pin.label,
            }
        return {
            "ok": True,
            "document_id": saved.id,
            "selection_count": len(usable),
            "skipped": skipped,
            "pin": pin_payload,
        }

    def _partition_usable_selections(
        self, selections: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Split selections into usable rows and skipped rows with reasons."""
        usable: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for raw in selections:
            if not isinstance(raw, dict):
                skipped.append(
                    {
                        "snippet_id": None,
                        "detail_level": None,
                        "reason": "not found",
                    }
                )
                continue
            snippet_id = raw.get("snippet_id")
            try:
                snippet_id_int = int(snippet_id)
            except (TypeError, ValueError):
                skipped.append(
                    {
                        "snippet_id": snippet_id,
                        "detail_level": raw.get("detail_level"),
                        "reason": "not found",
                    }
                )
                continue
            detail_level = str(
                raw.get("detail_level") or DetailLevel.STANDARD.value
            )
            snippet = self.database.get_snippet(snippet_id_int)
            if snippet is None:
                skipped.append(
                    {
                        "snippet_id": snippet_id_int,
                        "detail_level": detail_level,
                        "reason": "not found",
                    }
                )
                continue
            if snippet.variant_for(detail_level) is None:
                skipped.append(
                    {
                        "snippet_id": snippet_id_int,
                        "detail_level": detail_level,
                        "reason": f"has no {detail_level!r} variant",
                    }
                )
                continue
            usable.append(dict(raw))
        return usable, skipped

    def merge_selections(
        self,
        selections: list[dict[str, Any]],
        *,
        history_label: str = "library-add",
    ) -> dict[str, Any]:
        """Merge snippet selections into the Working Draft without wiping it.

        When another detail level of an added snippet is already present, both
        remain and conflict highlights are stored for the Working Draft editor.

        Args:
            selections: Ordered Tailor-style selections to append.
            history_label: Undo label recorded before the change.

        Returns:
            Summary with document id, counts, optional warning, and conflicts.

        Raises:
            ValueError: Empty selections or missing working document.
            KeyError: Missing snippet detail level.
        """
        if not selections:
            raise ValueError("selections must be a non-empty list")
        working = self.store.get_working()
        if working is None or working.id is None:
            raise ValueError("working draft document is missing")
        document = self.composer.load_document_yaml(working.content_yaml)
        added, new_conflicts = self.composer.merge_selections_into_document(
            document, selections
        )
        if added == 0:
            return {
                "ok": True,
                "document_id": working.id,
                "selection_count": len(selections),
                "added_count": 0,
                "skipped_count": len(selections),
                "conflicts": [],
                "warning": None,
            }
        new_yaml = self.composer.dump_document_yaml(document)
        self.store.push_before_change(
            working.id, history_label, working.content_yaml
        )
        saved = self.store.upsert_working(new_yaml)
        if saved.id is None:
            raise ValueError("working draft document is missing")
        warning: Optional[str] = None
        conflicts_payload: list[dict[str, Any]] = []
        if new_conflicts:
            prior = [item.to_dict() for item in self.store.list_conflict_highlights(saved.id)]
            saved_conflicts = self.store.replace_conflict_highlights(
                saved.id, prior + new_conflicts
            )
            conflicts_payload = [item.to_dict() for item in saved_conflicts]
            warning = (
                "Another detail level of this content is already on the "
                "Working Draft — open Working Draft CV to choose."
            )
        return {
            "ok": True,
            "document_id": saved.id,
            "selection_count": len(selections),
            "added_count": added,
            "skipped_count": len(selections) - added,
            "conflicts": conflicts_payload,
            "warning": warning,
        }

    def resolve_conflicts(self, action: str) -> dict[str, Any]:
        """Resolve Working Draft detail-level conflict highlights.

        Args:
            action: One of ``keep_both``, ``keep_existing``, or ``keep_new``.

        Returns:
            Summary including action taken and remaining conflict count.

        Raises:
            ValueError: Unknown action or missing working document.
        """
        normalised = str(action or "").strip().lower()
        if normalised not in {"keep_both", "keep_existing", "keep_new"}:
            raise ValueError(
                "action must be keep_both, keep_existing, or keep_new"
            )
        working = self.store.get_working()
        if working is None or working.id is None:
            raise ValueError("working draft document is missing")
        highlights = self.store.list_conflict_highlights(working.id)
        if not highlights:
            return {
                "ok": True,
                "action": normalised,
                "document_id": working.id,
                "removed_count": 0,
                "conflicts": [],
            }
        removed_count = 0
        if normalised in {"keep_existing", "keep_new"}:
            drop_mark = "new" if normalised == "keep_existing" else "existing"
            needles = [
                item.needle for item in highlights if item.mark == drop_mark
            ]
            document = self.composer.load_document_yaml(working.content_yaml)
            removed_count = self.composer.remove_needles_from_document(
                document, needles
            )
            if removed_count:
                new_yaml = self.composer.dump_document_yaml(document)
                self.store.push_before_change(
                    working.id, f"conflict-{normalised}", working.content_yaml
                )
                working = self.store.upsert_working(new_yaml)
        self.store.clear_conflict_highlights(working.id)
        return {
            "ok": True,
            "action": normalised,
            "document_id": working.id,
            "removed_count": removed_count,
            "conflicts": [],
        }

    def load_variant(self, name: str) -> dict[str, Any]:
        """Replace Working Draft content sections from a named application CV.

        Preserves the Working Draft ``person`` block. Pushes history first and
        clears any pending conflict highlights.

        Args:
            name: Variant document name (application-ready CV).

        Returns:
            Summary with document id and loaded variant name.

        Raises:
            ValueError: Missing working document or empty name.
            KeyError: Variant name not found.
        """
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("variant name is required")
        working = self.store.get_working()
        if working is None or working.id is None:
            raise ValueError("working draft document is missing")
        variant = self.store.get_variant(clean_name)
        if variant is None:
            raise KeyError(f"CV variant {clean_name!r} was not found")
        working_doc = self.composer.load_document_yaml(working.content_yaml)
        variant_doc = self.composer.load_document_yaml(variant.content_yaml)
        person = deepcopy(working_doc.get("person") or {})
        merged = {
            "person": person,
            "skills": deepcopy(
                variant_doc.get("skills")
                or {"technical": [], "functional": []}
            ),
            "bio": deepcopy(variant_doc.get("bio") or []),
            "experience": deepcopy(variant_doc.get("experience") or []),
            "education": deepcopy(variant_doc.get("education") or []),
            "panels": deepcopy(variant_doc.get("panels") or []),
        }
        new_yaml = self.composer.dump_document_yaml(merged)
        self.store.push_before_change(
            working.id, f"load-variant:{clean_name}", working.content_yaml
        )
        saved = self.store.upsert_working(new_yaml)
        if saved.id is None:
            raise ValueError("working draft document is missing")
        self.store.clear_conflict_highlights(saved.id)
        return {
            "ok": True,
            "document_id": saved.id,
            "name": clean_name,
        }
