#!/usr/bin/env python3
"""Local editor for the HTML/CSS CV: edit text in the browser, then render
a real PDF on demand to preview it.

Also exposes the SQLite snippet library, custom-CV builder, drafts,
job-posting matching, and variant manager endpoints.

Usage: python3 scripts/serve-editor.py [port]
Then open http://127.0.0.1:<port>/cv/web/edit
     or http://127.0.0.1:<port>/cv/web/build
     or http://127.0.0.1:<port>/cv/web/variants

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
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cvweb
from cvbuilder.composer import CvComposer
from cvbuilder.database import SnippetDatabase
from cvbuilder.importer import SnippetImporter
from cvbuilder.matcher import SnippetMatcher
from cvbuilder.models import DetailLevel, Snippet, SnippetVariant

from flask import Flask, jsonify, request, send_from_directory
from ruamel.yaml import YAML

app = Flask(__name__, static_folder=None)

PREVIEW_PDF = cvweb.REPO_ROOT / "cv" / "current" / "cv.pdf"
DEFAULT_DB = cvweb.REPO_ROOT / "data" / "snippets.db"
VARIANTS_DIR = cvweb.REPO_ROOT / "cv" / "variants"
ASSETS_DIR = cvweb.REPO_ROOT / "assets" / "images"
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


@app.get("/cv/web/edit")
def edit_page() -> str:
    """Serve the in-place CV editor page."""
    return cvweb.render_html(edit_mode=True)


@app.get("/cv/web/build")
def build_page() -> str:
    """Serve the custom-CV snippet builder page."""
    return (cvweb.WEB_DIR / "builder.html").read_text(encoding="utf-8")


@app.get("/cv/web/variants")
def variants_page() -> str:
    """Serve the composed-variant manager page."""
    return (cvweb.WEB_DIR / "variants.html").read_text(encoding="utf-8")


@app.get("/cv/web/docs")
def docs_page() -> str:
    """Serve README.md as a plain readable page — the "how to use" link."""
    from markupsafe import escape

    readme = (cvweb.REPO_ROOT / "README.md").read_text(encoding="utf-8")
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>CV Builder — How to use</title>"
        "<link rel=\"stylesheet\" href=\"/cv/web/builder.css\"></head>"
        "<body class=\"builder\">"
        "<header class=\"builder-header\"><div><h1>How to use</h1>"
        "<p class=\"subtitle\">README.md</p></div>"
        "<nav class=\"builder-nav\">"
        "<a href=\"/cv/web/edit\">Editor</a>"
        "<a href=\"/cv/web/build\">Builder</a>"
        "<a href=\"/cv/web/variants\">Variants</a>"
        "</nav></header>"
        "<pre style=\"white-space:pre-wrap;max-width:860px;margin:0 auto;"
        f"padding:1.5rem 1rem 3rem;line-height:1.5;\">{escape(readme)}</pre>"
        "</body></html>"
    )


def _history() -> cvweb.EditHistory:
    """Return the edit-history store for the active data.yaml."""
    return cvweb.edit_history()


@app.post("/api/save")
def api_save() -> Any:
    """Persist in-place editor edits back to data.yaml."""
    edits = request.get_json(force=True)
    if not isinstance(edits, list):
        return jsonify(error="edits must be a list"), 400
    if edits:
        before = cvweb.read_data_text()
        data = cvweb.load_data()
        for item in edits:
            cvweb.set_leaf(data, item["path"], item["value"])
        after = cvweb.dump_data_text(data)
        if after != before:
            _history().push_before_change("save", text=before)
            cvweb.write_data_text(after)
    return jsonify(ok=True, **_history().status())


@app.post("/api/structure")
def api_structure() -> Any:
    """Apply a structural insert/delete/move operation to data.yaml."""
    payload = request.get_json(force=True) or {}
    op = str(payload.get("op", "")).strip()
    path = str(payload.get("path", "")).strip()
    allowed_ops = {"insert", "delete", "move", "replace", "replace-subsection"}
    if op not in allowed_ops:
        return jsonify(error="op must be one of: " + ", ".join(sorted(allowed_ops))), 400
    if not path:
        return jsonify(error="path is required"), 400
    before = cvweb.read_data_text()
    data = cvweb.load_data()
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
        _history().push_before_change(op, text=before)
        cvweb.write_data_text(after)
    return jsonify(ok=True, reload=True, **_history().status())


@app.get("/api/history")
def api_history() -> Any:
    """Return whether undo/redo are available."""
    return jsonify(_history().status())


@app.post("/api/undo")
def api_undo() -> Any:
    """Restore the previous data.yaml snapshot and reload the editor."""
    try:
        result = _history().undo()
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(ok=True, reload=True, **result)


@app.post("/api/redo")
def api_redo() -> Any:
    """Re-apply the most recently undone data.yaml snapshot."""
    try:
        result = _history().redo()
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(ok=True, reload=True, **result)


@app.post("/api/export")
def api_export() -> Any:
    """Render the current data.yaml to the preview PDF."""
    cvweb.export_pdf(PREVIEW_PDF)
    return jsonify(ok=True)


@app.get("/api/preview.pdf")
def api_preview_pdf() -> Any:
    """Serve the preview PDF, generating it first if missing."""
    if not PREVIEW_PDF.exists():
        cvweb.export_pdf(PREVIEW_PDF)
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
    """Create or update a named draft selection."""
    payload = request.get_json(force=True) or {}
    selections = payload.get("selections") or []
    if not isinstance(selections, list):
        return jsonify(error="selections must be a list"), 400
    database = _database()
    try:
        draft = database.save_draft(name, selections)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(draft.to_dict())


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
    """Compose selected snippet variants into a named CV variant and PDF."""
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
        result = composer.compose(name=name, selections=selections)
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


def _image_entry(path: Path) -> dict[str, Any]:
    """Describe one image file for the picker UI."""
    return {
        "name": path.name,
        "web_path": "/" + str(path.relative_to(cvweb.REPO_ROOT)),
        # Path relative to cv/web/, the form data.yaml expects for person.photo.
        "data_path": "../../" + str(path.relative_to(cvweb.REPO_ROOT)),
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


@app.get("/api/variants")
def api_list_variants() -> Any:
    """List composed CV variants under cv/variants/."""
    variants: list[dict[str, Any]] = []
    if VARIANTS_DIR.is_dir():
        for path in sorted(VARIANTS_DIR.iterdir()):
            if not path.is_dir():
                continue
            data_yaml = path / "data.yaml"
            if not data_yaml.is_file():
                continue
            pdfs = sorted(path.glob("*.pdf"))
            pdf_path: Optional[Path] = pdfs[0] if pdfs else None
            mtime = datetime.fromtimestamp(
                data_yaml.stat().st_mtime, tz=timezone.utc
            ).isoformat()
            variants.append(
                {
                    "name": path.name,
                    "data_yaml": str(data_yaml.relative_to(cvweb.REPO_ROOT)),
                    "pdf": (
                        str(pdf_path.relative_to(cvweb.REPO_ROOT))
                        if pdf_path
                        else None
                    ),
                    "updated_at": mtime,
                }
            )
    return jsonify(variants)


@app.delete("/api/variants/<name>")
def api_delete_variant_folder(name: str) -> Any:
    """Delete a composed variant directory."""
    safe = _safe_name(name)
    if not safe:
        return jsonify(error="invalid variant name"), 400
    target = (VARIANTS_DIR / safe).resolve()
    variants_root = VARIANTS_DIR.resolve()
    try:
        target.relative_to(variants_root)
    except ValueError:
        return jsonify(error="invalid path"), 400
    if not target.is_dir():
        return jsonify(error="not found"), 404
    shutil.rmtree(target)
    return jsonify(ok=True)


@app.post("/api/variants/<name>/render")
def api_render_variant(name: str) -> Any:
    """Re-render a composed variant's PDF from its data.yaml."""
    safe = _safe_name(name)
    if not safe:
        return jsonify(error="invalid variant name"), 400
    data_path = VARIANTS_DIR / safe / "data.yaml"
    if not data_path.is_file():
        return jsonify(error="not found"), 404
    with data_path.open(encoding="utf-8") as handle:
        document = _VARIANT_YAML.load(handle) or {}
    if not isinstance(document, dict):
        return jsonify(error="invalid data.yaml"), 400
    pdf_path = VARIANTS_DIR / safe / f"{safe}.pdf"
    try:
        cvweb.export_pdf(pdf_path, data=document)
    except (OSError, RuntimeError, SystemExit) as exc:
        return jsonify(error=str(exc)), 500
    return jsonify(
        ok=True,
        pdf=str(pdf_path.relative_to(cvweb.REPO_ROOT)),
    )


@app.get("/<path:subpath>")
def serve_repo_file(subpath: str) -> Any:
    """Serve any repo-relative file for local asset resolution."""
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
        f"Editor running at http://127.0.0.1:{bind_port}/cv/web/edit  "
        f"(builder: /cv/web/build, variants: /cv/web/variants)  "
        f"(Ctrl-C to stop)"
    )
    if bind_host != "127.0.0.1":
        print(
            f"WARNING: binding to {bind_host} — ensure this is only reachable "
            "locally (e.g. Docker publishing 127.0.0.1:5057)."
        )
    app.run(host=bind_host, port=bind_port, debug=False)
