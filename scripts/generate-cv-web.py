#!/usr/bin/env python3
"""Render the DB-backed master CV through cv/web/template.html.j2 and print to PDF.

Usage: scripts/generate-cv-web.py [output-pdf]
  output-pdf   default: cv/current/cv.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import cvweb
from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.paths import DataPaths


class CvWebGenerator:
    """Generate a PDF from the DB-backed master CV document."""

    def __init__(self, repo_root: Path) -> None:
        """Initialise the generator for a repository root."""
        self.repo_root = repo_root
        self.data_paths = DataPaths(repo_root)

    def run(self, argv: list[str]) -> None:
        """Render the requested output PDF from the stored master document."""
        out_pdf = (
            Path(argv[1]).resolve()
            if len(argv) > 1
            else self.data_paths.preview_pdf
        )
        store = self._document_store()
        document = store.get_master()
        if document is None:
            raise LookupError("Master CV document is not available")
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        cvweb.export_pdf(out_pdf, data=document.content_yaml)
        print(f"Generated: {out_pdf}")

    def _document_store(self) -> DocumentStore:
        """Return a bootstrapped document store."""
        db_path = self.data_paths.snippets_db
        db_path.parent.mkdir(parents=True, exist_ok=True)
        database = SnippetDatabase(db_path)
        database.ensure_schema()
        store = DocumentStore(database)
        store.bootstrap_from_filesystem(self.repo_root)
        return store


def main() -> None:
    """Run the command-line PDF generator."""
    CvWebGenerator(cvweb.REPO_ROOT).run(sys.argv)


if __name__ == "__main__":
    main()
