"""
tests/test_chunker.py
──────────────────────
Unit tests for the chunker — no LLM calls required.
Run: pytest tests/test_chunker.py -v
"""

import pytest
from graphrag.chunker import chunk_text, chunk_file
from pathlib import Path

SAMPLE_TEXT = """
OpenAI was founded in 2015 by Sam Altman and Elon Musk.
They wanted to ensure AI benefits humanity.

Microsoft invested heavily in OpenAI in 2023.
The partnership gave Microsoft access to GPT technology.

Anthropic was founded by Dario Amodei and Daniela Amodei.
They left OpenAI to start a safety-focused AI company.
"""


def test_chunk_text_returns_chunks():
    chunks = chunk_text(SAMPLE_TEXT, source="test.txt", chunk_size=100, chunk_overlap=10)
    assert len(chunks) > 0
    for c in chunks:
        assert c.text.strip()
        assert c.source == "test.txt"
        assert c.token_count > 0


def test_chunk_overlap_does_not_crash():
    # Very small chunk size to force many chunks
    chunks = chunk_text(SAMPLE_TEXT, source="test.txt", chunk_size=30, chunk_overlap=5)
    assert len(chunks) > 1


def test_chunk_file(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text(SAMPLE_TEXT)
    chunks = chunk_file(test_file, chunk_size=200)
    assert len(chunks) > 0
    assert chunks[0].source == "test.txt"


def test_chunk_indices_sequential():
    chunks = chunk_text(SAMPLE_TEXT, source="x.txt", chunk_size=80, chunk_overlap=10)
    for i, c in enumerate(chunks):
        assert c.chunk_index == i
