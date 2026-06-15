"""Tests for the Telegram char splitter — splits long texts safely."""

import pytest

from channels.telegram.char_splitter import CharSplitter


class TestCharSplitter:
    """Unit tests for CharSplitter — pure logic, no IO."""

    def setup_method(self):
        self.splitter = CharSplitter()

    def test_short_text_single_chunk(self):
        """Text under limit returns single chunk."""
        result = self.splitter.split("Hello, world!")
        assert result == ["Hello, world!"]

    def test_empty_text(self):
        """Empty text returns [\"\"]."""
        result = self.splitter.split("")
        assert result == [""]

    def test_exact_fit(self):
        """Text exactly at limit returns single chunk."""
        text = "A" * 4000
        result = self.splitter.split(text)
        assert result == [text]

    def test_splits_at_word_boundary(self):
        """Long text splits at the last whitespace before the limit."""
        # Create text where the word boundary is before 4000
        chunk1 = "word " * 500  # ~2500 chars of words
        chunk2 = "more " * 500  # ~2500 more
        text = chunk1 + chunk2

        result = self.splitter.split(text, max_chars=1000)
        assert len(result) >= 2
        # Each chunk should be at most 1000 chars (except possibly last)
        for chunk in result[:-1]:
            assert len(chunk) <= 1000

    def test_no_word_boundary_hard_split(self):
        """Text without spaces falls back to hard character split."""
        text = "A" * 5000
        result = self.splitter.split(text, max_chars=1000)
        assert len(result) == 5
        assert all(len(c) <= 1000 for c in result)

    def test_custom_max_chars(self):
        """Custom max_chars overrides default."""
        text = "Hello world foo bar baz"
        result = self.splitter.split(text, max_chars=10)
        assert len(result) >= 2

    def test_newline_preferred_split(self):
        """Newlines are preferred split points."""
        text = ("A" * 100) + "\n" + ("B" * 100)
        result = self.splitter.split(text, max_chars=150)
        assert len(result) == 2
        assert "A" in result[0]
        assert "B" in result[1]

    def test_rstrip_lstrip_chunks(self):
        """Chunks are stripped of leading/trailing whitespace."""
        text = "word " * 500 + "end"
        result = self.splitter.split(text, max_chars=1000)
        for chunk in result:
            if chunk:
                assert chunk == chunk.strip()
