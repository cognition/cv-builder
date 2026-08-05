"""Apply Tailor selections into the Working Draft CV document store."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from cvbuilder.composer import CvComposer
from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore


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

        Args:
            selections: Ordered Tailor selections to apply.
            history_label: Undo label recorded before the change.
            pin_label: When set, freeze the result as a pin after save.

        Returns:
            Summary including document id, selection count, and optional pin.

        Raises:
            ValueError: Empty selections or missing working document.
            KeyError: Missing snippet detail level.
        """
        if not selections:
            raise ValueError("selections must be a non-empty list")
        working = self.store.get_working()
        if working is None or working.id is None:
            raise ValueError("working draft document is missing")
        base = self.composer.base_document_shell(working.content_yaml)
        document = self.composer.build_document_from_selections(
            base, selections
        )
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
            "selection_count": len(selections),
            "pin": pin_payload,
        }
