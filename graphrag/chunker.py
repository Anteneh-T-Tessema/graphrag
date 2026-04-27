"""
graphrag/chunker.py
────────────────────
Phase 1 – Step 1: Break source documents into token-aware text chunks.

Supports:
  • Plain .txt files
  • .md files
  • Arbitrary strings (for in-memory use)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import tiktoken
import pypdf
from rich.console import Console

from .models import TextChunk

console = Console()


def _get_encoder(model: str = "gpt-4o") -> tiktoken.Encoding:
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def _count_tokens(text: str, encoder: tiktoken.Encoding) -> int:
    return len(encoder.encode(text))


def chunk_text(
    text: str,
    source: str,
    chunk_size: int = 1200,
    chunk_overlap: int = 100,
    model: str = "gpt-4o",
) -> List[TextChunk]:
    """
    Split `text` into overlapping token-aware chunks.

    Strategy:
      1. Split on double-newlines (paragraph boundaries) first.
      2. Greedily pack paragraphs into a chunk until `chunk_size` is reached.
      3. Carry over the last `chunk_overlap` tokens as a sliding window.
    """
    encoder = _get_encoder(model)
    paragraphs = re.split(r"\n{2,}", text.strip())
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks: List[TextChunk] = []
    current_tokens: List[int] = []
    chunk_index = 0

    def flush(tokens: List[int]) -> None:
        nonlocal chunk_index
        chunk_text_str = encoder.decode(tokens)
        chunks.append(
            TextChunk(
                source=source,
                text=chunk_text_str,
                token_count=len(tokens),
                chunk_index=chunk_index,
            )
        )
        chunk_index += 1

    for para in paragraphs:
        para_tokens = encoder.encode(para)

        # If a single paragraph is larger than chunk_size, split it by sentences
        if len(para_tokens) > chunk_size:
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sent in sentences:
                sent_tokens = encoder.encode(sent)
                if len(current_tokens) + len(sent_tokens) > chunk_size:
                    if current_tokens:
                        flush(current_tokens)
                        current_tokens = current_tokens[-chunk_overlap:]
                current_tokens.extend(sent_tokens)
        else:
            if len(current_tokens) + len(para_tokens) > chunk_size:
                if current_tokens:
                    flush(current_tokens)
                    current_tokens = current_tokens[-chunk_overlap:]
            current_tokens.extend(para_tokens)

    if current_tokens:
        flush(current_tokens)

    console.print(
        f"[cyan]Chunker[/cyan] '{source}' → [bold]{len(chunks)}[/bold] chunks"
    )
    return chunks


def chunk_file(
    path: str | Path,
    chunk_size: int = 1200,
    chunk_overlap: int = 100,
) -> List[TextChunk]:
    """Load a file (.txt, .md, .pdf) and chunk it."""
    path = Path(path)
    if path.suffix.lower() == '.pdf':
        text = ""
        reader = pypdf.PdfReader(path)
        for page in reader.pages:
            content = page.extract_text()
            if content:
                text += content + "\n\n"
    else:
        text = path.read_text(encoding="utf-8")
        
    return chunk_text(
        text=text,
        source=path.name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def chunk_directory(
    directory: str | Path,
    extensions: tuple[str, ...] = (".txt", ".md", ".pdf"),
    chunk_size: int = 1200,
    chunk_overlap: int = 100,
) -> List[TextChunk]:
    """Recursively chunk all matching files in a directory."""
    directory = Path(directory)
    all_chunks: List[TextChunk] = []
    files = [f for ext in extensions for f in directory.rglob(f"*{ext}")]
    console.print(f"[cyan]Chunker[/cyan] Found [bold]{len(files)}[/bold] files in '{directory}'")
    for file in files:
        all_chunks.extend(chunk_file(file, chunk_size, chunk_overlap))
    return all_chunks
