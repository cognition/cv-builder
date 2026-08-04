"""Behave environment — real CV Studio Flask app (not the wireframe)."""

from __future__ import annotations

import os
import runpy
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
SRC = REPO_ROOT / "src"


def before_all(context: Any) -> None:
    """Boot serve-editor against the real repo, with an isolated SQLite DB."""
    for path in (str(SCRIPTS), str(SRC), str(REPO_ROOT / "features" / "steps")):
        if path not in sys.path:
            sys.path.insert(0, path)

    context.repo_root = REPO_ROOT
    context._bdd_tmpdir = Path(tempfile.mkdtemp(prefix="cvbuilder-bdd-"))
    db_path = context._bdd_tmpdir / "snippets.db"
    os.environ["SNIPPETS_DB"] = str(db_path)

    # Variants must stay under the real repo root so relative_to(REPO_ROOT) works.
    variants_dir = REPO_ROOT / "cv" / "variants" / "_behave_tmp"
    if variants_dir.exists():
        shutil.rmtree(variants_dir)
    variants_dir.mkdir(parents=True, exist_ok=True)
    context._bdd_variants_dir = variants_dir

    sys.modules.pop("serve-editor", None)
    namespace = runpy.run_path(str(SCRIPTS / "serve-editor.py"))

    namespace["VARIANTS_DIR"] = variants_dir
    for func_name in (
        "home_page",
        "_list_variants",
        "api_list_variants",
        "api_delete_variant_folder",
        "api_render_variant",
        "api_compose",
    ):
        func = namespace.get(func_name)
        if func is not None:
            func.__globals__["VARIANTS_DIR"] = variants_dir

    original_composer = namespace["CvComposer"]

    class _IsolatedComposer(original_composer):  # type: ignore[misc,valid-type]
        """Write composed variants under the BDD scratch directory."""

        def __init__(self, database: Any, repo_root: Path) -> None:
            """Initialise the composer and redirect the variants directory."""
            super().__init__(database=database, repo_root=repo_root)
            self.variants_dir = variants_dir

        def compose(
            self,
            name: str,
            selections: Any,
            render_pdf: bool = True,
        ) -> dict[str, Any]:
            """Compose without PDF rendering (avoids browser deps in BDD)."""
            return super().compose(
                name=name, selections=selections, render_pdf=False
            )

    namespace["CvComposer"] = _IsolatedComposer
    namespace["api_compose"].__globals__["CvComposer"] = _IsolatedComposer

    app = namespace["app"]
    app.config["TESTING"] = True
    context.app_ns = namespace
    context.app = app
    context.client = app.test_client()
    context.variants_dir = variants_dir

    from cvbuilder.importer import SnippetImporter

    database = namespace["_database"]()
    SnippetImporter(database=database, repo_root=REPO_ROOT).seed()


def before_scenario(context: Any, scenario: Any) -> None:
    """Reset per-scenario response state."""
    context.response = None
    context.response_json = None
    context.last_response = None
    context.page = None
    context.page_html = None
    context.page_path = None
    context.created_snippet_id = None
    context.created_source_id = None
    context.compose_name = None


def after_all(context: Any) -> None:
    """Remove temporary BDD database and variant scratch directories."""
    tmp = getattr(context, "_bdd_tmpdir", None)
    if tmp is not None and Path(tmp).exists():
        shutil.rmtree(tmp, ignore_errors=True)
    variants = getattr(context, "_bdd_variants_dir", None)
    if variants is not None and Path(variants).exists():
        shutil.rmtree(variants, ignore_errors=True)
