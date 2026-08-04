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
    ):
        func = ns[func_name]
        func.__globals__["VARIANTS_DIR"] = repo_fixture / "cv" / "variants"
        func.__globals__["ASSETS_DIR"] = repo_fixture / "assets" / "images"
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
