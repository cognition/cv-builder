"""First-boot preparation of the SQLite store for Docker / volume starts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from cvbuilder.database import SnippetDatabase
from cvbuilder.importer import SnippetImporter


class FirstBoot:
    """Prepare the SQLite store on container / volume first boot."""

    @staticmethod
    def prepare_database(
        db_path: Path,
        repo_root: Path,
        *,
        demo: bool,
    ) -> dict[str, Any]:
        """Create schema; optionally seed demo snippets.

        Args:
            db_path: Path to ``snippets.db``.
            repo_root: Repository root containing ``cv/web/data.yaml``
                and ``content/``.
            demo: When True, run ``SnippetImporter.seed()``. When False,
                create schema only (no snippets).

        Returns:
            ``{"demo": bool, "snippet_total": int, "stats": dict}``.
            ``stats`` is empty when ``demo`` is False.
        """
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        database = SnippetDatabase(db_path)
        if not demo:
            database.ensure_schema()
            return {"demo": False, "snippet_total": 0, "stats": {}}

        importer = SnippetImporter(database=database, repo_root=Path(repo_root))
        stats = importer.seed()
        return {
            "demo": True,
            "snippet_total": sum(stats.values()),
            "stats": stats,
        }


class FirstBootCli:
    """Command-line adapter for Docker first-boot database preparation."""

    @staticmethod
    def run() -> int:
        """Prepare the database using environment-driven container settings."""
        db_path = Path(os.environ["SNIPPETS_DB"])
        repo_root = Path(os.environ.get("REPO_ROOT", "/app"))
        demo = os.environ.get("DEMO") == "1"
        result = FirstBoot.prepare_database(db_path, repo_root, demo=demo)
        if demo:
            print(f"Seeded {result['snippet_total']} demo snippets into {db_path}")
            return 0
        print(f"Created blank database at {db_path}")
        return 0


if __name__ == "__main__":
    raise SystemExit(FirstBootCli.run())
