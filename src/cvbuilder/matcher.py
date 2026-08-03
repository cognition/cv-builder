"""Keyword-based matching of job postings to CV snippets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from cvbuilder.database import SnippetDatabase
from cvbuilder.models import Snippet

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+.#/-]{1,}")

# Lightweight English stopword list — enough for posting keyword overlap.
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "our",
        "that",
        "the",
        "their",
        "this",
        "to",
        "was",
        "we",
        "will",
        "with",
        "you",
        "your",
        "job",
        "role",
        "work",
        "working",
        "experience",
        "required",
        "requirements",
        "preferred",
        "ability",
        "able",
        "including",
        "etc",
        "using",
        "use",
        "years",
        "year",
        "team",
        "teams",
        "strong",
        "good",
        "must",
        "should",
        "may",
        "can",
        "also",
        "other",
        "such",
        "than",
        "into",
        "over",
        "all",
        "any",
        "not",
        "new",
        "across",
        "within",
        "about",
        "per",
        "plus",
    }
)

# Weights for overlap sources.
_WEIGHT_TAG = 5.0
_WEIGHT_HEADING = 3.0
_WEIGHT_COMPANY = 2.0
_WEIGHT_CONTENT = 1.0


@dataclass
class MatchResult:
    """A ranked snippet match against a job posting."""

    snippet: Snippet
    score: float
    matched_terms: list[str]

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation."""
        return {
            "snippet": self.snippet.to_dict(),
            "snippet_id": self.snippet.id,
            "score": round(self.score, 3),
            "matched_terms": list(self.matched_terms),
        }


class SnippetMatcher:
    """Score snippets by weighted keyword overlap with a job posting."""

    def __init__(self, database: SnippetDatabase) -> None:
        """Initialise the matcher.

        Args:
            database: Snippet store to search.
        """
        self.database = database

    def match(
        self,
        text: str,
        limit: int = 25,
        category: Optional[str] = None,
    ) -> list[MatchResult]:
        """Rank snippets against the given posting text.

        Args:
            text: Job posting or requirement text.
            limit: Maximum number of results to return.
            category: Optional category filter.

        Returns:
            Ranked match results with positive scores only.
        """
        terms = self.tokenize(text)
        if not terms:
            return []
        snippets = self.database.list_snippets(category=category)
        results: list[MatchResult] = []
        for snippet in snippets:
            score, matched = self._score_snippet(snippet, terms)
            if score > 0:
                results.append(
                    MatchResult(
                        snippet=snippet,
                        score=score,
                        matched_terms=sorted(matched),
                    )
                )
        results.sort(key=lambda item: (-item.score, item.snippet.id or 0))
        return results[: max(1, limit)]

    @classmethod
    def tokenize(cls, text: str) -> set[str]:
        """Tokenise text into lowercase content terms, minus stopwords.

        Args:
            text: Free-form posting text.

        Returns:
            Set of meaningful tokens.
        """
        tokens = set(_TOKEN_RE.findall(text.lower()))
        return {token for token in tokens if token not in _STOPWORDS and len(token) > 1}

    def _score_snippet(
        self, snippet: Snippet, terms: set[str]
    ) -> tuple[float, set[str]]:
        """Compute a weighted overlap score for one snippet."""
        score = 0.0
        matched: set[str] = set()

        tag_terms = self.tokenize(" ".join(snippet.tags))
        heading_terms = self.tokenize(snippet.heading or "")
        company_terms = self.tokenize(
            " ".join(filter(None, [snippet.company, snippet.role]))
        )
        content_bits: list[str] = []
        for variant in snippet.variants:
            content_bits.append(variant.content)
        content_terms = self.tokenize(" ".join(content_bits))

        score += self._accumulate(terms, tag_terms, _WEIGHT_TAG, matched)
        score += self._accumulate(terms, heading_terms, _WEIGHT_HEADING, matched)
        score += self._accumulate(terms, company_terms, _WEIGHT_COMPANY, matched)
        score += self._accumulate(terms, content_terms, _WEIGHT_CONTENT, matched)
        return score, matched

    @staticmethod
    def _accumulate(
        query: set[str],
        field_terms: set[str],
        weight: float,
        matched: set[str],
    ) -> float:
        """Add weighted hits for overlapping terms into ``matched``."""
        hits = query & field_terms
        if not hits:
            return 0.0
        matched.update(hits)
        return weight * float(len(hits))
