"""
graphrag/graph_builder.py
──────────────────────────
Phase 1 – Steps 3 & 4: Graph Construction + Community Detection.

Builds a NetworkX graph from extraction results and runs community detection
(Leiden preferred, falls back to Louvain if graspologic is unavailable).

Persists the graph to disk as GraphML for inspection in Gephi / Cytoscape.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Dict, List, Tuple

import networkx as nx
from rich.console import Console
from rich.table import Table

from .models import Community, Entity, ExtractionResult, Relationship

console = Console()


# ─── Graph Construction ───────────────────────────────────────────────────────

class KnowledgeGraph:
    """
    Wraps a NetworkX MultiDiGraph with convenience methods for
    adding entities / relationships and running community detection.
    """

    def __init__(self) -> None:
        self.G: nx.Graph = nx.Graph()   # undirected for community detection
        self.DG: nx.DiGraph = nx.DiGraph()  # directed for traversal
        self._entity_map: Dict[str, Entity] = {}
        self._communities: List[Community] = []

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def add_extraction_results(self, results: List[ExtractionResult]) -> None:
        """Merge all extraction results into the graph."""
        for result in results:
            for ent in result.entities:
                self._add_entity(ent)
            for rel in result.relationships:
                self._add_relationship(rel)

        console.print(
            f"[green]GraphBuilder[/green] "
            f"Nodes: [bold]{self.G.number_of_nodes()}[/bold]  "
            f"Edges: [bold]{self.G.number_of_edges()}[/bold]"
        )

    def _add_entity(self, entity: Entity) -> None:
        # Merge by name – if seen before, enrich description
        if entity.name not in self._entity_map:
            self._entity_map[entity.name] = entity
            attrs = {
                "type": entity.type,
                "description": entity.description,
                "id": entity.id,
            }
            self.G.add_node(entity.name, **attrs)
            self.DG.add_node(entity.name, **attrs)
        else:
            # Merge descriptions
            existing = self._entity_map[entity.name]
            if entity.description and not existing.description:
                existing.description = entity.description
                nx.set_node_attributes(
                    self.G, {entity.name: {"description": entity.description}}
                )

    def _add_relationship(self, rel: Relationship) -> None:
        # Ensure both endpoints exist
        if rel.source_entity not in self.G:
            self.G.add_node(rel.source_entity, type="OTHER", description="")
            self.DG.add_node(rel.source_entity, type="OTHER", description="")
        if rel.target_entity not in self.G:
            self.G.add_node(rel.target_entity, type="OTHER", description="")
            self.DG.add_node(rel.target_entity, type="OTHER", description="")

        # Accumulate edge weight on duplicates
        if self.G.has_edge(rel.source_entity, rel.target_entity):
            self.G[rel.source_entity][rel.target_entity]["weight"] += rel.weight
        else:
            self.G.add_edge(
                rel.source_entity,
                rel.target_entity,
                relation=rel.relation,
                description=rel.description,
                weight=rel.weight,
                id=rel.id,
            )

        self.DG.add_edge(
            rel.source_entity,
            rel.target_entity,
            relation=rel.relation,
            description=rel.description,
            weight=rel.weight,
        )

    # ── Community Detection ───────────────────────────────────────────────────

    def detect_communities(
        self, algorithm: str = "leiden", resolution: float = 1.0
    ) -> List[Community]:
        """
        Run community detection. Returns a list of Community objects.

        Priority:
          1. Leiden (graspologic) – preferred for quality
          2. Louvain (python-louvain) – fallback
          3. Label Propagation – last resort (no extra deps)
        """
        console.print(f"[cyan]Community Detection[/cyan] Algorithm: {algorithm}")

        partition: Dict[str, int] = {}

        if algorithm == "leiden":
            partition = self._run_leiden()
        elif algorithm == "louvain":
            partition = self._run_louvain(resolution)
        else:
            partition = self._run_label_propagation()

        # Group nodes by community id
        community_map: Dict[int, List[str]] = {}
        for node, cid in partition.items():
            community_map.setdefault(cid, []).append(node)

        self._communities = [
            Community(id=cid, entity_names=nodes)
            for cid, nodes in community_map.items()
        ]

        self._print_community_stats()
        return self._communities

    def _run_leiden(self) -> Dict[str, int]:
        try:
            from graspologic.partition import leiden

            adj = nx.to_scipy_sparse_array(self.G, weight="weight")
            labels, _ = leiden(adj)
            nodes = list(self.G.nodes())
            return {nodes[i]: int(labels[i]) for i in range(len(nodes))}
        except ImportError:
            console.print(
                "[yellow]graspologic not installed; falling back to Louvain[/yellow]"
            )
            return self._run_louvain()

    def _run_louvain(self, resolution: float = 1.0) -> Dict[str, int]:
        try:
            import community as community_louvain

            partition = community_louvain.best_partition(
                self.G, weight="weight", resolution=resolution
            )
            return partition
        except ImportError:
            console.print(
                "[yellow]python-louvain not installed; falling back to Label Propagation[/yellow]"
            )
            return self._run_label_propagation()

    def _run_label_propagation(self) -> Dict[str, int]:
        communities_gen = nx.community.label_propagation_communities(self.G)
        partition = {}
        for cid, community_set in enumerate(communities_gen):
            for node in community_set:
                partition[node] = cid
        return partition

    def _print_community_stats(self) -> None:
        table = Table(title="Community Detection Results")
        table.add_column("Community ID", style="cyan")
        table.add_column("# Entities", style="green")
        table.add_column("Sample Members")
        for c in self._communities[:10]:
            table.add_row(
                str(c.id),
                str(len(c.entity_names)),
                ", ".join(c.entity_names[:5]),
            )
        console.print(table)
        console.print(f"Total communities: [bold]{len(self._communities)}[/bold]")

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def communities(self) -> List[Community]:
        return self._communities

    @property
    def entity_map(self) -> Dict[str, Entity]:
        return self._entity_map

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        # GraphML (human-readable, works with Gephi)
        nx.write_graphml(self.G, output_dir / "knowledge_graph.graphml")
        # Pickle for fast reload
        with open(output_dir / "knowledge_graph.pkl", "wb") as f:
            pickle.dump(self, f)
        # Communities as JSON
        communities_data = [c.model_dump() for c in self._communities]
        with open(output_dir / "communities.json", "w") as f:
            json.dump(communities_data, f, indent=2)
        console.print(f"[green]Graph saved to[/green] {output_dir}")

    @classmethod
    def load(cls, output_dir: Path) -> "KnowledgeGraph":
        pkl_path = output_dir / "knowledge_graph.pkl"
        with open(pkl_path, "rb") as f:
            kg = pickle.load(f)
        console.print(f"[green]Graph loaded from[/green] {output_dir}")
        return kg

    # ── Local Search Helpers ──────────────────────────────────────────────────

    def get_entity_context(
        self, entity_name: str, hop: int = 2
    ) -> Tuple[List[Entity], List[Relationship]]:
        """
        Return entities and relationships within `hop` hops of `entity_name`.
        Used by LocalSearch.
        """
        if entity_name not in self.DG:
            return [], []

        subgraph_nodes = set(
            nx.ego_graph(self.G, entity_name, radius=hop).nodes()
        )
        entities = [
            self._entity_map[n]
            for n in subgraph_nodes
            if n in self._entity_map
        ]
        relationships = [
            Relationship(
                source_entity=u,
                target_entity=v,
                relation=self.DG[u][v].get("relation", ""),
                description=self.DG[u][v].get("description", ""),
                weight=self.DG[u][v].get("weight", 1.0),
            )
            for u, v in self.DG.edges()
            if u in subgraph_nodes and v in subgraph_nodes
        ]
        return entities, relationships
