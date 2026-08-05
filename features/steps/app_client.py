"""Helpers for exercising the real Flask app in Behave steps."""

from __future__ import annotations

from typing import Any, Optional

from bs4 import BeautifulSoup
from behave.runner import Context

# Map product names → real routes in serve-editor.py
PAGE_ROUTES = {
    "home": "/cv/web/",
    "master": "/cv/web/edit",
    "master cv": "/cv/web/edit",
    "edit": "/cv/web/edit",
    "personal details": "/cv/web/details",
    "details": "/cv/web/details",
    "tailor": "/cv/web/build",
    "build": "/cv/web/build",
    "questions": "/cv/web/questions",
    "application questions": "/cv/web/questions",
    "content library": "/cv/web/library",
    "library": "/cv/web/library",
    "assets": "/cv/web/assets",
    "asset library": "/cv/web/assets",
    "versions": "/cv/web/variants",
    "cv versions": "/cv/web/variants",
    "connect ai": "/cv/web/connect",
    "connect": "/cv/web/connect",
    "docs": "/cv/web/docs",
    "import resume": "/cv/web/import",
    "import": "/cv/web/import",
}

NAV_ACTIVE = {
    "home": "home",
    "master": "master",
    "master cv": "master",
    "personal details": "details",
    "details": "details",
    "tailor": "tailor",
    "questions": "questions",
    "application questions": "questions",
    "content library": "library",
    "library": "library",
    "assets": "assets",
    "versions": "versions",
    "cv versions": "versions",
    "connect ai": "connect",
    "connect": "connect",
    "import resume": "import",
    "import": "import",
}


def resolve_path(name_or_path: str) -> str:
    """Resolve a page name or raw path to a URL path."""
    key = name_or_path.strip().lower()
    if key.startswith("/"):
        return name_or_path.strip()
    if key not in PAGE_ROUTES:
        raise AssertionError(f"unknown page: {name_or_path!r}")
    return PAGE_ROUTES[key]


def open_page(context: Context, name_or_path: str) -> BeautifulSoup:
    """GET a real page and stash HTML + parsed soup on the context."""
    path = resolve_path(name_or_path)
    response = context.client.get(path)
    context.response = response
    context.page_html = response.get_data(as_text=True)
    context.page = BeautifulSoup(context.page_html, "html.parser")
    context.page_path = path
    return context.page


def api_json(
    context: Context,
    method: str,
    path: str,
    payload: Optional[dict[str, Any]] = None,
) -> Any:
    """Call a JSON API endpoint and return the decoded body."""
    client_method = getattr(context.client, method.lower())
    if payload is None:
        response = client_method(path)
    else:
        response = client_method(path, json=payload)
    context.response = response
    if response.content_type and "json" in response.content_type:
        context.response_json = response.get_json()
    else:
        context.response_json = None
    return context.response_json


def page(context: Context) -> BeautifulSoup:
    """Return the last opened page soup."""
    if context.page is None:
        raise AssertionError("no page open — use 'I open the … page' first")
    return context.page


def nav_labels(soup: BeautifulSoup) -> list[str]:
    """Return shell nav destination labels."""
    labels: list[str] = []
    for link in soup.select("aside nav a.nav-link, aside nav a"):
        span = link.select_one("span")
        labels.append(span.get_text(strip=True) if span else link.get_text(strip=True))
    return labels


def has_text(soup: BeautifulSoup, fragment: str) -> bool:
    """True if the page text contains ``fragment`` (case-insensitive)."""
    return fragment.lower() in soup.get_text(" ", strip=True).lower()


def has_selector(soup: BeautifulSoup, selector: str) -> bool:
    """True if ``selector`` matches at least one element."""
    return soup.select_one(selector) is not None
