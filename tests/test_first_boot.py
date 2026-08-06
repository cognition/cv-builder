"""Unit tests for first-boot blank vs demo database preparation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from cvbuilder.database import SnippetDatabase
from cvbuilder.document_store import DocumentStore
from cvbuilder.first_boot import FirstBoot, FirstBootCli

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.monkeypatch import MonkeyPatch


def _mini_repo(tmp_path: Path) -> Path:
    """Create a tiny repo with Homer-like YAML and one markdown snippet."""
    repo = tmp_path / "repo"
    (repo / "cv" / "web").mkdir(parents=True)
    (repo / "content" / "parts").mkdir(parents=True)
    (repo / "cv" / "web" / "data.yaml").write_text(
        "person:\n  first_name: Homer\nbio:\n  - Safety first.\n"
        "skills:\n  technical: []\n  functional: []\n"
        "experience: []\neducation: []\n",
        encoding="utf-8",
    )
    (repo / "content" / "parts" / "intro.md").write_text(
        "# Intro\n\n## Alternate bio\n\nA longer intro paragraph.\n",
        encoding="utf-8",
    )
    return repo


class TestFirstBoot:
    """Blank vs demo first-boot preparation."""

    def test_blank_creates_schema_with_zero_snippets(
        self, tmp_path: Path
    ) -> None:
        """DEMO-off path creates DB schema and no snippets."""
        repo = _mini_repo(tmp_path)
        db_path = tmp_path / "data" / "snippets.db"
        result = FirstBoot.prepare_database(db_path, repo, demo=False)
        assert result["demo"] is False
        assert result["snippet_total"] == 0
        assert result["stats"] == {}
        assert db_path.is_file()
        database = SnippetDatabase(db_path)
        assert database.list_snippets() == []
        assert DocumentStore(database).get_working() is None

    def test_demo_seeds_snippets_from_yaml(
        self, tmp_path: Path
    ) -> None:
        """DEMO-on path seeds at least the YAML bio snippet."""
        repo = _mini_repo(tmp_path)
        db_path = tmp_path / "data" / "snippets.db"
        result = FirstBoot.prepare_database(db_path, repo, demo=True)
        assert result["demo"] is True
        assert result["snippet_total"] >= 1
        assert isinstance(result["stats"], dict)
        assert result["stats"]
        database = SnippetDatabase(db_path)
        snippets = database.list_snippets()
        assert len(snippets) >= 1

    def test_blank_restart_needs_skip_filesystem_bootstrap(
        self, tmp_path: Path, monkeypatch: MonkeyPatch
    ) -> None:
        """Blank first boot would import YAML on restart without the skip policy."""
        repo = _mini_repo(tmp_path)
        db_path = tmp_path / "data" / "snippets.db"
        FirstBoot.prepare_database(db_path, repo, demo=False)

        monkeypatch.delenv("SKIP_FS_BOOTSTRAP", raising=False)
        store_without_policy = DocumentStore(SnippetDatabase(db_path))
        result_without_policy = store_without_policy.bootstrap_from_filesystem(repo)
        assert result_without_policy["master"] == 1
        master_without_policy = store_without_policy.get_working()
        assert master_without_policy is not None
        assert "Homer" in master_without_policy.content_yaml

        second_db_path = tmp_path / "data" / "snippets-restart.db"
        FirstBoot.prepare_database(second_db_path, repo, demo=False)
        monkeypatch.setenv("SKIP_FS_BOOTSTRAP", "1")
        store_with_policy = DocumentStore(SnippetDatabase(second_db_path))
        result_with_policy = store_with_policy.bootstrap_from_filesystem(repo)
        assert result_with_policy == {"master": 0, "variants": 0, "history": 0}
        assert store_with_policy.get_working() is None

    def test_entrypoint_exports_skip_bootstrap_on_every_blank_start(
        self, tmp_path: Path
    ) -> None:
        """DEMO-off starts export SKIP_FS_BOOTSTRAP even when the DB already exists."""
        repo_root = Path(__file__).resolve().parents[1]
        data_root = tmp_path / "data"
        db_path = data_root / "snippets.db"
        data_root.mkdir()
        db_path.touch()

        environment = os.environ.copy()
        environment.update(
            {
                "CV_DATA_ROOT": str(data_root),
                "ENABLE_MCP": "0",
                "PYTHONPATH": str(repo_root / "src"),
                "SNIPPETS_DB": str(db_path),
            }
        )
        environment.pop("DEMO", None)
        environment.pop("SKIP_FS_BOOTSTRAP", None)

        completed = subprocess.run(
            [
                "sh",
                str(repo_root / "docker-entrypoint.sh"),
                sys.executable,
                "-c",
                "import os; print(os.environ.get('SKIP_FS_BOOTSTRAP', ''))",
            ],
            check=True,
            capture_output=True,
            env=environment,
            text=True,
        )

        assert completed.stdout.strip() == "1"

    def test_cli_reads_database_path_from_environment(
        self,
        tmp_path: Path,
        monkeypatch: MonkeyPatch,
        capsys: CaptureFixture[str],
    ) -> None:
        """The module CLI prepares the env-selected database without shell interpolation."""
        repo = _mini_repo(tmp_path)
        db_path = tmp_path / "data" / "snippets.db"
        monkeypatch.setenv("SNIPPETS_DB", str(db_path))
        monkeypatch.setenv("REPO_ROOT", str(repo))
        monkeypatch.delenv("DEMO", raising=False)

        exit_code = FirstBootCli.run()

        assert exit_code == 0
        assert db_path.is_file()
        assert "Created blank database" in capsys.readouterr().out
