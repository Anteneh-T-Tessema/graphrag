"""
tests/test_graph_builder.py
────────────────────────────
Unit tests for KnowledgeGraph — no LLM calls required.
"""

import pytest
from graphrag.graph_builder import KnowledgeGraph
from graphrag.models import Entity, Relationship, ExtractionResult


def _make_result(entities, relationships):
    return ExtractionResult(
        chunk_id="test-chunk",
        entities=entities,
        relationships=relationships,
    )


def test_add_entities_creates_nodes():
    kg = KnowledgeGraph()
    result = _make_result(
        entities=[
            Entity(name="OpenAI", type="ORG", description="AI company"),
            Entity(name="Sam Altman", type="PERSON", description="CEO"),
        ],
        relationships=[],
    )
    kg.add_extraction_results([result])
    assert "OpenAI" in kg.G.nodes
    assert "Sam Altman" in kg.G.nodes


def test_add_relationships_creates_edges():
    kg = KnowledgeGraph()
    result = _make_result(
        entities=[
            Entity(name="OpenAI", type="ORG", description=""),
            Entity(name="Sam Altman", type="PERSON", description=""),
        ],
        relationships=[
            Relationship(
                source_entity="Sam Altman",
                target_entity="OpenAI",
                relation="leads",
                description="Sam Altman is CEO",
                weight=1.0,
            )
        ],
    )
    kg.add_extraction_results([result])
    assert kg.G.has_edge("Sam Altman", "OpenAI")


def test_community_detection_label_propagation():
    """Test with label propagation (no external deps)."""
    kg = KnowledgeGraph()
    # Build a small graph manually
    for name, typ in [
        ("OpenAI", "ORG"), ("Sam Altman", "PERSON"),
        ("Anthropic", "ORG"), ("Dario Amodei", "PERSON"),
    ]:
        result = _make_result(
            entities=[Entity(name=name, type=typ, description="")],
            relationships=[],
        )
        kg.add_extraction_results([result])

    # Add edges
    for src, tgt in [("Sam Altman", "OpenAI"), ("Dario Amodei", "Anthropic")]:
        kg.G.add_edge(src, tgt, weight=1.0, relation="leads", description="")

    communities = kg.detect_communities(algorithm="label_propagation")
    assert len(communities) > 0
    all_names = [n for c in communities for n in c.entity_names]
    assert "OpenAI" in all_names


def test_entity_context_retrieval():
    kg = KnowledgeGraph()
    result = _make_result(
        entities=[
            Entity(name="A", type="ORG", description=""),
            Entity(name="B", type="ORG", description=""),
            Entity(name="C", type="ORG", description=""),
        ],
        relationships=[
            Relationship(source_entity="A", target_entity="B", relation="linked", weight=1.0),
            Relationship(source_entity="B", target_entity="C", relation="linked", weight=1.0),
        ],
    )
    kg.add_extraction_results([result])
    entities, rels = kg.get_entity_context("A", hop=2)
    entity_names = [e.name for e in entities]
    assert "A" in entity_names
    assert "B" in entity_names
