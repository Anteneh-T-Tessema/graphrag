"""
graphrag/models.py
──────────────────
Typed data models shared across all pipeline stages.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field
import uuid


class TextChunk(BaseModel):
    """A single chunk of source text."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str                    # filename or document title
    text: str
    token_count: int = 0
    chunk_index: int = 0


class Entity(BaseModel):
    """A named entity extracted from text."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    type: str                      # PERSON | ORG | CONCEPT | PLACE | EVENT | OTHER
    description: str = ""
    source_chunk_id: str = ""


class Relationship(BaseModel):
    """A directed relationship between two entities."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_entity: str             # Entity.name
    target_entity: str             # Entity.name
    relation: str                  # e.g. "acquired", "founded", "works_at"
    description: str = ""
    weight: float = 1.0            # co-occurrence / confidence score
    source_chunk_id: str = ""


class Community(BaseModel):
    """A cluster of strongly related entities."""
    id: int
    entity_names: List[str]
    summary: str = ""
    level: int = 0                 # hierarchy level (Leiden supports multi-level)


class ExtractionResult(BaseModel):
    """Output of the extraction stage for a single chunk."""
    chunk_id: str
    entities: List[Entity] = []
    relationships: List[Relationship] = []
