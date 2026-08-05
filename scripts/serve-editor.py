#!/usr/bin/env python3
"""Local editor for the HTML/CSS CV: edit text in the browser, then render
a real PDF on demand to preview it.

Also exposes the SQLite snippet library, custom-CV builder, drafts,
job-posting matching, and variant manager endpoints.

Usage: python3 scripts/serve-editor.py [port]
Then open http://127.0.0.1:<port>/edit
     or http://127.0.0.1:<port>/build
     or http://127.0.0.1:<port>/variants

Binds to 127.0.0.1 by default (override with EDITOR_HOST). It serves the
whole repo over HTTP for local asset resolution (images, stylesheet) —
fine for personal local use, but don't change the host to 0.0.0.0 without
adding auth, since that would expose the whole repo (including cover
letters/applications) to your LAN. Docker Compose publishes only on
127.0.0.1 while setting EDITOR_HOST=0.0.0.0 inside the container.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cvweb
from cvbuilder.composer import CvComposer
from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.importer import SnippetImporter
from cvbuilder.markdown_export import MarkdownExporter
from cvbuilder.matcher import SnippetMatcher
from cvbuilder.models import (
    CvDocument,
    DetailLevel,
    Question,
    QuestionSource,
    ResumeImport,
    Snippet,
    SnippetVariant,
)
from cvbuilder.question_extractor import extract_questions
from cvbuilder.resume_extractor import (
    SUPPORTED_EXTENSIONS,
    build_candidates,
    content_hash,
    extract_text,
    parse_resume,
)
from cvbuilder.resume_to_master import apply_resume_to_master
from cvbuilder.paths import DataPaths
from cvbuilder.working_draft import WorkingDraftApplier

from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    request,
    send_from_directory,
)
from jinja2 import (
    Environment as JinjaEnvironment,
    FileSystemLoader as JinjaFSLoader,
    select_autoescape,
)
from markupsafe import Markup
from ruamel.yaml import YAML

app = Flask(__name__, static_folder=None)

# Real app-chrome pages (Home, Tailor, Content library, Versions, Assets,
# Connect AI) render through cv/web/src/ Jinja templates that share one
# app shell (cv/web/src/shell/base.html). This is separate from
# cvweb.render_html(), which renders the CV document itself
# (template.html.j2) and must stay untouched by app-chrome concerns.
_APP_ENV = JinjaEnvironment(
    loader=JinjaFSLoader(str(cvweb.WEB_DIR / "src")),
    autoescape=select_autoescape(["html"]),
)

_DATA_PATHS = DataPaths(cvweb.REPO_ROOT)
PREVIEW_PDF = _DATA_PATHS.preview_pdf
DEFAULT_DB = _DATA_PATHS.snippets_db
VARIANTS_DIR = _DATA_PATHS.variants
EXPORT_FORMATS = frozenset({"yaml", "markdown", "pdf"})
EXPORT_DOCUMENT_KINDS = frozenset({"master", "variant"})
ASSETS_DIR = _DATA_PATHS.assets_images
ASSETS_BRANDING_DIR = _DATA_PATHS.assets_branding
ALLOWED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico"}
IMAGE_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_VARIANT_YAML = YAML()
_VARIANT_YAML.preserve_quotes = True

# Uploaded resume files. Overridable so tests/BDD scenarios can point this
# at a scratch directory instead of writing into the tracked repo tree
# (same pattern as SNIPPETS_DB / features/environment.py's VARIANTS_DIR).
IMPORTS_DIR = _DATA_PATHS.imports
STAGING_DIR = IMPORTS_DIR / "staging"
MAX_IMPORT_BYTES = 25 * 1024 * 1024
IMPORT_SECTIONS = ("profile", "experience", "skills", "education")
IMPORT_MODES = frozenset({"library", "master"})
IMPORT_FILE_TYPES = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".md": "md",
    ".markdown": "md",
    ".txt": "txt",
}
_IMPORT_TOKEN_RE = re.compile(r"^[0-9a-f]{16}$")


def _db_path() -> Path:
    """Return the configured SQLite database path."""
    return Path(os.environ.get("SNIPPETS_DB", str(DEFAULT_DB)))


def _database() -> SnippetDatabase:
    """Open (and create if needed) the snippet database."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    database = SnippetDatabase(path)
    database.ensure_schema()
    return database


def _document_store() -> DocumentStore:
    """Open the DB-backed CV document store, bootstrapping filesystem data once."""
    database = _database()
    store = DocumentStore(database)
    store.bootstrap_from_filesystem(cvweb.REPO_ROOT)
    return store


def _master_document(store: DocumentStore) -> CvDocument:
    """Return the bootstrapped Master CV document or raise a clear error."""
    document = store.get_master()
    if document is None:
        raise LookupError("Master CV document is not available")
    return document


def _master_data(store: DocumentStore) -> tuple[CvDocument, Any]:
    """Return the Master CV document and parsed YAML content."""
    document = _master_document(store)
    data = cvweb.load_data_text(document.content_yaml)
    if not isinstance(data, dict):
        raise ValueError("Master CV YAML must be a mapping")
    return document, data


def _export_document_data(
    store: DocumentStore, payload: dict[str, Any]
) -> tuple[CvDocument, dict[str, Any]]:
    """Return the requested export document and parsed YAML content."""
    kind = str(payload.get("document", "master")).strip().lower()
    if kind not in EXPORT_DOCUMENT_KINDS:
        raise ValueError("document must be one of: master, variant")
    if kind == "master":
        document = _master_document(store)
    else:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("name is required for variant export")
        document = store.get_variant(name)
        if document is None:
            raise LookupError(f"CV variant {name!r} is not available")
    data = cvweb.load_data_text(document.content_yaml)
    if not isinstance(data, dict):
        label = "Master CV" if kind == "master" else f"CV variant {document.name!r}"
        raise ValueError(f"{label} YAML must be a mapping")
    return document, data


def _document_for_pin(store: DocumentStore, payload: dict[str, Any]) -> CvDocument:
    """Return the requested pin target document."""
    kind = str(payload.get("document", "master")).strip().lower()
    if kind not in EXPORT_DOCUMENT_KINDS:
        raise ValueError("document must be one of: master, variant")
    if kind == "master":
        return _master_document(store)
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ValueError("name is required for variant pins")
    document = store.get_variant(name)
    if document is None:
        raise LookupError(f"CV variant {name!r} is not available")
    return document


def _default_export_path(document: CvDocument, export_format: str) -> Path:
    """Return the default output path for an export request."""
    if document.kind == "variant" and document.name:
        safe = _safe_name(document.name)
        if not safe:
            raise ValueError("variant name is invalid")
        variant_dir = VARIANTS_DIR / safe
        if export_format == "yaml":
            return variant_dir / "data.yaml"
        if export_format == "markdown":
            return variant_dir / f"{safe}.md"
        return variant_dir / f"{safe}.pdf"
    if export_format == "yaml":
        return cvweb.DATA_FILE
    if export_format == "markdown":
        return PREVIEW_PDF.with_suffix(".md")
    return PREVIEW_PDF


def _export_path(
    payload: dict[str, Any], document: CvDocument, export_format: str
) -> Path:
    """Resolve an export output path from the payload or defaults."""
    raw_path = str(payload.get("path", "")).strip()
    if not raw_path:
        return _default_export_path(document, export_format)
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return cvweb.REPO_ROOT / path


def _relative_export_path(path: Path) -> str:
    """Return a URL-friendly path for JSON responses when possible."""
    variant_url = _variant_file_url(path, require_exists=False)
    if variant_url is not None:
        return variant_url
    try:
        return path.relative_to(cvweb.REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _variant_file_url(
    path: Path, *, require_exists: bool = True
) -> Optional[str]:
    """Return a ``cv/variants/...`` URL path for a file under VARIANTS_DIR.

    Args:
        path: Absolute or relative filesystem path to a variant export.
        require_exists: When True, return None unless the file exists.

    Returns:
        A browser path suitable for ``/<path>`` (served from VARIANTS_DIR),
        or None when the path is outside the variants directory.
    """
    resolved = path.resolve()
    if require_exists and not resolved.is_file():
        return None
    try:
        relative = resolved.relative_to(VARIANTS_DIR.resolve()).as_posix()
    except ValueError:
        return None
    return f"cv/variants/{relative}"


def _cleanup_partial_export(path: Path) -> None:
    """Remove an export target that may have been partially written."""
    if path.exists():
        try:
            path.unlink()
        except OSError:
            return


def _master_unavailable_html(exc: Exception) -> str:
    """Render a Studio shell page when the Working Draft is missing or invalid."""
    template = _APP_ENV.from_string(
        '{% extends "shell/base.html" %}'
        '{% block title %}CV Studio — Working Draft unavailable{% endblock %}'
        '{% block content %}'
        '<div class="empty-state"><h2>Working Draft unavailable</h2>'
        "<p>{{ message }}</p></div>"
        "{% endblock %}"
    )
    return template.render(
        message=str(exc),
        crumb="WORKING DRAFT",
        title="Working Draft unavailable",
        active="master",
    )


def _history_status(store: DocumentStore, document: CvDocument) -> dict[str, Any]:
    """Return history status for a persisted document."""
    if document.id is None:
        raise ValueError("Master CV document id is required")
    return store.history_status(document.id)


def _safe_name(name: str) -> str:
    """Sanitise a name for use as a directory or draft key."""
    cleaned = _SAFE_NAME_RE.sub("-", name.strip()).strip("-._")
    return cleaned[:80]


def _parse_tags(raw: Any) -> list[str]:
    """Normalise tags from a list or comma-separated string."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _payload_bool(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    """Return a boolean flag from JSON or query-string values."""
    raw = payload.get(key, request.args.get(key, default))
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return bool(raw)


def _render_page(template_name: str, **context: Any) -> str:
    """Render one of the real app-chrome pages through the shared shell."""
    return _APP_ENV.get_template(template_name).render(**context)


def _apply_variants(
    database: SnippetDatabase, snippet_id: int, payload: dict[str, Any]
) -> None:
    """Upsert variants from ``content``/``detail_level`` or a ``variants`` map."""
    variants = payload.get("variants")
    if isinstance(variants, dict):
        for level, content in variants.items():
            if content is None:
                continue
            text = str(content).strip()
            if not text:
                continue
            database.upsert_variant(
                SnippetVariant(
                    snippet_id=snippet_id,
                    detail_level=str(level),
                    content=text,
                )
            )
        return
    if "content" in payload and "detail_level" in payload:
        database.upsert_variant(
            SnippetVariant(
                snippet_id=snippet_id,
                detail_level=str(payload["detail_level"]),
                content=str(payload["content"]),
            )
        )


@app.get("/")
def home_page() -> str:
    """Serve the real dashboard: live snippet/variant counts + recent versions."""
    database = _database()
    snippet_count = len(database.list_snippets())
    variants = _list_variants()
    return _render_page(
        "pages/home.html",
        crumb="WORKSPACE",
        title="CV Studio",
        active="home",
        snippet_count=snippet_count,
        variant_count=len(variants),
        recent_variants=variants[:4],
    )


@app.get("/edit")
def edit_page() -> Any:
    """Serve Working Draft CV inside the Studio shell."""
    store = _document_store()
    try:
        _, data = _master_data(store)
    except (LookupError, ValueError) as exc:
        return make_response(_master_unavailable_html(exc), 404)
    body = cvweb.render_cv_body(data=data, edit_mode=True)
    return _render_page(
        "pages/master.html",
        crumb="WORKING DRAFT",
        title="Edit your Working Draft CV",
        active="master",
        cv_body_html=Markup(body),
    )


@app.get("/library")
def library_page() -> str:
    """Serve the content-library browse view over the snippet database."""
    return _render_page(
        "pages/library.html", crumb="LIBRARY", title="Your career content", active="library"
    )


@app.get("/details")
def details_page() -> str:
    """Serve the personal-details page (identity, contact, social profiles)."""
    return _render_page(
        "pages/details.html",
        crumb="PROFILE",
        title="Personal and contact details",
        active="details",
    )


@app.get("/import")
def import_page() -> str:
    """Serve the resume-import page (upload, review, import into the library)."""
    return _render_page(
        "pages/import.html",
        crumb="IMPORT",
        title="Import a resume",
        active="import",
    )


@app.get("/build")
def build_page() -> str:
    """Serve the tailor flow: paste a posting, choose content, compose a version."""
    return _render_page(
        "pages/tailor.html", crumb="NEW TAILORED CV", title="Tell us about the role", active="tailor"
    )


@app.get("/questions")
def questions_page() -> str:
    """Serve the application-questions page (sources, questions, answers)."""
    return _render_page(
        "pages/questions.html",
        crumb="QUESTIONS",
        title="Build evidence-backed answers",
        active="questions",
    )


@app.get("/variants")
def variants_page() -> str:
    """Serve the composed-variant manager page."""
    return _render_page(
        "pages/versions.html", crumb="VERSIONS", title="Application-ready CVs", active="versions"
    )


@app.get("/connect")
def connect_page() -> str:
    """Serve the Connect AI (MCP) setup page."""
    return _render_page(
        "pages/connect.html",
        crumb="CONNECT AI",
        title="Use CV Studio with your assistant",
        active="connect",
    )


@app.get("/wireframe")
def wireframe_page() -> str:
    """Serve the standalone, sample-data-only product wireframe."""
    return (cvweb.WEB_DIR / "wireframe.html").read_text(encoding="utf-8")


@app.get("/docs")
def docs_page() -> str:
    """Serve README.md as a plain readable page — the "how to use" link."""
    readme = (cvweb.REPO_ROOT / "README.md").read_text(encoding="utf-8")
    return _render_page(
        "pages/docs.html", crumb="DOCS", title="How to use", readme=readme
    )


def _history() -> cvweb.EditHistory:
    """Return the edit-history store for the active data.yaml."""
    return cvweb.edit_history()


@app.get("/api/person")
def api_get_person() -> Any:
    """Return the Master CV person block for the Assets page."""
    store = _document_store()
    try:
        _, data = _master_data(store)
    except (LookupError, ValueError) as exc:
        return jsonify(error=str(exc)), 404
    person = data.get("person") if isinstance(data, dict) else None
    return jsonify(person if isinstance(person, dict) else {})


@app.post("/api/save")
def api_save() -> Any:
    """Persist in-place editor edits to the Master CV document."""
    edits = request.get_json(force=True)
    if not isinstance(edits, list):
        return jsonify(error="edits must be a list"), 400
    store = _document_store()
    try:
        document, data = _master_data(store)
    except (LookupError, ValueError) as exc:
        return jsonify(error=str(exc)), 404
    if edits:
        before = document.content_yaml
        for item in edits:
            cvweb.set_leaf(data, item["path"], item["value"])
        after = cvweb.dump_data_text(data)
        if after != before:
            if document.id is None:
                return jsonify(error="Master CV document id is required"), 500
            store.push_before_change(document.id, "save", before)
            document = store.upsert_master(after)
    return jsonify(ok=True, **_history_status(store, document))


@app.post("/api/structure")
def api_structure() -> Any:
    """Apply a structural insert/delete/move operation to the Master CV."""
    payload = request.get_json(force=True) or {}
    op = str(payload.get("op", "")).strip()
    path = str(payload.get("path", "")).strip()
    allowed_ops = {"insert", "delete", "move", "replace", "replace-subsection"}
    if op not in allowed_ops:
        return jsonify(error="op must be one of: " + ", ".join(sorted(allowed_ops))), 400
    if not path:
        return jsonify(error="path is required"), 400
    store = _document_store()
    try:
        document, data = _master_data(store)
    except (LookupError, ValueError) as exc:
        return jsonify(error=str(exc)), 404
    before = document.content_yaml
    try:
        if op == "insert":
            list_path = path
            cvweb.insert_item(
                data,
                list_path,
                index=payload.get("index"),
                value=payload.get("value"),
            )
        elif op == "delete":
            cvweb.delete_item(data, path)
        elif op == "replace":
            value = payload.get("value")
            if not isinstance(value, str) or not value.strip():
                return jsonify(error="value is required for replace"), 400
            cvweb.set_leaf(data, path, value.strip())
        elif op == "replace-subsection":
            content = str(payload.get("content", "")).strip()
            if not content:
                return jsonify(error="content is required for replace-subsection"), 400
            subsection = cvweb.subsection_from_text(
                str(payload.get("heading", "")), content
            )
            cvweb.replace_item(data, path, subsection)
        else:
            offset = payload.get("offset")
            if offset is None:
                return jsonify(error="offset is required for move"), 400
            cvweb.move_item(data, path, int(offset))
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return jsonify(error=str(exc)), 400
    after = cvweb.dump_data_text(data)
    if after != before:
        if document.id is None:
            return jsonify(error="Master CV document id is required"), 500
        store.push_before_change(document.id, op, before)
        document = store.upsert_master(after)
    return jsonify(ok=True, reload=True, **_history_status(store, document))


@app.get("/api/history")
def api_history() -> Any:
    """Return whether undo/redo are available."""
    store = _document_store()
    try:
        document = _master_document(store)
    except LookupError as exc:
        return jsonify(error=str(exc)), 404
    return jsonify(_history_status(store, document))


@app.post("/api/undo")
def api_undo() -> Any:
    """Restore the previous Master CV snapshot and reload the editor."""
    store = _document_store()
    try:
        document = _master_document(store)
    except LookupError as exc:
        return jsonify(error=str(exc)), 404
    if document.id is None:
        return jsonify(error="Master CV document id is required"), 500
    if not store.history_status(document.id)["can_undo"]:
        return jsonify(error="nothing to undo"), 400
    result = store.undo(document.id)
    return jsonify(ok=True, reload=True, **result)


@app.post("/api/redo")
def api_redo() -> Any:
    """Re-apply the most recently undone Master CV snapshot."""
    store = _document_store()
    try:
        document = _master_document(store)
    except LookupError as exc:
        return jsonify(error=str(exc)), 404
    if document.id is None:
        return jsonify(error="Master CV document id is required"), 500
    if not store.history_status(document.id)["can_redo"]:
        return jsonify(error="nothing to redo"), 400
    result = store.redo(document.id)
    return jsonify(ok=True, reload=True, **result)


@app.get("/api/pins")
def api_list_pins() -> Any:
    """List saved pins for a master or variant CV document."""
    store = _document_store()
    try:
        document = _document_for_pin(store, dict(request.args))
    except LookupError as exc:
        return jsonify(error=str(exc)), 404
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    if document.id is None:
        return jsonify(error="CV document id is required"), 500
    return jsonify([pin.to_dict() for pin in store.list_pins(document.id)])


@app.post("/api/pins")
def api_create_pin() -> Any:
    """Create a named pin for a master or variant CV document."""
    payload = request.get_json(force=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error="payload must be an object"), 400
    label = str(payload.get("label", "")).strip()
    if not label:
        return jsonify(error="label is required"), 400
    store = _document_store()
    try:
        document = _document_for_pin(store, payload)
        if document.id is None:
            return jsonify(error="CV document id is required"), 500
        pin = store.create_pin(document.id, label)
    except LookupError as exc:
        return jsonify(error=str(exc)), 404
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(pin.to_dict())


@app.post("/api/pins/<int:pin_id>/restore")
def api_restore_pin(pin_id: int) -> Any:
    """Restore a saved pin, auto-pinning the current state first."""
    store = _document_store()
    try:
        pin = store.restore_pin(pin_id)
    except KeyError as exc:
        return jsonify(error=str(exc)), 404
    return jsonify(ok=True, reload=True, pin=pin.to_dict())


@app.delete("/api/pins/<int:pin_id>")
def api_delete_pin(pin_id: int) -> Any:
    """Delete a saved pin."""
    store = _document_store()
    try:
        store.delete_pin(pin_id)
    except KeyError as exc:
        return jsonify(error=str(exc)), 404
    return jsonify(ok=True)


@app.post("/api/export")
def api_export() -> Any:
    """Export a DB-backed CV document as YAML, Markdown, or PDF."""
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify(error="payload must be an object"), 400
    export_format = str(payload.get("format", "pdf")).strip().lower()
    if export_format not in EXPORT_FORMATS:
        return jsonify(error="format must be one of: yaml, markdown, pdf"), 400

    store = _document_store()
    try:
        document, data = _export_document_data(store, payload)
        out_path = _export_path(payload, document, export_format)
    except LookupError as exc:
        return jsonify(error=str(exc)), 404
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if export_format == "yaml":
            out_path.write_text(document.content_yaml, encoding="utf-8")
        elif export_format == "markdown":
            out_path.write_text(MarkdownExporter().render(data), encoding="utf-8")
        else:
            cvweb.export_pdf(out_path, data=data)
    except (OSError, RuntimeError, SystemExit) as exc:
        _cleanup_partial_export(out_path)
        return jsonify(error=str(exc)), 500

    return jsonify(
        ok=True,
        format=export_format,
        document=document.kind,
        name=document.name,
        path=_relative_export_path(out_path),
    )


@app.get("/api/preview.pdf")
def api_preview_pdf() -> Any:
    """Serve a fresh preview PDF of the Working Draft CV."""
    store = _document_store()
    try:
        _, data = _master_data(store)
    except (LookupError, ValueError) as exc:
        return jsonify(error=str(exc)), 404
    try:
        PREVIEW_PDF.parent.mkdir(parents=True, exist_ok=True)
        cvweb.export_pdf(PREVIEW_PDF, data=data)
    except (OSError, RuntimeError, SystemExit) as exc:
        return jsonify(error=str(exc)), 500
    return send_from_directory(
        PREVIEW_PDF.parent, PREVIEW_PDF.name, mimetype="application/pdf"
    )


@app.get("/api/snippets")
def api_list_snippets() -> Any:
    """List snippets, optionally filtered by category/tag/level/search."""
    database = _database()
    snippets = database.list_snippets(
        category=request.args.get("category"),
        tag=request.args.get("tag"),
        detail_level=request.args.get("level"),
        search=request.args.get("search"),
    )
    return jsonify([snippet.to_dict() for snippet in snippets])


@app.get("/api/snippets/<int:snippet_id>")
def api_get_snippet(snippet_id: int) -> Any:
    """Return a single snippet by id."""
    database = _database()
    snippet = database.get_snippet(snippet_id)
    if snippet is None:
        return jsonify(error="not found"), 404
    return jsonify(snippet.to_dict())


@app.post("/api/snippets")
def api_create_snippet() -> Any:
    """Create a snippet and optional detail-level variants."""
    payload = request.get_json(force=True) or {}
    database = _database()
    snippet = Snippet(
        category=str(payload.get("category", "part")),
        company=payload.get("company") or None,
        role=payload.get("role") or None,
        heading=payload.get("heading") or None,
        tags=_parse_tags(payload.get("tags")),
        source_path=payload.get("source_path"),
        content_hash=payload.get("content_hash"),
    )
    snippet_id = database.create_snippet(snippet)
    _apply_variants(database, snippet_id, payload)
    created = database.get_snippet(snippet_id)
    return jsonify(created.to_dict() if created else {"id": snippet_id}), 201


@app.put("/api/snippets/<int:snippet_id>")
def api_update_snippet(snippet_id: int) -> Any:
    """Update snippet metadata and/or detail-level variants."""
    payload = request.get_json(force=True) or {}
    database = _database()
    existing = database.get_snippet(snippet_id)
    if existing is None:
        return jsonify(error="not found"), 404
    existing.category = str(payload.get("category", existing.category))
    if "company" in payload:
        existing.company = payload.get("company") or None
    if "role" in payload:
        existing.role = payload.get("role") or None
    if "heading" in payload:
        existing.heading = payload.get("heading") or None
    if "tags" in payload:
        existing.tags = _parse_tags(payload.get("tags"))
    database.update_snippet(existing)
    _apply_variants(database, snippet_id, payload)
    updated = database.get_snippet(snippet_id)
    return jsonify(updated.to_dict() if updated else {"id": snippet_id})


@app.delete("/api/snippets/<int:snippet_id>")
def api_delete_snippet(snippet_id: int) -> Any:
    """Delete a snippet and all of its variants."""
    database = _database()
    if not database.delete_snippet(snippet_id):
        return jsonify(error="not found"), 404
    return jsonify(ok=True)


@app.delete("/api/snippets/<int:snippet_id>/variants/<level>")
def api_delete_variant(snippet_id: int, level: str) -> Any:
    """Delete one detail-level variant for a snippet."""
    if level not in {
        DetailLevel.BRIEF.value,
        DetailLevel.STANDARD.value,
        DetailLevel.DETAILED.value,
    }:
        return jsonify(error="invalid detail level"), 400
    database = _database()
    if database.get_snippet(snippet_id) is None:
        return jsonify(error="not found"), 404
    if not database.delete_variant(snippet_id, level):
        return jsonify(error="variant not found"), 404
    return jsonify(ok=True)


@app.get("/api/drafts")
def api_list_drafts() -> Any:
    """List saved builder drafts."""
    database = _database()
    return jsonify([draft.to_dict() for draft in database.list_drafts()])


@app.get("/api/drafts/<name>")
def api_get_draft(name: str) -> Any:
    """Return one saved draft by name."""
    database = _database()
    draft = database.get_draft(name)
    if draft is None:
        return jsonify(error="not found"), 404
    return jsonify(draft.to_dict())


@app.put("/api/drafts/<name>")
def api_save_draft(name: str) -> Any:
    """Create or update a named draft; optionally apply into Working Draft."""
    payload = request.get_json(force=True) or {}
    selections = payload.get("selections") or []
    if not isinstance(selections, list):
        return jsonify(error="selections must be a list"), 400
    apply = bool(payload.get("apply"))
    pin_label = payload.get("pin_label")
    database = _database()
    try:
        draft = database.save_draft(name, selections)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    result = draft.to_dict()
    result["applied"] = False
    if apply:
        if not selections:
            return jsonify(error="selections must be a non-empty list"), 400
        store = _document_store()
        applier = WorkingDraftApplier(database, store, cvweb.REPO_ROOT)
        try:
            applied = applier.apply_selections(
                selections,
                history_label=f"draft:{name}",
                pin_label=str(pin_label).strip() if pin_label else None,
            )
        except (ValueError, KeyError) as exc:
            return jsonify(error=str(exc)), 400
        result["applied"] = True
        result["apply"] = applied
    return jsonify(result)


@app.post("/api/drafts/<name>/apply")
def api_apply_draft(name: str) -> Any:
    """Re-apply a saved draft's selections into the Working Draft CV."""
    payload = request.get_json(force=True) or {}
    pin_label = payload.get("pin_label")
    database = _database()
    draft = database.get_draft(name)
    if draft is None:
        return jsonify(error="not found"), 404
    store = _document_store()
    applier = WorkingDraftApplier(database, store, cvweb.REPO_ROOT)
    try:
        applied = applier.apply_selections(
            draft.selections,
            history_label=f"draft:{name}",
            pin_label=str(pin_label).strip() if pin_label else None,
        )
    except (ValueError, KeyError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify({"ok": True, "name": name, **applied})


@app.post("/api/working-draft/add-snippets")
def api_working_draft_add_snippets() -> Any:
    """Merge library snippet selections into the Working Draft CV."""
    payload = request.get_json(force=True) or {}
    selections = payload.get("selections") or []
    if not isinstance(selections, list) or not selections:
        return jsonify(error="selections must be a non-empty list"), 400
    database = _database()
    store = _document_store()
    applier = WorkingDraftApplier(database, store, cvweb.REPO_ROOT)
    try:
        result = applier.merge_selections(
            selections, history_label="library-add"
        )
    except (ValueError, KeyError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result)


@app.get("/api/working-draft/conflicts")
def api_working_draft_conflicts() -> Any:
    """Return pending detail-level conflict highlights for the Working Draft."""
    store = _document_store()
    working = store.get_working()
    if working is None or working.id is None:
        return jsonify(error="working draft document is missing"), 404
    highlights = store.list_conflict_highlights(working.id)
    return jsonify(
        {
            "document_id": working.id,
            "conflicts": [item.to_dict() for item in highlights],
        }
    )


@app.post("/api/working-draft/conflicts/resolve")
def api_working_draft_conflicts_resolve() -> Any:
    """Resolve Working Draft conflict highlights (keep both / existing / new)."""
    payload = request.get_json(force=True) or {}
    action = payload.get("action")
    database = _database()
    store = _document_store()
    applier = WorkingDraftApplier(database, store, cvweb.REPO_ROOT)
    try:
        result = applier.resolve_conflicts(str(action or ""))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result)


@app.post("/api/working-draft/load-variant")
def api_working_draft_load_variant() -> Any:
    """Replace Working Draft content sections from an application-ready CV."""
    payload = request.get_json(force=True) or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    database = _database()
    store = _document_store()
    applier = WorkingDraftApplier(database, store, cvweb.REPO_ROOT)
    try:
        result = applier.load_variant(name)
    except KeyError as exc:
        return jsonify(error=str(exc)), 404
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result)


@app.delete("/api/drafts/<name>")
def api_delete_draft(name: str) -> Any:
    """Delete a named draft."""
    database = _database()
    if not database.delete_draft(name):
        return jsonify(error="not found"), 404
    return jsonify(ok=True)


@app.post("/api/match")
def api_match() -> Any:
    """Rank snippets against a pasted job posting."""
    payload = request.get_json(force=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify(error="text is required"), 400
    limit = int(payload.get("limit") or 25)
    category = payload.get("category")
    database = _database()
    matcher = SnippetMatcher(database)
    results = matcher.match(text=text, limit=limit, category=category)
    return jsonify([result.to_dict() for result in results])


@app.post("/api/compose")
def api_compose() -> Any:
    """Compose selected snippet variants into a named DB-backed CV variant."""
    payload = request.get_json(force=True) or {}
    name = str(payload.get("name", "")).strip()
    if not name:
        return jsonify(error="name is required"), 400
    selections = payload.get("selections") or []
    if not isinstance(selections, list) or not selections:
        return jsonify(error="selections must be a non-empty list"), 400
    database = _database()
    composer = CvComposer(database=database, repo_root=cvweb.REPO_ROOT)
    try:
        result = composer.compose(
            name=name,
            selections=selections,
            render_pdf=_payload_bool(payload, "render_pdf", False),
            export_yaml=_payload_bool(payload, "export_yaml", False),
        )
    except (KeyError, ValueError, OSError, RuntimeError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(result)


@app.post("/api/seed")
def api_seed() -> Any:
    """Re-seed the snippet database from data.yaml and content/."""
    database = _database()
    importer = SnippetImporter(database=database, repo_root=cvweb.REPO_ROOT)
    stats = importer.seed()
    return jsonify(stats)


_QUESTION_SOURCE_TYPES = {"job", "form", "matrix"}


@app.get("/api/question-sources")
def api_list_question_sources() -> Any:
    """List all application-question sources with their question counts."""
    database = _database()
    sources = database.list_question_sources()
    questions_by_source: dict[int, int] = {}
    for question in database.list_questions():
        questions_by_source[question.source_id] = (
            questions_by_source.get(question.source_id, 0) + 1
        )
    return jsonify(
        [
            {**source.to_dict(), "question_count": questions_by_source.get(source.id, 0)}
            for source in sources
        ]
    )


@app.post("/api/question-sources")
def api_create_question_source() -> Any:
    """Create a question source, optionally extracting questions from pasted text."""
    payload = request.get_json(force=True) or {}
    title = str(payload.get("title", "")).strip()
    source_type = str(payload.get("source_type", "form"))
    if not title:
        return jsonify(error="title is required"), 400
    if source_type not in _QUESTION_SOURCE_TYPES:
        return jsonify(error="source_type must be one of: " + ", ".join(sorted(_QUESTION_SOURCE_TYPES))), 400
    database = _database()
    source_id = database.create_question_source(
        QuestionSource(title=title, source_type=source_type)
    )
    text = str(payload.get("text", ""))
    created_ids: list[int] = []
    if text.strip():
        for prompt in extract_questions(text, source_type):
            created_ids.append(
                database.create_question(Question(source_id=source_id, prompt=prompt))
            )
    source = database.get_question_source(source_id)
    return jsonify(
        {**source.to_dict(), "question_count": len(created_ids)}
    ), 201


@app.delete("/api/question-sources/<int:source_id>")
def api_delete_question_source(source_id: int) -> Any:
    """Delete a question source and every question/evidence link under it."""
    database = _database()
    if not database.delete_question_source(source_id):
        return jsonify(error="not found"), 404
    return jsonify(ok=True)


@app.get("/api/questions")
def api_list_questions() -> Any:
    """List questions, optionally filtered to one source."""
    database = _database()
    source_id = request.args.get("source_id")
    questions = database.list_questions(
        source_id=int(source_id) if source_id else None
    )
    return jsonify([question.to_dict() for question in questions])


@app.get("/api/questions/<int:question_id>")
def api_get_question(question_id: int) -> Any:
    """Return one question with its evidence."""
    database = _database()
    question = database.get_question(question_id)
    if question is None:
        return jsonify(error="not found"), 404
    return jsonify(question.to_dict())


@app.put("/api/questions/<int:question_id>")
def api_update_question(question_id: int) -> Any:
    """Save a question's answer text."""
    payload = request.get_json(force=True) or {}
    database = _database()
    if not database.update_question_answer(question_id, str(payload.get("answer", ""))):
        return jsonify(error="not found"), 404
    question = database.get_question(question_id)
    return jsonify(question.to_dict() if question else {"id": question_id})


@app.delete("/api/questions/<int:question_id>")
def api_delete_question(question_id: int) -> Any:
    """Delete a question."""
    database = _database()
    if not database.delete_question(question_id):
        return jsonify(error="not found"), 404
    return jsonify(ok=True)


@app.post("/api/questions/<int:question_id>/evidence")
def api_add_question_evidence(question_id: int) -> Any:
    """Link a snippet as evidence for a question."""
    payload = request.get_json(force=True) or {}
    snippet_id = payload.get("snippet_id")
    if not isinstance(snippet_id, int):
        return jsonify(error="snippet_id is required"), 400
    database = _database()
    if database.get_question(question_id) is None:
        return jsonify(error="question not found"), 404
    if database.get_snippet(snippet_id) is None:
        return jsonify(error="snippet not found"), 404
    database.add_question_evidence(
        question_id, snippet_id, str(payload.get("detail_level", "standard"))
    )
    question = database.get_question(question_id)
    return jsonify(question.to_dict() if question else {"id": question_id}), 201


@app.delete("/api/questions/<int:question_id>/evidence/<int:snippet_id>")
def api_remove_question_evidence(question_id: int, snippet_id: int) -> Any:
    """Unlink a snippet from a question's evidence."""
    database = _database()
    if not database.remove_question_evidence(question_id, snippet_id):
        return jsonify(error="not found"), 404
    return jsonify(ok=True)


@app.post("/api/questions/<int:question_id>/suggest")
def api_suggest_question_answer(question_id: int) -> Any:
    """Draft an answer from the question's evidence, matching more in first if needed.

    If the question has no evidence yet, ranks snippets against the
    question's own prompt text (via the same matcher used for job-posting
    matching) and links the top few before drafting. The draft is a
    literal join of the linked snippets' content — real assembly from the
    user's own material, not a generated/fabricated answer.
    """
    database = _database()
    question = database.get_question(question_id)
    if question is None:
        return jsonify(error="not found"), 404
    if not question.evidence:
        matcher = SnippetMatcher(database)
        for result in matcher.match(text=question.prompt, limit=3):
            if result.snippet.id is not None:
                variant = result.snippet.variant_for("standard") or (
                    result.snippet.variants[0] if result.snippet.variants else None
                )
                if variant is not None:
                    database.add_question_evidence(
                        question_id, result.snippet.id, variant.detail_level
                    )
        question = database.get_question(question_id)
    paragraphs = []
    for item in question.evidence:
        snippet = database.get_snippet(item.snippet_id)
        if snippet is None:
            continue
        variant = snippet.variant_for(item.detail_level) or (
            snippet.variants[0] if snippet.variants else None
        )
        if variant is not None:
            paragraphs.append(variant.content)
    draft = " ".join(paragraphs)
    return jsonify(answer=draft, evidence=[item.to_dict() for item in question.evidence])


def _staged_import_path(token: str) -> Optional[Path]:
    """Find a staged upload by its token, if it hasn't been confirmed yet."""
    if not _IMPORT_TOKEN_RE.match(token) or not STAGING_DIR.is_dir():
        return None
    matches = list(STAGING_DIR.glob(f"{token}__*"))
    return matches[0] if matches else None


def _import_candidates_with_duplicates(
    database: SnippetDatabase, resume: Any
) -> list[dict[str, Any]]:
    """Flag candidates whose content already exists as a stored snippet."""
    candidates = build_candidates(resume)
    existing = database.existing_content_hashes(
        [content_hash(item["content"]) for item in candidates]
    )
    for candidate in candidates:
        candidate["duplicate"] = content_hash(candidate["content"]) in existing
    return candidates


@app.post("/api/imports")
def api_upload_import() -> Any:
    """Stage an uploaded resume file and return its parsed preview.

    The file is written to a staging directory and parsed immediately so
    the review screen can show real extracted content, but nothing is
    written to the snippet library until /confirm is called — and that
    route re-reads and re-parses the staged file itself rather than
    trusting a client-sent preview payload.
    """
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify(error="no file provided"), 400
    original = Path(uploaded.filename)
    ext = original.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return jsonify(error=f"unsupported file type: {ext or '(none)'}"), 400
    data = uploaded.read()
    if len(data) > MAX_IMPORT_BYTES:
        return jsonify(error="file exceeds 25 MB limit"), 400
    try:
        resume = parse_resume(extract_text(uploaded.filename, data))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(8)
    stem = _safe_name(original.stem) or "resume"
    (STAGING_DIR / f"{token}__{stem}{ext}").write_bytes(data)

    database = _database()
    return jsonify(
        token=token,
        filename=uploaded.filename,
        file_type=IMPORT_FILE_TYPES.get(ext, ext.lstrip(".")),
        counts=resume.counts(),
        candidates=_import_candidates_with_duplicates(database, resume),
    ), 201


@app.post("/api/imports/<token>/confirm")
def api_confirm_import(token: str) -> Any:
    """Re-parse the staged file and create snippets for the chosen sections."""
    staged = _staged_import_path(token)
    if staged is None:
        return jsonify(error="import not found or already confirmed"), 404
    payload = request.get_json(force=True) or {}
    mode = payload.get("mode") or "library"
    if mode not in IMPORT_MODES:
        return jsonify(error="unsupported import mode"), 400
    requested_sections = payload.get("sections")
    enabled = (
        {name for name in IMPORT_SECTIONS if requested_sections.get(name, True)}
        if isinstance(requested_sections, dict)
        else set(IMPORT_SECTIONS)
    )

    original_name = staged.name.split("__", 1)[1]
    try:
        resume = parse_resume(extract_text(original_name, staged.read_bytes()))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    if mode == "master":
        store = _document_store()
        try:
            document, data = _master_data(store)
        except (LookupError, ValueError) as exc:
            return jsonify(error=str(exc)), 404
        if document.id is None:
            return jsonify(error="Master CV document id is required"), 500
        store.create_pin(document.id, f"before-import:{token}")
        patched = apply_resume_to_master(data, resume, enabled)
        store.upsert_master(cvweb.dump_data_text(patched))

    database = _database()
    created = 0
    for candidate in build_candidates(resume):
        if candidate["section"] not in enabled or not candidate["content"].strip():
            continue
        snippet = Snippet(
            category=candidate["category"],
            company=candidate["company"],
            role=candidate["role"],
            heading=candidate["heading"],
            tags=candidate["tags"],
            source_path=f"resume-import/{token}#{candidate['section']}[{candidate['index']}]",
            content_hash=content_hash(candidate["content"]),
        )
        variant = SnippetVariant(
            detail_level=DetailLevel.STANDARD.value, content=candidate["content"]
        )
        database.upsert_by_source(snippet, variant)
        created += 1

    IMPORTS_DIR.mkdir(parents=True, exist_ok=True)
    permanent_path = IMPORTS_DIR / staged.name
    shutil.move(str(staged), str(permanent_path))
    ext = Path(original_name).suffix.lower()
    import_id = database.create_resume_import(
        ResumeImport(
            filename=original_name,
            file_type=IMPORT_FILE_TYPES.get(ext, ext.lstrip(".")),
            stored_path=staged.name,
            snippet_count=created,
        )
    )
    result = {
        "id": import_id,
        "filename": original_name,
        "snippet_count": created,
        "mode": mode,
        "master_updated": mode == "master",
    }
    return jsonify(**result)


@app.delete("/api/imports/staging/<token>")
def api_discard_staged_import(token: str) -> Any:
    """Delete an unconfirmed staged upload (used when the user cancels review)."""
    staged = _staged_import_path(token)
    if staged is not None:
        staged.unlink()
    return jsonify(ok=True)


@app.get("/api/imports")
def api_list_imports() -> Any:
    """List past resume imports, newest first."""
    database = _database()
    return jsonify([item.to_dict() for item in database.list_resume_imports()])


@app.get("/api/imports/<int:import_id>/source")
def api_download_import_source(import_id: int) -> Any:
    """Download the originally uploaded resume file for one import."""
    database = _database()
    record = database.get_resume_import(import_id)
    if record is None:
        return jsonify(error="not found"), 404
    if not (IMPORTS_DIR / record.stored_path).is_file():
        return jsonify(error="source file is missing"), 404
    return send_from_directory(
        IMPORTS_DIR,
        record.stored_path,
        download_name=record.filename,
        as_attachment=True,
    )


@app.delete("/api/imports/<int:import_id>")
def api_delete_import(import_id: int) -> Any:
    """Delete an import record and its stored source file."""
    database = _database()
    record = database.get_resume_import(import_id)
    if record is None:
        return jsonify(error="not found"), 404
    database.delete_resume_import(import_id)
    stored = IMPORTS_DIR / record.stored_path
    if stored.is_file():
        stored.unlink()
    return jsonify(ok=True)


def _image_entry(path: Path) -> dict[str, Any]:
    """Describe one image file for the picker UI."""
    return {
        "name": path.name,
        "web_path": f"/assets/images/{path.name}",
        # Path relative to cv/web/, the form data.yaml expects for person.photo.
        "data_path": f"../../assets/images/{path.name}",
        "size": path.stat().st_size,
    }


def _unique_image_path(stem: str, ext: str) -> Path:
    """Return a non-clobbering destination path in the assets directory."""
    candidate = ASSETS_DIR / f"{stem}{ext}"
    counter = 1
    while candidate.exists():
        candidate = ASSETS_DIR / f"{stem}-{counter}{ext}"
        counter += 1
    return candidate


@app.get("/assets")
def assets_page() -> str:
    """Serve the asset library page over the existing images API."""
    return _render_page(
        "pages/assets.html", crumb="ASSET LIBRARY", title="Your visual identity", active="assets"
    )


@app.get("/api/images")
def api_list_images() -> Any:
    """List images available under assets/images/."""
    images: list[dict[str, Any]] = []
    if ASSETS_DIR.is_dir():
        for path in sorted(ASSETS_DIR.iterdir()):
            if path.is_file() and path.suffix.lower() in ALLOWED_IMAGE_EXTS:
                images.append(_image_entry(path))
    return jsonify(images)


@app.post("/api/images/upload")
def api_upload_image() -> Any:
    """Save an uploaded image into assets/images/."""
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify(error="no file provided"), 400
    original = Path(uploaded.filename)
    ext = original.suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        return jsonify(error=f"unsupported image type: {ext or 'none'}"), 400
    stem = _safe_name(original.stem) or "image"
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    destination = _unique_image_path(stem, ext)
    uploaded.save(str(destination))
    if destination.stat().st_size > MAX_IMAGE_BYTES:
        destination.unlink()
        return jsonify(error="image exceeds 10 MB limit"), 400
    return jsonify(_image_entry(destination)), 201


@app.delete("/api/images/<path:filename>")
def api_delete_image(filename: str) -> Any:
    """Delete one uploaded image from the persistent assets directory.

    Built-in branding icons are not stored here and cannot be deleted.
    When the deleted file is the current profile photo, ``person.photo``
    is cleared on the Working Draft document.
    """
    # Reject nested or traversed names — only a bare filename is allowed.
    safe = Path(filename).name
    if (
        not safe
        or safe != filename
        or safe in {".", ".."}
        or "/" in filename
        or "\\" in filename
    ):
        return jsonify(error="invalid image name"), 400
    if Path(safe).suffix.lower() not in ALLOWED_IMAGE_EXTS:
        return jsonify(error="unsupported image type"), 400

    assets_root = ASSETS_DIR.resolve()
    target = (ASSETS_DIR / safe).resolve()
    try:
        target.relative_to(assets_root)
    except ValueError:
        return jsonify(error="invalid path"), 400
    if not target.is_file():
        return jsonify(error="not found"), 404

    data_path = f"../../assets/images/{safe}"
    cleared_profile_photo = False
    store = _document_store()
    try:
        document, data = _master_data(store)
    except (LookupError, ValueError):
        document = None
        data = None
    if (
        isinstance(data, dict)
        and isinstance(data.get("person"), dict)
        and document is not None
        and document.id is not None
    ):
        current = str(data["person"].get("photo") or "")
        if current == data_path or current.endswith(f"/{safe}"):
            before = document.content_yaml
            data["person"]["photo"] = ""
            after = cvweb.dump_data_text(data)
            if after != before:
                store.push_before_change(document.id, "delete-asset", before)
                store.upsert_master(after)
                cleared_profile_photo = True

    try:
        target.unlink()
    except OSError as exc:
        return jsonify(error=f"failed to delete: {exc}"), 500
    return jsonify(ok=True, name=safe, cleared_profile_photo=cleared_profile_photo)


@app.post("/api/images/fetch")
def api_fetch_image() -> Any:
    """Download an image (icon, photo, etc.) from a URL into assets/images/."""
    payload = request.get_json(force=True) or {}
    url = str(payload.get("url", "")).strip()
    if not url:
        return jsonify(error="url is required"), 400
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return jsonify(error="only http(s) URLs are supported"), 400
    req = urllib.request.Request(url, headers={"User-Agent": "cv-editor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            data = resp.read(MAX_IMAGE_BYTES + 1)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return jsonify(error=f"download failed: {exc}"), 400
    if len(data) > MAX_IMAGE_BYTES:
        return jsonify(error="image exceeds 10 MB limit"), 400

    url_ext = Path(parsed.path).suffix.lower()
    ext = IMAGE_CONTENT_TYPES.get(content_type) or (
        url_ext if url_ext in ALLOWED_IMAGE_EXTS else ""
    )
    if not ext:
        return jsonify(
            error=f"not an image (content-type: {content_type or 'unknown'})"
        ), 400

    requested = str(payload.get("name", "")).strip()
    stem = _safe_name(Path(requested).stem if requested else Path(parsed.path).stem)
    stem = stem or "image"
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    destination = _unique_image_path(stem, ext)
    destination.write_bytes(data)
    return jsonify(_image_entry(destination)), 201


def _list_variants() -> list[dict[str, Any]]:
    """Describe every DB-backed composed CV variant, newest first."""
    variants: list[dict[str, Any]] = []
    store = _document_store()
    for document in store.list_variants():
        if not document.name:
            continue
        safe = _safe_name(document.name)
        if not safe:
            continue
        variant_dir = VARIANTS_DIR / safe
        data_yaml = variant_dir / "data.yaml"
        pdf_path = variant_dir / f"{safe}.pdf"
        variants.append(
            {
                "name": document.name,
                "data_yaml": _variant_file_url(data_yaml),
                "pdf": _variant_file_url(pdf_path),
                "updated_at": document.updated_at,
            }
        )
    variants.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return variants


@app.get("/api/variants")
def api_list_variants() -> Any:
    """List DB-backed composed CV variants."""
    return jsonify(_list_variants())


@app.delete("/api/variants/<name>")
def api_delete_variant_folder(name: str) -> Any:
    """Delete a DB-backed composed variant and any leftover export files."""
    safe = _safe_name(name)
    if not safe:
        return jsonify(error="invalid variant name"), 400
    store = _document_store()
    try:
        store.delete_variant(safe)
    except KeyError:
        return jsonify(error="not found"), 404
    target = (VARIANTS_DIR / safe).resolve()
    variants_root = VARIANTS_DIR.resolve()
    try:
        target.relative_to(variants_root)
    except ValueError:
        return jsonify(error="invalid path"), 400
    if target.is_dir():
        shutil.rmtree(target)
    return jsonify(ok=True)


@app.post("/api/variants/<name>/render")
def api_render_variant(name: str) -> Any:
    """Render a composed variant PDF from its DB-backed YAML."""
    safe = _safe_name(name)
    if not safe:
        return jsonify(error="invalid variant name"), 400
    store = _document_store()
    document = store.get_variant(safe)
    if document is None:
        return jsonify(error="not found"), 404
    data = _VARIANT_YAML.load(document.content_yaml) or {}
    if not isinstance(data, dict):
        return jsonify(error="invalid variant YAML"), 400
    pdf_path = VARIANTS_DIR / safe / f"{safe}.pdf"
    try:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        cvweb.export_pdf(pdf_path, data=data)
    except (OSError, RuntimeError, SystemExit) as exc:
        return jsonify(error=str(exc)), 500
    return jsonify(
        ok=True,
        pdf=_variant_file_url(pdf_path) or _relative_export_path(pdf_path),
    )


@app.get("/cv/variants/<path:filename>")
def serve_variant_export(filename: str) -> Any:
    """Serve composed variant export files from the data volume."""
    return send_from_directory(VARIANTS_DIR, filename)


@app.get("/cv/web/")
@app.get("/cv/web")
@app.get("/cv/web/<path:rest>")
def legacy_cv_web_redirect(rest: str = "") -> Any:
    """Redirect former ``/cv/web/...`` URLs to the top-level studio paths."""
    target = f"/{rest}" if rest else "/"
    return redirect(target, code=301)


@app.get("/assets/images/<path:filename>")
def serve_user_image(filename: str) -> Any:
    """Serve a user-uploaded image from the persistent data volume."""
    return send_from_directory(ASSETS_DIR, filename)


@app.get("/assets/branding/<path:filename>")
def serve_branding_asset(filename: str) -> Any:
    """Serve built-in branding assets shipped with the application image."""
    return send_from_directory(ASSETS_BRANDING_DIR, filename)


@app.get("/<path:subpath>")
def serve_repo_file(subpath: str) -> Any:
    """Serve UI assets from ``cv/web/``, then other repo-relative files."""
    web_candidate = cvweb.WEB_DIR / subpath
    if web_candidate.is_file():
        return send_from_directory(cvweb.WEB_DIR, subpath)
    return send_from_directory(cvweb.REPO_ROOT, subpath)


def _resolve_host_port(argv: list[str]) -> tuple[str, int]:
    """Resolve bind host/port from env and optional CLI port argument."""
    host = os.environ.get("EDITOR_HOST", "127.0.0.1")
    if len(argv) > 1:
        port = int(argv[1])
    else:
        port = int(os.environ.get("EDITOR_PORT", "5057"))
    return host, port


if __name__ == "__main__":
    bind_host, bind_port = _resolve_host_port(sys.argv)
    print(
        f"Editor running at http://127.0.0.1:{bind_port}/edit  "
        f"(builder: /build, variants: /variants)  "
        f"(Ctrl-C to stop)"
    )
    if bind_host != "127.0.0.1":
        print(
            f"WARNING: binding to {bind_host} — ensure this is only reachable "
            "locally (e.g. Docker publishing 127.0.0.1:5057)."
        )
    app.run(host=bind_host, port=bind_port, debug=False)
