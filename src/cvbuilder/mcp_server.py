"""MCP server exposing the snippet library and CV composer as LLM tools.

Lets an MCP client (Claude Desktop, Claude Code, etc.) search/edit the
snippet library, match a job posting against it, and compose a tailored CV
variant — the same operations the browser builder at ``/cv/web/build``
performs, via ``cvbuilder`` directly rather than the Flask HTTP API.

By default this runs over stdio (``python3 scripts/mcp-server.py``), for
MCP clients that spawn it as a local subprocess — Claude Code, Claude
Desktop, etc. Set ``MCP_TRANSPORT=streamable-http`` (plus optionally
``MCP_HOST`` / ``MCP_PORT``) to instead serve it over HTTP — used when
this runs inside the Docker container, so a remote MCP client can point
at it directly. See README.md for client configuration either way.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from cvbuilder.composer import CvComposer
from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.importer import SnippetImporter
from cvbuilder.matcher import SnippetMatcher
from cvbuilder.models import Snippet, SnippetVariant

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "snippets.db"

MCP_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")
MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.environ.get("MCP_PORT", "8765"))

mcp = FastMCP(
    name="cv-builder",
    instructions=(
        "Tools for tailoring a CV. Snippets are reusable CV "
        "content units (category: bio/skill/experience/education/part/"
        "requirement, "
        "each with brief/standard/detailed variants). Typical flow: "
        "match_job_posting with the posting text to find relevant "
        "snippets, list/inspect/create snippets to fill gaps, then "
        "compose_cv with an ordered list of {snippet_id, detail_level, "
        "section} selections to store a tailored DB-backed variant."
    ),
    # Only consulted for streamable-http/sse transport; harmless for stdio.
    host=MCP_HOST,
    port=MCP_PORT,
)


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
    store.bootstrap_from_filesystem(REPO_ROOT)
    return store


def _parse_tags(raw: Any) -> list[str]:
    """Normalise tags from a list or comma-separated string."""
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


@mcp.tool()
def list_snippets(
    category: Optional[str] = None,
    tag: Optional[str] = None,
    detail_level: Optional[str] = None,
    search: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List CV snippets, optionally filtered.

    Args:
        category: Exact category match (e.g. "bio", "skill", "experience",
            "education", "part", "requirement").
        tag: Require this tag (case-insensitive).
        detail_level: Only include snippets that have this variant
            ("brief", "standard", or "detailed").
        search: Case-insensitive substring match against heading, company,
            role, and variant content.
    """
    snippets = _database().list_snippets(
        category=category, tag=tag, detail_level=detail_level, search=search
    )
    return [snippet.to_dict() for snippet in snippets]


@mcp.tool()
def get_snippet(snippet_id: int) -> dict[str, Any]:
    """Fetch one snippet by id, including all of its detail-level variants.

    Args:
        snippet_id: Primary key of the snippet.
    """
    snippet = _database().get_snippet(snippet_id)
    if snippet is None:
        raise ValueError(f"snippet {snippet_id} not found")
    return snippet.to_dict()


@mcp.tool()
def create_snippet(
    category: str,
    content: str,
    detail_level: str = "standard",
    company: Optional[str] = None,
    role: Optional[str] = None,
    heading: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Create a new snippet with one initial content variant.

    Use this to add new CV material (e.g. a bullet point tailored to a
    posting) that doesn't already exist in the library. Add further detail
    levels afterwards with ``add_snippet_variant``.

    Args:
        category: "bio", "skill", "experience", "education", "part", or
            "requirement".
        content: The variant text (bullets as "- " prefixed lines, or
            prose paragraphs).
        detail_level: Level for the initial variant ("brief", "standard",
            or "detailed").
        company: Employer name, for experience snippets.
        role: Job title (experience) or skill kind ("technical" vs
            "functional" — matched by substring) for skill snippets.
        heading: Subsection heading, for experience snippets.
        tags: Keywords used for job-posting matching.
    """
    database = _database()
    snippet_id = database.create_snippet(
        Snippet(
            category=category,
            company=company,
            role=role,
            heading=heading,
            tags=_parse_tags(tags),
        )
    )
    database.upsert_variant(
        SnippetVariant(
            snippet_id=snippet_id,
            detail_level=detail_level,
            content=content,
        )
    )
    snippet = database.get_snippet(snippet_id)
    assert snippet is not None
    return snippet.to_dict()


@mcp.tool()
def update_snippet(
    snippet_id: int,
    category: Optional[str] = None,
    company: Optional[str] = None,
    role: Optional[str] = None,
    heading: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Update a snippet's metadata (not its variant content).

    Omitted fields keep their current value. Use ``add_snippet_variant`` to
    change content.

    Args:
        snippet_id: Primary key of the snippet to update.
        category: New category, if changing it.
        company: New company, if changing it.
        role: New role, if changing it.
        heading: New heading, if changing it.
        tags: New tag list (replaces the existing tags), if changing it.
    """
    database = _database()
    existing = database.get_snippet(snippet_id)
    if existing is None:
        raise ValueError(f"snippet {snippet_id} not found")
    existing.category = category if category is not None else existing.category
    existing.company = company if company is not None else existing.company
    existing.role = role if role is not None else existing.role
    existing.heading = heading if heading is not None else existing.heading
    if tags is not None:
        existing.tags = _parse_tags(tags)
    database.update_snippet(existing)
    updated = database.get_snippet(snippet_id)
    assert updated is not None
    return updated.to_dict()


@mcp.tool()
def add_snippet_variant(snippet_id: int, detail_level: str, content: str) -> dict[str, Any]:
    """Add or replace a detail-level variant on an existing snippet.

    Args:
        snippet_id: Primary key of the parent snippet.
        detail_level: "brief", "standard", or "detailed".
        content: The variant text.
    """
    database = _database()
    if database.get_snippet(snippet_id) is None:
        raise ValueError(f"snippet {snippet_id} not found")
    database.upsert_variant(
        SnippetVariant(snippet_id=snippet_id, detail_level=detail_level, content=content)
    )
    snippet = database.get_snippet(snippet_id)
    assert snippet is not None
    return snippet.to_dict()


@mcp.tool()
def delete_snippet(snippet_id: int) -> bool:
    """Delete a snippet and all of its variants.

    Args:
        snippet_id: Primary key of the snippet to delete.
    """
    return _database().delete_snippet(snippet_id)


@mcp.tool()
def delete_snippet_variant(snippet_id: int, detail_level: str) -> bool:
    """Delete one detail-level variant from a snippet, leaving others intact.

    Args:
        snippet_id: Primary key of the parent snippet.
        detail_level: "brief", "standard", or "detailed".
    """
    return _database().delete_variant(snippet_id, detail_level)


@mcp.tool()
def match_job_posting(
    text: str, limit: int = 15, category: Optional[str] = None
) -> list[dict[str, Any]]:
    """Rank snippets by keyword overlap against a job posting or requirement.

    Use this first when tailoring a CV to a specific posting — it surfaces
    which existing snippets are most relevant, so you know what to include
    in ``compose_cv`` and where content gaps exist that ``create_snippet``
    should fill.

    Args:
        text: Job posting or requirement text to match against.
        limit: Maximum number of ranked results to return.
        category: Optional category filter (e.g. only "experience").
    """
    results = SnippetMatcher(_database()).match(text, limit=limit, category=category)
    return [result.to_dict() for result in results]


@mcp.tool()
def compose_cv(
    name: str,
    selections: list[dict[str, Any]],
    render_pdf: bool = False,
    export_yaml: bool = False,
) -> dict[str, Any]:
    """Compose a named CV variant from an ordered list of snippet selections.

    Stores a DB-backed variant document. Re-running with the same ``name``
    overwrites the previous variant. Set ``export_yaml`` to also write
    ``cv/variants/<name>/data.yaml``; set ``render_pdf`` to also export a PDF.

    Args:
        name: Variant folder name under ``cv/variants/`` (sanitised
            automatically).
        selections: Ordered list of ``{"snippet_id": int,
            "detail_level": "brief"|"standard"|"detailed",
            "section": str (optional, defaults to the snippet's category)}``.
            Order controls the order content appears in the composed CV.
        render_pdf: When true, also export a PDF.
        export_yaml: When true, also export ``data.yaml``.
    """
    composer = CvComposer(_database(), REPO_ROOT)
    return composer.compose(
        name,
        selections,
        render_pdf=render_pdf,
        export_yaml=export_yaml,
    )


@mcp.tool()
def list_variants() -> list[dict[str, Any]]:
    """List DB-backed composed CV variants with any exported files."""
    results: list[dict[str, Any]] = []
    variants_dir = REPO_ROOT / "cv" / "variants"
    for document in _document_store().list_variants():
        if not document.name:
            continue
        variant_dir = variants_dir / document.name
        files = (
            sorted(p.name for p in variant_dir.iterdir() if p.is_file())
            if variant_dir.is_dir()
            else []
        )
        results.append(
            {
                "name": document.name,
                "files": files,
                "updated_at": document.updated_at,
            }
        )
    return results


@mcp.tool()
def list_drafts() -> list[dict[str, Any]]:
    """List saved builder drafts (named, ordered snippet selections)."""
    return [draft.to_dict() for draft in _database().list_drafts()]


@mcp.tool()
def get_draft(name: str) -> dict[str, Any]:
    """Fetch one saved draft by name.

    Args:
        name: Draft name.
    """
    draft = _database().get_draft(name)
    if draft is None:
        raise ValueError(f"draft {name!r} not found")
    return draft.to_dict()


@mcp.tool()
def save_draft(name: str, selections: list[dict[str, Any]]) -> dict[str, Any]:
    """Save (or overwrite) a named draft of ordered snippet selections.

    Args:
        name: Unique draft name.
        selections: Ordered list of selection dicts, same shape as
            ``compose_cv``'s ``selections`` argument.
    """
    return _database().save_draft(name, selections).to_dict()


@mcp.tool()
def delete_draft(name: str) -> bool:
    """Delete a saved draft.

    Args:
        name: Draft name.
    """
    return _database().delete_draft(name)


@mcp.tool()
def reseed_snippets() -> dict[str, int]:
    """Re-import snippets from ``cv/web/data.yaml`` and ``content/**/*.md``.

    Run this after editing those source files directly, so manually-added
    content becomes available as snippets. Idempotent — safe to re-run.
    """
    return SnippetImporter(_database(), REPO_ROOT).seed()


def main() -> None:
    """Entry point: run the MCP server on the configured transport."""
    mcp.run(transport=MCP_TRANSPORT)


if __name__ == "__main__":
    main()
