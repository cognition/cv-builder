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
        assert "overflow: hidden" in css
        # Must not reintroduce the legacy viewport-fixed drawer.
        assert "position: fixed" not in css.split(".master-workspace #preview-pane")[1].split(
            ".master-workspace #preview-close"
        )[0]
        assert "42vw" not in css
