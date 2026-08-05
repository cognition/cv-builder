"""Resolve persistent data directories for CV Studio.

When ``CV_DATA_ROOT`` is set (Docker defaults to ``/data``), mutable
user content — the SQLite database, uploaded images, resume imports,
variant export files, and preview artefacts — lives under that root.
When unset, paths fall back to the repository root so local non-Docker
runs keep today's layout.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class DataPaths:
    """Locate writable Studio paths under a configurable data root."""

    def __init__(
        self,
        repo_root: Path,
        data_root: Optional[Path] = None,
    ) -> None:
        """Initialise path resolution.

        Args:
            repo_root: Application / repository root (seed content, branding).
            data_root: Mutable data root. Defaults to ``CV_DATA_ROOT`` env or
                ``repo_root`` when the env var is unset.
        """
        self.repo_root = Path(repo_root).resolve()
        if data_root is not None:
            self._data_root = Path(data_root).resolve()
        else:
            env_root = os.environ.get("CV_DATA_ROOT", "").strip()
            self._data_root = (
                Path(env_root).resolve() if env_root else self.repo_root
            )

    @property
    def root(self) -> Path:
        """Return the mutable data root directory."""
        return self._data_root

    @property
    def snippets_db(self) -> Path:
        """Return the SQLite database path."""
        env_db = os.environ.get("SNIPPETS_DB", "").strip()
        if env_db:
            return Path(env_db)
        return self.root / "snippets.db" if self.root != self.repo_root else (
            self.repo_root / "data" / "snippets.db"
        )

    @property
    def assets_images(self) -> Path:
        """Return the user-uploaded images directory."""
        env_dir = os.environ.get("ASSETS_IMAGES_DIR", "").strip()
        if env_dir:
            return Path(env_dir)
        if self.root != self.repo_root:
            return self.root / "assets" / "images"
        return self.repo_root / "assets" / "images"

    @property
    def assets_branding(self) -> Path:
        """Return the built-in branding assets directory (always under repo)."""
        return self.repo_root / "assets" / "branding"

    @property
    def imports(self) -> Path:
        """Return the resume-imports directory."""
        env_dir = os.environ.get("RESUME_IMPORTS_DIR", "").strip()
        if env_dir:
            return Path(env_dir)
        if self.root != self.repo_root:
            return self.root / "imports"
        return self.repo_root / "data" / "imports"

    @property
    def variants(self) -> Path:
        """Return the composed-variant export directory."""
        env_dir = os.environ.get("VARIANTS_DIR", "").strip()
        if env_dir:
            return Path(env_dir)
        if self.root != self.repo_root:
            return self.root / "cv" / "variants"
        return self.repo_root / "cv" / "variants"

    @property
    def preview_pdf(self) -> Path:
        """Return the disposable Master CV preview PDF path."""
        env_path = os.environ.get("PREVIEW_PDF", "").strip()
        if env_path:
            return Path(env_path)
        if self.root != self.repo_root:
            return self.root / "cv" / "current" / "cv.pdf"
        return self.repo_root / "cv" / "current" / "cv.pdf"

    def ensure_directories(self) -> None:
        """Create the standard mutable data directories if missing."""
        for path in (
            self.assets_images,
            self.imports / "staging",
            self.variants,
            self.preview_pdf.parent,
            self.snippets_db.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)
