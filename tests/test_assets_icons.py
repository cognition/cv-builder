"""Regression checks for built-in Assets contact icons."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_JS = REPO_ROOT / "cv" / "web" / "src" / "pages" / "assets.js"


class TestAssetsBrandIcons:
    """Ensure GitHub and GitLab use real SVG marks on the Assets page."""

    def test_github_and_gitlab_use_inline_svg_marks(self) -> None:
        """Built-in icons must embed SVG path data, not letter placeholders."""
        source = ASSETS_JS.read_text(encoding="utf-8")
        assert 'cls: "github"' in source
        assert 'cls: "gitlab"' in source
        assert "<svg" in source
        assert 'viewBox="0 0 24 24"' in source
        # GitHub mark path fragment and GitLab tanuki-style path fragment.
        assert "M12 2C6.477 2 2 6.484" in source
        assert "M23.955 13.209" in source
        assert 'glyph: "GH"' not in source
        assert "&#9670;" not in source
