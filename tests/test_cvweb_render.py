"""Tests for CV web template rendering helpers."""

from __future__ import annotations

import cvweb


class TestCvwebRendering:
    """Exercise standalone and partial CV rendering."""

    def test_render_cv_body_returns_partial_without_page_chrome(self) -> None:
        """The body helper should omit document and editor toolbar chrome."""
        html = cvweb.render_cv_body(edit_mode=True)

        assert '<div class="hero">' in html
        assert 'contenteditable="true"' in html
        assert "<!doctype html>" not in html
        assert "<body" not in html
        assert "editor-toolbar" not in html
        assert "preview-pane" not in html
        assert "editor.js" not in html

    def test_render_html_wraps_body_for_print_export(self) -> None:
        """Standalone rendering should stay export-ready and chrome-free."""
        html = cvweb.render_html(edit_mode=False)

        assert "<!doctype html>" in html
        assert '<div class="cv-document">' in html
        assert '<div class="hero">' in html
        assert "shell" not in html
        assert "CV Studio" not in html
        assert 'class="nav-link' not in html
        assert "editor-toolbar" not in html
