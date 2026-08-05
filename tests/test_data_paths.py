"""Tests for CV_DATA_ROOT path resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cvbuilder.paths import DataPaths

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch


class TestDataPaths:
    """Verify mutable paths resolve under CV_DATA_ROOT when set."""

    def test_defaults_to_repo_layout_without_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unset CV_DATA_ROOT keeps today's repo-relative layout."""
        monkeypatch.delenv("CV_DATA_ROOT", raising=False)
        monkeypatch.delenv("SNIPPETS_DB", raising=False)
        monkeypatch.delenv("RESUME_IMPORTS_DIR", raising=False)
        monkeypatch.delenv("ASSETS_IMAGES_DIR", raising=False)
        monkeypatch.delenv("VARIANTS_DIR", raising=False)
        monkeypatch.delenv("PREVIEW_PDF", raising=False)
        repo = tmp_path / "repo"
        repo.mkdir()
        paths = DataPaths(repo)
        assert paths.root == repo.resolve()
        assert paths.snippets_db == (repo / "data" / "snippets.db").resolve()
        assert paths.assets_images == (repo / "assets" / "images").resolve()
        assert paths.imports == (repo / "data" / "imports").resolve()
        assert paths.variants == (repo / "cv" / "variants").resolve()
        assert paths.preview_pdf == (repo / "cv" / "current" / "cv.pdf").resolve()
        assert paths.assets_branding == (repo / "assets" / "branding").resolve()

    def test_data_root_layout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CV_DATA_ROOT moves mutable content under /data-style layout."""
        repo = tmp_path / "app"
        data = tmp_path / "data"
        repo.mkdir()
        data.mkdir()
        monkeypatch.setenv("CV_DATA_ROOT", str(data))
        monkeypatch.delenv("SNIPPETS_DB", raising=False)
        monkeypatch.delenv("RESUME_IMPORTS_DIR", raising=False)
        monkeypatch.delenv("ASSETS_IMAGES_DIR", raising=False)
        monkeypatch.delenv("VARIANTS_DIR", raising=False)
        monkeypatch.delenv("PREVIEW_PDF", raising=False)
        paths = DataPaths(repo)
        assert paths.root == data.resolve()
        assert paths.snippets_db == data / "snippets.db"
        assert paths.assets_images == data / "assets" / "images"
        assert paths.imports == data / "imports"
        assert paths.variants == data / "cv" / "variants"
        assert paths.preview_pdf == data / "cv" / "current" / "cv.pdf"
        assert paths.assets_branding == (repo / "assets" / "branding").resolve()

    def test_ensure_directories_creates_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ensure_directories creates the expected folders."""
        repo = tmp_path / "app"
        data = tmp_path / "data"
        repo.mkdir()
        monkeypatch.setenv("CV_DATA_ROOT", str(data))
        monkeypatch.delenv("SNIPPETS_DB", raising=False)
        paths = DataPaths(repo)
        paths.ensure_directories()
        assert paths.assets_images.is_dir()
        assert (paths.imports / "staging").is_dir()
        assert paths.variants.is_dir()
        assert paths.preview_pdf.parent.is_dir()
        assert paths.snippets_db.parent.is_dir()

    def test_env_overrides_win(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Explicit SNIPPETS_DB / RESUME_IMPORTS_DIR override data-root defaults."""
        repo = tmp_path / "app"
        data = tmp_path / "data"
        custom_db = tmp_path / "custom.db"
        custom_imports = tmp_path / "imports-here"
        repo.mkdir()
        data.mkdir()
        monkeypatch.setenv("CV_DATA_ROOT", str(data))
        monkeypatch.setenv("SNIPPETS_DB", str(custom_db))
        monkeypatch.setenv("RESUME_IMPORTS_DIR", str(custom_imports))
        paths = DataPaths(repo)
        assert paths.snippets_db == custom_db
        assert paths.imports == custom_imports
