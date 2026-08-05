"""Flask API tests for drafts, match, variants, and variant deletion."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator

import pytest

from cvbuilder.database import SnippetDatabase
from cvbuilder.models import DetailLevel, Snippet, SnippetVariant

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture
    from _pytest.fixtures import FixtureRequest
    from _pytest.logging import LogCaptureFixture
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture
    from flask.testing import FlaskClient


@pytest.fixture
def api_app(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, repo_fixture: Path
) -> Generator[Any, None, None]:
    """Load serve-editor with an isolated DB and variants directory.

    Args:
        tmp_path: Temporary directory for the DB.
        monkeypatch: Pytest monkeypatch fixture.
        repo_fixture: Minimal repository tree.

    Yields:
        The Flask application module namespace.
    """
    db_path = tmp_path / "api.db"
    monkeypatch.setenv("SNIPPETS_DB", str(db_path))

    # Point cvweb.REPO_ROOT / WEB_DIR / variants at the fixture tree.
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    src = Path(__file__).resolve().parents[1] / "src"
    monkeypatch.syspath_prepend(str(scripts))
    monkeypatch.syspath_prepend(str(src))

    import cvweb

    monkeypatch.setattr(cvweb, "REPO_ROOT", repo_fixture)
    monkeypatch.setattr(cvweb, "WEB_DIR", repo_fixture / "cv" / "web")
    monkeypatch.setattr(cvweb, "DATA_FILE", repo_fixture / "cv" / "web" / "data.yaml")

    # Provide minimal builder/variants HTML for page routes.
    (repo_fixture / "cv" / "web" / "builder.html").write_text(
        "<html>builder</html>", encoding="utf-8"
    )
    (repo_fixture / "cv" / "web" / "variants.html").write_text(
        "<html>variants</html>", encoding="utf-8"
    )
    (repo_fixture / "cv" / "variants").mkdir(parents=True, exist_ok=True)

    # Ensure a clean import of serve-editor under the patched paths.
    sys.modules.pop("serve-editor", None)
    ns = runpy.run_path(str(scripts / "serve-editor.py"))
    monkeypatch.setattr(ns["cvweb"], "REPO_ROOT", repo_fixture)
    monkeypatch.setattr(
        ns["cvweb"], "WEB_DIR", repo_fixture / "cv" / "web"
    )
    monkeypatch.setattr(
        ns["cvweb"], "DATA_FILE", repo_fixture / "cv" / "web" / "data.yaml"
    )
    # Patch route globals so variants/assets paths resolve inside the fixture tree.
    for func_name in (
        "api_list_variants",
        "api_delete_variant_folder",
        "api_render_variant",
        "api_list_images",
        "api_upload_image",
        "api_fetch_image",
        "api_upload_import",
    ):
        func = ns[func_name]
        func.__globals__["VARIANTS_DIR"] = repo_fixture / "cv" / "variants"
        func.__globals__["ASSETS_DIR"] = repo_fixture / "assets" / "images"
        func.__globals__["IMPORTS_DIR"] = repo_fixture / "data" / "imports"
        func.__globals__["STAGING_DIR"] = repo_fixture / "data" / "imports" / "staging"
        func.__globals__["cvweb"] = ns["cvweb"]

    database = SnippetDatabase(db_path)
    database.ensure_schema()
    sid = database.create_snippet(
        Snippet(
            category="skill",
            heading="Python",
            tags=["python"],
        )
    )
    database.upsert_variant(
        SnippetVariant(
            snippet_id=sid,
            detail_level=DetailLevel.STANDARD.value,
            content="Python development",
        )
    )
    yield ns


@pytest.fixture
def client(api_app: dict[str, Any]) -> "FlaskClient":
    """Return a Flask test client for the loaded app."""
    app = api_app["app"]
    app.config["TESTING"] = True
    return app.test_client()


class TestApiEndpoints:
    """Exercise the new Flask endpoints with a test client."""

    def test_drafts_round_trip(self, client: "FlaskClient") -> None:
        """PUT/GET/DELETE drafts should succeed."""
        put = client.put(
            "/api/drafts/demo",
            json={"selections": [{"snippet_id": 1, "detail_level": "standard"}]},
        )
        assert put.status_code == 200
        assert put.get_json()["name"] == "demo"
        get = client.get("/api/drafts/demo")
        assert get.status_code == 200
        listed = client.get("/api/drafts")
        assert any(item["name"] == "demo" for item in listed.get_json())
        deleted = client.delete("/api/drafts/demo")
        assert deleted.status_code == 200
        missing = client.get("/api/drafts/demo")
        assert missing.status_code == 404

    def test_match_endpoint(self, client: "FlaskClient") -> None:
        """POST /api/match should return ranked hits for known terms."""
        resp = client.post("/api/match", json={"text": "Need strong Python skills"})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body
        assert body[0]["snippet_id"]
        assert "python" in body[0]["matched_terms"]

    def test_delete_variant_level(self, client: "FlaskClient") -> None:
        """DELETE /api/snippets/<id>/variants/<level> should remove one level."""
        created = client.post(
            "/api/snippets",
            json={
                "category": "part",
                "heading": "Temp",
                "variants": {
                    "brief": "short",
                    "standard": "normal",
                },
            },
        )
        assert created.status_code == 201
        snippet_id = created.get_json()["id"]
        deleted = client.delete(f"/api/snippets/{snippet_id}/variants/brief")
        assert deleted.status_code == 200
        fetched = client.get(f"/api/snippets/{snippet_id}")
        levels = {v["detail_level"] for v in fetched.get_json()["variants"]}
        assert "brief" not in levels
        assert "standard" in levels

    def test_structure_replace_text(
        self, client: "FlaskClient", api_app: dict[str, Any]
    ) -> None:
        """POST /api/structure op=replace should overwrite a leaf value."""
        resp = client.post(
            "/api/structure",
            json={"op": "replace", "path": "bio[0]", "value": "Replacement bio."},
        )
        assert resp.status_code == 200
        data = api_app["cvweb"].load_data()
        assert str(data["bio"][0]).strip() == "Replacement bio."

    def test_structure_replace_subsection(
        self, client: "FlaskClient", api_app: dict[str, Any]
    ) -> None:
        """op=replace-subsection should rebuild heading/paragraphs/bullets."""
        resp = client.post(
            "/api/structure",
            json={
                "op": "replace-subsection",
                "path": "experience[0].subsections[0]",
                "heading": "Swapped Heading",
                "content": "Intro paragraph text.\n\n- First bullet\n- Second bullet",
            },
        )
        assert resp.status_code == 200
        data = api_app["cvweb"].load_data()
        sub = data["experience"][0]["subsections"][0]
        assert sub["heading"] == "Swapped Heading"
        assert list(sub["bullets"]) == ["First bullet", "Second bullet"]
        assert list(sub["paragraphs"]) == ["Intro paragraph text."]

    def test_structure_replace_requires_value(
        self, client: "FlaskClient"
    ) -> None:
        """op=replace without a usable value should fail with 400."""
        resp = client.post(
            "/api/structure",
            json={"op": "replace", "path": "bio[0]", "value": "  "},
        )
        assert resp.status_code == 400

    def test_structure_then_undo_redo(
        self, client: "FlaskClient", api_app: dict[str, Any]
    ) -> None:
        """Structural changes should be reversible via /api/undo and /api/redo."""
        before = api_app["cvweb"].read_data_text()
        inserted = client.post(
            "/api/structure",
            json={"op": "insert", "path": "bio", "value": "Undo me"},
        )
        assert inserted.status_code == 200
        assert inserted.get_json()["can_undo"] is True

        status = client.get("/api/history")
        assert status.status_code == 200
        assert status.get_json()["can_undo"] is True

        undone = client.post("/api/undo")
        assert undone.status_code == 200
        assert api_app["cvweb"].read_data_text() == before
        assert undone.get_json()["can_redo"] is True

        redone = client.post("/api/redo")
        assert redone.status_code == 200
        data = api_app["cvweb"].load_data()
        assert "Undo me" in [str(part).strip() for part in data["bio"]]

    def test_empty_save_skips_history(self, client: "FlaskClient") -> None:
        """An empty save payload should not create an undo entry."""
        resp = client.post("/api/save", json=[])
        assert resp.status_code == 200
        assert resp.get_json()["can_undo"] is False

    def test_variants_list_and_delete(
        self, client: "FlaskClient", repo_fixture: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Variant list/delete should operate on cv/variants folders."""
        variant_dir = repo_fixture / "cv" / "variants" / "sample"
        variant_dir.mkdir(parents=True, exist_ok=True)
        (variant_dir / "data.yaml").write_text("person: {}\n", encoding="utf-8")
        (variant_dir / "sample.pdf").write_bytes(b"%PDF-1.4")

        listed = client.get("/api/variants")
        assert listed.status_code == 200
        names = {item["name"] for item in listed.get_json()}
        assert "sample" in names

        deleted = client.delete("/api/variants/sample")
        assert deleted.status_code == 200
        assert not variant_dir.exists()

    def test_image_upload_and_list(
        self, client: "FlaskClient", repo_fixture: Path
    ) -> None:
        """Uploading an image should store it and list it afterwards."""
        from io import BytesIO

        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        )
        upload = client.post(
            "/api/images/upload",
            data={"file": (BytesIO(png_bytes), "test icon.png")},
            content_type="multipart/form-data",
        )
        assert upload.status_code == 201
        body = upload.get_json()
        assert body["name"].endswith(".png")
        assert body["data_path"].startswith("../../assets/images/")
        stored = repo_fixture / "assets" / "images" / body["name"]
        assert stored.is_file()

        listed = client.get("/api/images")
        assert listed.status_code == 200
        names = {item["name"] for item in listed.get_json()}
        assert body["name"] in names

    def test_image_upload_rejects_bad_type(self, client: "FlaskClient") -> None:
        """Non-image extensions should be rejected."""
        from io import BytesIO

        upload = client.post(
            "/api/images/upload",
            data={"file": (BytesIO(b"hello"), "notes.txt")},
            content_type="multipart/form-data",
        )
        assert upload.status_code == 400

    def test_image_fetch_rejects_bad_scheme(self, client: "FlaskClient") -> None:
        """Only http(s) URLs should be accepted for image grabs."""
        resp = client.post(
            "/api/images/fetch", json={"url": "file:///etc/passwd"}
        )
        assert resp.status_code == 400
        missing = client.post("/api/images/fetch", json={})
        assert missing.status_code == 400


class TestQuestionApiEndpoints:
    """Exercise the application-questions endpoints end-to-end."""

    def test_create_source_extracts_questions(self, client: "FlaskClient") -> None:
        """Creating a source with pasted text should extract questions."""
        created = client.post(
            "/api/question-sources",
            json={
                "title": "Government screening",
                "source_type": "form",
                "text": "Do you have a valid work permit?\nAre you willing to relocate?",
            },
        )
        assert created.status_code == 201
        body = created.get_json()
        assert body["question_count"] == 2
        source_id = body["id"]

        listed_sources = client.get("/api/question-sources")
        assert any(s["id"] == source_id for s in listed_sources.get_json())

        listed_questions = client.get(f"/api/questions?source_id={source_id}")
        prompts = {q["prompt"] for q in listed_questions.get_json()}
        assert prompts == {
            "Do you have a valid work permit?",
            "Are you willing to relocate?",
        }
        assert all(q["status"] == "needs_evidence" for q in listed_questions.get_json())

    def test_create_source_rejects_bad_type(self, client: "FlaskClient") -> None:
        """An unknown source_type should be rejected."""
        resp = client.post(
            "/api/question-sources", json={"title": "x", "source_type": "essay"}
        )
        assert resp.status_code == 400

    def test_answer_evidence_and_suggest_round_trip(
        self, client: "FlaskClient"
    ) -> None:
        """Save an answer, link evidence, then re-suggest from that evidence."""
        source = client.post(
            "/api/question-sources", json={"title": "Leadership", "source_type": "matrix"}
        ).get_json()
        question = client.post(
            "/api/question-sources", json={"title": "x2", "source_type": "matrix", "text": "Python fluency"}
        ).get_json()
        question_id = client.get(f"/api/questions?source_id={question['id']}").get_json()[0]["id"]

        # Fixture seeds a "Python" skill snippet — find its id.
        snippet_id = next(
            s["id"] for s in client.get("/api/snippets").get_json() if s["heading"] == "Python"
        )

        linked = client.post(
            f"/api/questions/{question_id}/evidence", json={"snippet_id": snippet_id}
        )
        assert linked.status_code == 201
        assert linked.get_json()["evidence"][0]["snippet_id"] == snippet_id

        after_link = client.get(f"/api/questions/{question_id}").get_json()
        assert after_link["status"] == "in_progress"

        suggested = client.post(f"/api/questions/{question_id}/suggest")
        assert suggested.status_code == 200
        assert "Python development" in suggested.get_json()["answer"]

        saved = client.put(
            f"/api/questions/{question_id}", json={"answer": "I know Python well."}
        )
        assert saved.status_code == 200
        assert saved.get_json()["status"] == "complete"

        unlinked = client.delete(f"/api/questions/{question_id}/evidence/{snippet_id}")
        assert unlinked.status_code == 200

        deleted = client.delete(f"/api/questions/{question_id}")
        assert deleted.status_code == 200
        assert client.get(f"/api/questions/{question_id}").status_code == 404

        assert client.delete(f"/api/question-sources/{source['id']}").status_code == 200

    def test_suggest_with_no_evidence_ranks_against_prompt(
        self, client: "FlaskClient"
    ) -> None:
        """With no linked evidence yet, /suggest should match against the prompt."""
        source = client.post(
            "/api/question-sources",
            json={"title": "Skills check", "source_type": "form", "text": "Python experience?"},
        ).get_json()
        question_id = client.get(f"/api/questions?source_id={source['id']}").get_json()[0]["id"]
        suggested = client.post(f"/api/questions/{question_id}/suggest")
        assert suggested.status_code == 200
        assert suggested.get_json()["evidence"]
        assert "Python development" in suggested.get_json()["answer"]


SAMPLE_RESUME_TEXT = """Homer Simpson

Summary
Platform leader with a decade of experience building resilient cloud systems.

Experience
Staff Platform Engineer — Acme Corp (2021 - Present)
- Led migration of 40+ services to Kubernetes
- Built the on-call incident response program

Skills
Kubernetes, Terraform, AWS

Education
BSc Computer Science, State University, 2013
"""


class TestResumeImportApiEndpoints:
    """Exercise the resume-import upload/review/confirm endpoints."""

    def test_upload_and_confirm_round_trip(self, client: "FlaskClient") -> None:
        from io import BytesIO

        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        assert uploaded.status_code == 201
        body = uploaded.get_json()
        assert body["file_type"] == "txt"
        assert body["counts"]["experience"] == 1
        assert body["counts"]["skills"] == 3
        assert len(body["candidates"]) == sum(body["counts"].values())
        token = body["token"]

        confirmed = client.post(f"/api/imports/{token}/confirm", json={})
        assert confirmed.status_code == 200
        confirmed_body = confirmed.get_json()
        assert confirmed_body["snippet_count"] == len(body["candidates"])

        listed = client.get("/api/imports")
        assert listed.status_code == 200
        records = listed.get_json()
        assert len(records) == 1
        assert records[0]["filename"] == "resume.txt"
        assert records[0]["snippet_count"] == confirmed_body["snippet_count"]
        import_id = records[0]["id"]

        library = client.get("/api/snippets?tag=import")
        assert len(library.get_json()) == confirmed_body["snippet_count"]

        downloaded = client.get(f"/api/imports/{import_id}/source")
        assert downloaded.status_code == 200
        assert downloaded.data == SAMPLE_RESUME_TEXT.encode()

        deleted = client.delete(f"/api/imports/{import_id}")
        assert deleted.status_code == 200
        assert client.get("/api/imports").get_json() == []

    def test_upload_rejects_unsupported_extension(self, client: "FlaskClient") -> None:
        from io import BytesIO

        resp = client.post(
            "/api/imports",
            data={"file": (BytesIO(b"whatever"), "resume.exe")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400

    def test_confirm_respects_disabled_sections(self, client: "FlaskClient") -> None:
        from io import BytesIO

        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        token = uploaded.get_json()["token"]

        confirmed = client.post(
            f"/api/imports/{token}/confirm",
            json={
                "sections": {
                    "profile": False,
                    "experience": False,
                    "skills": True,
                    "education": False,
                }
            },
        )
        assert confirmed.status_code == 200
        assert confirmed.get_json()["snippet_count"] == 3

        skills = client.get("/api/snippets?category=skill&tag=import")
        assert len(skills.get_json()) == 3

    def test_confirm_master_mode_updates_yaml_and_preserves_person(
        self, client: "FlaskClient"
    ) -> None:
        from io import BytesIO

        import cvweb

        before = cvweb.load_data()
        original_first = before["person"]["first_name"]

        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        token = uploaded.get_json()["token"]
        confirmed = client.post(
            f"/api/imports/{token}/confirm",
            json={"mode": "master"},
        )
        assert confirmed.status_code == 200
        body = confirmed.get_json()
        assert body["mode"] == "master"
        assert body["master_updated"] is True
        assert body["snippet_count"] > 0
        assert body["backup_path"].startswith("data/backups/data.yaml.")
        assert (cvweb.REPO_ROOT / body["backup_path"]).is_file()

        after = cvweb.load_data()
        assert after["person"]["first_name"] == original_first
        assert after["bio"]  # non-empty from SAMPLE_RESUME_TEXT summary
        assert after["experience"]
        assert after["experience"][0]["company"] or after["experience"][0]["role"]
        skills = client.get("/api/snippets?tag=import")
        assert len(skills.get_json()) == body["snippet_count"]

    def test_confirm_invalid_mode_returns_400(self, client: "FlaskClient") -> None:
        from io import BytesIO

        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        token = uploaded.get_json()["token"]
        resp = client.post(
            f"/api/imports/{token}/confirm",
            json={"mode": "compare"},
        )
        assert resp.status_code == 400

    def test_confirm_library_mode_default_does_not_touch_master(
        self, client: "FlaskClient"
    ) -> None:
        from io import BytesIO

        import cvweb

        before_text = cvweb.read_data_text()
        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        token = uploaded.get_json()["token"]
        confirmed = client.post(
            f"/api/imports/{token}/confirm",
            json={},
        )
        assert confirmed.status_code == 200
        body = confirmed.get_json()
        assert body["mode"] == "library"
        assert body["master_updated"] is False
        assert cvweb.read_data_text() == before_text

    def test_backup_master_yaml_uses_unique_paths(
        self, api_app: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Backups created in the same second should never overwrite each other."""
        from datetime import datetime, timezone

        import cvweb

        class FrozenDatetime:
            """Provide a stable timestamp for backup collision testing."""

            @classmethod
            def now(cls, tz: object) -> datetime:
                """Return the same UTC timestamp for every backup call."""
                return datetime(2026, 8, 4, 17, 0, 0, tzinfo=timezone.utc)

        monkeypatch.setitem(
            api_app["_backup_master_yaml"].__globals__, "datetime", FrozenDatetime
        )

        first = api_app["_backup_master_yaml"]()
        second = api_app["_backup_master_yaml"]()

        assert first != second
        assert (cvweb.REPO_ROOT / first).is_file()
        assert (cvweb.REPO_ROOT / second).is_file()

    def test_confirm_master_backup_failure_preserves_yaml(
        self,
        client: "FlaskClient",
        api_app: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A backup failure should stop master import before data.yaml changes."""
        from io import BytesIO

        import cvweb

        def fail_backup() -> Path:
            """Raise the same error shape as a failed filesystem backup."""
            raise OSError("backup unavailable")

        before_text = cvweb.read_data_text()
        monkeypatch.setitem(
            api_app["api_confirm_import"].__globals__, "_backup_master_yaml", fail_backup
        )
        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        token = uploaded.get_json()["token"]

        confirmed = client.post(
            f"/api/imports/{token}/confirm",
            json={"mode": "master"},
        )

        assert confirmed.status_code == 500
        assert "backup unavailable" in confirmed.get_json()["error"]
        assert cvweb.read_data_text() == before_text

    def test_duplicate_candidates_are_flagged(self, client: "FlaskClient") -> None:
        from io import BytesIO

        from cvbuilder.resume_extractor import content_hash

        client.post(
            "/api/snippets",
            json={
                "category": "skill",
                "heading": "Kubernetes",
                "content_hash": content_hash("Kubernetes"),
                "content": "Kubernetes",
                "detail_level": "standard",
            },
        )

        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        candidates = uploaded.get_json()["candidates"]
        kubernetes = next(c for c in candidates if c["heading"] == "Kubernetes")
        terraform = next(c for c in candidates if c["heading"] == "Terraform")
        assert kubernetes["duplicate"] is True
        assert terraform["duplicate"] is False

    def test_upload_real_docx_through_multipart_endpoint(
        self, client: "FlaskClient"
    ) -> None:
        """A real (non-text) binary file should round-trip through the upload route."""
        from io import BytesIO

        from docx import Document

        document = Document()
        document.add_paragraph("Homer Simpson")
        document.add_paragraph("")
        document.add_paragraph("Skills")
        document.add_paragraph("Kubernetes, Terraform")
        buf = BytesIO()
        document.save(buf)
        buf.seek(0)

        uploaded = client.post(
            "/api/imports",
            data={"file": (buf, "resume.docx")},
            content_type="multipart/form-data",
        )
        assert uploaded.status_code == 201
        body = uploaded.get_json()
        assert body["file_type"] == "docx"
        assert body["counts"]["skills"] == 2

        confirmed = client.post(f"/api/imports/{body['token']}/confirm", json={})
        assert confirmed.status_code == 200
        assert confirmed.get_json()["snippet_count"] == body["counts"]["skills"] + sum(
            v for k, v in body["counts"].items() if k != "skills"
        )

        record = client.get("/api/imports").get_json()[0]
        assert record["file_type"] == "docx"
        downloaded = client.get(f"/api/imports/{record['id']}/source")
        assert downloaded.status_code == 200
        assert downloaded.data[:2] == b"PK"  # docx is a zip container

    def test_confirm_unknown_token_returns_404(self, client: "FlaskClient") -> None:
        resp = client.post("/api/imports/0011223344556677/confirm", json={})
        assert resp.status_code == 404

    def test_discard_staged_import(self, client: "FlaskClient") -> None:
        from io import BytesIO

        uploaded = client.post(
            "/api/imports",
            data={"file": (BytesIO(SAMPLE_RESUME_TEXT.encode()), "resume.txt")},
            content_type="multipart/form-data",
        )
        token = uploaded.get_json()["token"]

        discarded = client.delete(f"/api/imports/staging/{token}")
        assert discarded.status_code == 200

        confirmed = client.post(f"/api/imports/{token}/confirm", json={})
        assert confirmed.status_code == 404
