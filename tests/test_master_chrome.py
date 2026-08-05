"""Regression checks for Master CV page chrome staying under the shell."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MASTER_CSS = REPO_ROOT / "cv" / "web" / "src" / "pages" / "master.css"


class TestMasterPreviewChrome:
    """Ensure Save & Preview never paints over the Studio aside."""

    def test_preview_pane_rules_outrank_legacy_fixed_drawer(self) -> None:
        """Master CSS must fully reset the legacy fixed 42vw preview pane."""
        css = MASTER_CSS.read_text(encoding="utf-8")
        assert ".master-workspace #preview-pane" in css
        assert "position: absolute" in css
        assert "width: auto" in css
        assert "overflow-x: hidden" in css
        assert "overflow-y: auto" in css
        assert ".master-workspace #preview-pane {" in css
        rule = css.split(".master-workspace #preview-pane {", 1)[1].split("}", 1)[0]
        assert "position: absolute" in rule
        assert "42vw" not in css
        assert (REPO_ROOT / "cv" / "web" / "src" / "preview-pane.js").is_file()


class TestShellChromeScroll:
    """Ensure the Studio aside and header stay fixed while content scrolls."""

    def test_shell_locks_viewport_and_scrolls_main_content(self) -> None:
        """Shell CSS must pin chrome and scroll only main content."""
        css = (REPO_ROOT / "cv" / "web" / "src" / "shell" / "shell.css").read_text(
            encoding="utf-8"
        )
        assert "overflow: hidden" in css
        assert "main > :not(header):not(#preview-pane)" in css
        assert ".shell > aside" in css
        assert "max-height: 100vh" in css
