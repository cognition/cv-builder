"""Tests for the application-questions database layer and text extractor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cvbuilder.database import SnippetDatabase
from cvbuilder.models import DetailLevel, Question, QuestionSource, Snippet, SnippetVariant
from cvbuilder.question_extractor import extract_questions

if TYPE_CHECKING:
    pass


class TestQuestionSources:
    """Create/list/delete question sources."""

    def test_create_and_list_source(self, snippet_db: SnippetDatabase) -> None:
        source_id = snippet_db.create_question_source(
            QuestionSource(title="Platform Manager", source_type="job")
        )
        sources = snippet_db.list_question_sources()
        assert len(sources) == 1
        assert sources[0].id == source_id
        assert sources[0].title == "Platform Manager"
        assert sources[0].source_type == "job"

    def test_delete_source_cascades_to_questions(
        self, snippet_db: SnippetDatabase
    ) -> None:
        source_id = snippet_db.create_question_source(
            QuestionSource(title="Screening", source_type="form")
        )
        snippet_db.create_question(
            Question(source_id=source_id, prompt="Do you have a valid work permit?")
        )
        assert snippet_db.delete_question_source(source_id) is True
        assert snippet_db.list_questions() == []


class TestQuestionsAndEvidence:
    """Create questions, save answers, link/unlink evidence."""

    def _make_source(self, snippet_db: SnippetDatabase) -> int:
        return snippet_db.create_question_source(
            QuestionSource(title="Leadership competencies", source_type="matrix")
        )

    def test_create_question_requires_source_and_prompt(
        self, snippet_db: SnippetDatabase
    ) -> None:
        try:
            snippet_db.create_question(Question(source_id=None, prompt="x"))
            assert False, "expected ValueError"
        except ValueError:
            pass

    def test_derived_status_transitions(self, snippet_db: SnippetDatabase) -> None:
        source_id = self._make_source(snippet_db)
        snippet_id = snippet_db.create_snippet(
            Snippet(category="experience", heading="Led a platform team")
        )
        snippet_db.upsert_variant(
            SnippetVariant(
                snippet_id=snippet_id,
                detail_level=DetailLevel.STANDARD.value,
                content="Led a cross-functional platform team.",
            )
        )
        question_id = snippet_db.create_question(
            Question(source_id=source_id, prompt="Describe your leadership experience.")
        )
        question = snippet_db.get_question(question_id)
        assert question is not None
        assert question.status == "needs_evidence"

        snippet_db.add_question_evidence(question_id, snippet_id, "standard")
        question = snippet_db.get_question(question_id)
        assert question is not None
        assert question.status == "in_progress"
        assert question.evidence[0].heading == "Led a platform team"

        snippet_db.update_question_answer(question_id, "I led a platform team of six.")
        question = snippet_db.get_question(question_id)
        assert question is not None
        assert question.status == "complete"

        assert snippet_db.remove_question_evidence(question_id, snippet_id) is True
        question = snippet_db.get_question(question_id)
        assert question is not None
        assert question.evidence == []
        # Still complete: an answer alone is enough, evidence isn't required
        # retroactively once written.
        assert question.status == "complete"

    def test_list_questions_scoped_to_source(self, snippet_db: SnippetDatabase) -> None:
        source_a = self._make_source(snippet_db)
        source_b = snippet_db.create_question_source(
            QuestionSource(title="Other source", source_type="form")
        )
        snippet_db.create_question(Question(source_id=source_a, prompt="A1"))
        snippet_db.create_question(Question(source_id=source_b, prompt="B1"))
        assert [q.prompt for q in snippet_db.list_questions(source_id=source_a)] == ["A1"]
        assert len(snippet_db.list_questions()) == 2


class TestQuestionExtractor:
    """Deterministic line/bullet-based question extraction."""

    def test_form_extracts_one_question_per_line(self) -> None:
        text = "Do you have a valid work permit?\n\nAre you willing to relocate?"
        assert extract_questions(text, "form") == [
            "Do you have a valid work permit?",
            "Are you willing to relocate?",
        ]

    def test_matrix_strips_bullet_markers(self) -> None:
        text = "- Stakeholder management\n2. Executive communication"
        assert extract_questions(text, "matrix") == [
            "Stakeholder management",
            "Executive communication",
        ]

    def test_job_posting_reframes_bullets(self) -> None:
        text = (
            "We are looking for a platform engineer.\n"
            "- 5+ years of cloud infrastructure experience\n"
            "- Strong incident response background\n"
        )
        result = extract_questions(text, "job")
        assert result == [
            "Describe your experience with: 5+ years of cloud infrastructure experience",
            "Describe your experience with: Strong incident response background",
        ]

    def test_job_posting_falls_back_to_hint_sentences_without_bullets(self) -> None:
        text = "We need someone with deep experience in distributed systems. The office is in Toronto."
        result = extract_questions(text, "job")
        assert len(result) == 1
        assert "distributed systems" in result[0]

    def test_extraction_deduplicates_and_caps_length(self) -> None:
        text = "\n".join(["Same question?"] * 3)
        assert extract_questions(text, "form") == ["Same question?"]
