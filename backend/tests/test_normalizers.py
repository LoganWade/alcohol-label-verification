"""Unit tests for the normalization helpers."""

from __future__ import annotations

import pytest

from app.services.validation.normalizers import (
    collapse_whitespace,
    normalize_for_comparison,
    normalize_punctuation,
)


class TestNormalizePunctuation:
    def test_curly_quotes_become_straight(self):
        assert normalize_punctuation("\u2018hello\u2019") == "'hello'"
        assert normalize_punctuation("\u201Chello\u201D") == '"hello"'

    def test_unicode_dashes_become_hyphen(self):
        assert normalize_punctuation("a\u2014b") == "a-b"
        assert normalize_punctuation("a\u2013b") == "a-b"

    def test_ascii_passes_through(self):
        assert normalize_punctuation("plain text") == "plain text"


class TestCollapseWhitespace:
    def test_trims_and_collapses(self):
        assert collapse_whitespace("  hello   world  ") == "hello world"

    def test_handles_tabs_and_newlines(self):
        assert collapse_whitespace("hello\t\nworld") == "hello world"


class TestNormalizeForComparison:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("Stone's Throw", "stone's throw"),
            ("STONE'S THROW", "stone's throw"),
            ("  stone's   throw ", "stone's throw"),
            ("Stone\u2019s Throw", "stone's throw"),  # curly apostrophe
            ("Old Tom \u2014 Distillery", "old tom - distillery"),
            ("", ""),
        ],
    )
    def test_canonicalizes(self, value, expected):
        assert normalize_for_comparison(value) == expected

    def test_idempotent(self):
        once = normalize_for_comparison("Stone's Throw")
        twice = normalize_for_comparison(once)
        assert once == twice
