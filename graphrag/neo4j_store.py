"""
graphrag/neo4j_store.py
───────────────────────
Production-grade graph storage using Neo4j.
Mirrors the KnowledgeGraph interface for easy swapping.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple
from neo4j import GraphDatabase
from rich.console import Console
from .models import Entity, Relationship, ExtractionResult, Community

console = Console()

class Neo4jKnowledgeGraph:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def add_extraction_results(self, results: List[ExtractionResult]) -> None:
        """Merge extraction results into Neo4j using Cypher."""
        with self.driver.session() as session:
            for result in results:
                # Merge Entities
                for ent in result.entities:
                    session.execute_write(self._merge_entity, ent)
                
                # Merge Relationships
                for rel in result.relationships:
                    session.execute_write(self._merge_relationship, rel)

        console.print(f"[green]Neo4jBuilder[/green] Ingested {len(results)} extraction results.")

    @staticmethod
    def _merge_entity(tx, entity: Entity):
        query = (
            "MERGE (e:Entity {name: $name}) "
            "SET e.type = $type, e.description = $description, e.uuid = $id"
        )
        tx.run(query, name=entity.name, type=entity.type, description=entity.description, id=entity.id)

    @staticmethod
    def _merge_relationship(tx, rel: Relationship):
        query = (
            "MATCH (a:Entity {name: $source}) "
            "MATCH (b:Entity {name: $target}) "
            "MERGE (a)-[r:RELATED_TO {relation: $relation}]->(b) "
            "SET r.description = $description, r.weight = coalesce(r.weight, 0) + $weight"
        )
        tx.run(query, source=rel.source_entity, target=rel.target_entity, 
               relation=rel.relation, description=rel.description, weight=rel.weight)

    def get_entity_context(self, entity_name: str, hop: int = 2) -> Tuple[List[Entity], List[Relationship]]:
        """Fetch N-hop context from Neo4j."""
        with self.driver.session() as session:
            # Cypher query for N-hop neighbourhood
            query = (
                f"MATCH (n:Entity {{name: $name}})-[r*1..{hop}]-(m:Entity) "
                "RETURN n, r, m"
            )
            result = session.run(query, name=entity_name)
            
            entities = {}
            relationships = []
            
            for record in result:
                # Process nodes
                for node in [record['n'], record['m']]:
                    if node['name'] not in entities:
                        entities[node['name']] = Entity(
                            name=node['name'],
                            type=node['type'],
                            description=node['description'],
                            id=node.get('uuid', '')
                        )
                
                # Process relationships (path list)
                for rel in record['r']:
                    relationships.append(Relationship(
                        source_entity=rel.start_node['name'],
                        target_entity=rel.end_node['name'],
                        relation=rel['relation'],
                        description=rel.get('description', ''),
                        weight=rel.get('weight', 1.0)
                    ))
            
            return list(entities.values()), relationships

    def save(self, *args, **kwargs):
        """No-op for Neo4j as it's already persisted."""
        pass

    @property
    def entity_map(self) -> Dict[str, Entity]:
        """Fetch all entities from Neo4j."""
        with self.driver.session() as session:
            result = session.run("MATCH (e:Entity) RETURN e")
            return {r['e']['name']: Entity(
                name=r['e']['name'],
                type=r['e']['type'],
                description=r['e']['description']
            ) for r in result}

    @property
    def communities(self) -> List[Community]:
        # Implementation for community detection in Neo4j would use GDS plugin
        # For now, we return empty list or handle via summarize_all
        return []
