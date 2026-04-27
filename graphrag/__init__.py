"""
graphrag/__init__.py
─────────────────────
Public API surface for the graphrag package.
"""

from .chunker import chunk_text, chunk_file, chunk_directory
from .extractor import EntityExtractor
from .graph_builder import KnowledgeGraph
from .summarizer import CommunitySummarizer
from .retriever import GraphRAGRetriever, LocalSearch, GlobalSearch
from .models import TextChunk, Entity, Relationship, Community, ExtractionResult
from .config import GraphRAGConfig, config

__all__ = [
    "chunk_text",
    "chunk_file",
    "chunk_directory",
    "EntityExtractor",
    "KnowledgeGraph",
    "CommunitySummarizer",
    "GraphRAGRetriever",
    "LocalSearch",
    "GlobalSearch",
    "TextChunk",
    "Entity",
    "Relationship",
    "Community",
    "ExtractionResult",
    "GraphRAGConfig",
    "config",
]
