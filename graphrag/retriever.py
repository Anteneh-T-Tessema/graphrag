"""
graphrag/retriever.py
──────────────────────
Phase 2: Local Search & Global Search.

LOCAL SEARCH
  - Find the entity node(s) most relevant to the query
  - Grab their N-hop neighbourhood (entities + relationships)
  - Use that subgraph as context for the LLM answer

GLOBAL SEARCH
  - Gather all pre-computed community summaries
  - Use semantic similarity (embeddings) to rank summaries by relevance
  - Aggregate top-k summaries and synthesise a holistic answer
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import List, Optional

import numpy as np
from openai import AsyncOpenAI, OpenAI
from rich.console import Console
from sentence_transformers import SentenceTransformer

from .graph_builder import KnowledgeGraph
from .models import Community, Entity, Relationship
from .summarizer import CommunitySummarizer
from .config import config

console = Console()


# ─── Embedding Utilities ─────────────────────────────────────────────────────

def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def _embed(texts: List[str], client: OpenAI, model_name: str) -> np.ndarray:
    if config.embedding_provider == "local":
        model = SentenceTransformer(model_name)
        return model.encode(texts)
        
    response = client.embeddings.create(input=texts, model=model_name)
    return np.array([r.embedding for r in response.data])


# ─── Context Formatters ──────────────────────────────────────────────────────

def _format_entity_context(entities: List[Entity], relationships: List[Relationship]) -> str:
    lines = ["=== ENTITIES ==="]
    for e in entities:
        lines.append(f"• {e.name} ({e.type}): {e.description}")
    lines.append("\n=== RELATIONSHIPS ===")
    for r in relationships:
        lines.append(f"• {r.source_entity} --[{r.relation}]--> {r.target_entity}: {r.description}")
    return "\n".join(lines)


def _format_community_context(communities: List[Community]) -> str:
    lines = ["=== COMMUNITY SUMMARIES ==="]
    for i, c in enumerate(communities, 1):
        lines.append(f"\n[Community {i}]\n{c.summary}")
    return "\n".join(lines)


# ─── Answer Generation ────────────────────────────────────────────────────────

LOCAL_SYSTEM = """\
You are a precise knowledge assistant. Use only the provided graph context
to answer the user's question. If the context is insufficient, say so clearly.
Do not speculate beyond the provided information."""

GLOBAL_SYSTEM = """\
You are a strategic analyst. You have been given thematic summaries of
communities of knowledge extracted from a large document corpus.
Synthesize these summaries to provide a comprehensive, insightful answer
to the user's question. Highlight key themes, patterns, and connections."""


class LocalSearch:
    """
    Answers specific entity-level questions by traversing the knowledge graph.
    """

    def __init__(
        self,
        kg: KnowledgeGraph,
        llm_params: dict,
        model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-small",
        hop: int = 2,
    ):
        self.kg = kg
        self.client = OpenAI(**llm_params)
        self.async_client = AsyncOpenAI(**llm_params)
        self.model = model
        self.embedding_model = embedding_model
        self.hop = hop
        self._node_embeddings: Optional[np.ndarray] = None
        self._node_names: Optional[List[str]] = None

    def _build_node_index(self) -> None:
        """Pre-compute embeddings for all entity nodes."""
        if self._node_embeddings is not None:
            return
        names = list(self.kg.entity_map.keys())
        if not names:
            return
        console.print(f"[cyan]LocalSearch[/cyan] Indexing {len(names)} entity nodes...")
        self._node_names = names
        descs = [
            f"{n}: {self.kg.entity_map[n].description}" for n in names
        ]
        self._node_embeddings = _embed(descs, self.client, self.embedding_model)

    def _find_seed_entity(self, query: str) -> Optional[str]:
        """Find the most relevant entity for a query using cosine similarity."""
        self._build_node_index()
        if self._node_names is None or self._node_embeddings is None:
            return None

        q_emb = _embed([query], self.client, self.embedding_model)[0]
        sims = [
            _cosine_similarity(q_emb, self._node_embeddings[i])
            for i in range(len(self._node_names))
        ]
        best_idx = int(np.argmax(sims))
        best_entity = self._node_names[best_idx]
        console.print(
            f"[cyan]LocalSearch[/cyan] Seed entity: [bold]{best_entity}[/bold] "
            f"(similarity: {sims[best_idx]:.3f})"
        )
        return best_entity

    def search(self, query: str) -> str:
        """Run a local (entity-centric) search and return an answer."""
        seed = self._find_seed_entity(query)
        if seed is None:
            return "No entities found in the knowledge graph."

        entities, relationships = self.kg.get_entity_context(seed, hop=self.hop)
        context = _format_entity_context(entities, relationships)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": LOCAL_SYSTEM},
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nQuestion: {query}",
                },
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content.strip()


class GlobalSearch:
    """
    Answers holistic/thematic questions using pre-computed community summaries.
    """

    def __init__(
        self,
        communities: List[Community],
        llm_params: dict,
        model: str = "gpt-4o",
        embedding_model: str = "text-embedding-3-small",
        top_k: int = 10,
    ):
        self.communities = communities
        self.client = OpenAI(**llm_params)
        self.model = model
        self.embedding_model = embedding_model
        self.top_k = top_k
        self._summary_embeddings: Optional[np.ndarray] = None

    def _build_summary_index(self) -> None:
        if self._summary_embeddings is not None:
            return
        summaries = [c.summary for c in self.communities if c.summary]
        if not summaries:
            return
        console.print(
            f"[cyan]GlobalSearch[/cyan] Indexing {len(summaries)} community summaries..."
        )
        self._summary_embeddings = _embed(summaries, self.client, self.embedding_model)

    def _rank_communities(self, query: str) -> List[Community]:
        """Return top-k communities sorted by semantic relevance to query."""
        self._build_summary_index()
        scored = self.communities
        if self._summary_embeddings is not None:
            q_emb = _embed([query], self.client, self.embedding_model)[0]
            sims = [
                _cosine_similarity(q_emb, self._summary_embeddings[i])
                for i in range(len(self.communities))
            ]
            scored = sorted(
                zip(sims, self.communities), key=lambda x: x[0], reverse=True
            )
            scored = [c for _, c in scored]
        return scored[: self.top_k]

    def search(self, query: str) -> str:
        """Run a global (community-level) search and return an answer."""
        top_communities = self._rank_communities(query)
        console.print(
            f"[cyan]GlobalSearch[/cyan] Using top {len(top_communities)} communities"
        )
        context = _format_community_context(top_communities)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": GLOBAL_SYSTEM},
                {
                    "role": "user",
                    "content": f"Community Summaries:\n{context}\n\nQuestion: {query}",
                },
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content.strip()


class GraphRAGRetriever:
    """
    Unified retriever that automatically routes between Local and Global search.

    Routing heuristic:
      • If the query contains a known entity name → LOCAL
      • Otherwise → GLOBAL
    """

    def __init__(
        self,
        kg: KnowledgeGraph,
        communities: List[Community],
        llm_params: dict,
        extraction_model: str = "gpt-4o",
        summarization_model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
    ):
        self.local = LocalSearch(
            kg=kg,
            llm_params=llm_params,
            model=extraction_model,
            embedding_model=embedding_model,
        )
        self.global_ = GlobalSearch(
            communities=communities,
            llm_params=llm_params,
            model=summarization_model,
            embedding_model=embedding_model,
        )
        self.kg = kg

    def _route(self, query: str) -> str:
        """Return 'local' or 'global' based on simple entity-mention heuristic."""
        q_lower = query.lower()
        for name in self.kg.entity_map:
            if name.lower() in q_lower:
                return "local"
        return "global"

    def query(self, question: str, mode: Optional[str] = None) -> dict:
        """
        Answer a question using the appropriate search mode.

        Args:
            question: The user's natural language question.
            mode: Force 'local' | 'global' | None (auto-route).

        Returns:
            dict with 'answer', 'mode', and optionally 'seed_entity'.
        """
        if mode is None:
            mode = self._route(question)

        console.print(f"\n[bold magenta]Query Mode:[/bold magenta] {mode.upper()}")
        console.print(f"[bold]Question:[/bold] {question}\n")

        if mode == "local":
            answer = self.local.search(question)
        else:
            answer = self.global_.search(question)

        return {"question": question, "mode": mode, "answer": answer}
