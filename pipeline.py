"""
pipeline.py
────────────
Full GraphRAG Indexing Pipeline Orchestrator.

Runs all 5 steps of Phase 1:
  1. Chunk source documents
  2. Extract entities & relationships (LLM)
  3. Build knowledge graph
  4. Detect communities
  5. Summarize communities (LLM)

Usage:
  python pipeline.py --input ./data --output ./output
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

from graphrag.chunker import chunk_directory
from graphrag.extractor import EntityExtractor
from graphrag.graph_builder import KnowledgeGraph
from graphrag.neo4j_store import Neo4jKnowledgeGraph
from graphrag.summarizer import CommunitySummarizer
from graphrag.config import config

console = Console()


def run_pipeline(input_dir: Path, output_dir: Path) -> None:
    config.ensure_dirs()
    start = time.time()

    console.print(Panel.fit(
        "[bold cyan]GraphRAG Indexing Pipeline[/bold cyan]\n"
        f"Input:  {input_dir}\n"
        f"Output: {output_dir}",
        border_style="cyan",
    ))

    # ── STEP 1: Chunking ─────────────────────────────────────────────────────
    console.print(Rule("[bold]Step 1: Document Chunking[/bold]"))
    chunks = chunk_directory(
        directory=input_dir,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    if not chunks:
        console.print("[red]No chunks produced. Check your input directory.[/red]")
        sys.exit(1)

    # ── STEP 2: Entity & Relationship Extraction ──────────────────────────────
    console.print(Rule("[bold]Step 2: Entity & Relationship Extraction[/bold]"))
    extractor = EntityExtractor(
        llm_params=config.get_llm_params(),
        model=config.extraction_model,
    )
    results = extractor.extract_all(chunks)

    # ── STEP 3: Graph Construction ────────────────────────────────────────────
    console.print(Rule("[bold]Step 3: Knowledge Graph Construction[/bold]"))
    if config.graph_backend == "neo4j":
        kg = Neo4jKnowledgeGraph(
            uri=config.neo4j_uri,
            user=config.neo4j_user,
            password=config.neo4j_password
        )
    else:
        kg = KnowledgeGraph()
        
    kg.add_extraction_results(results)

    # ── STEP 4: Community Detection ───────────────────────────────────────────
    console.print(Rule("[bold]Step 4: Community Detection[/bold]"))
    kg.detect_communities(
        algorithm=config.community_algorithm,
        resolution=config.resolution,
    )

    # ── STEP 5: Community Summarization ──────────────────────────────────────
    console.print(Rule("[bold]Step 5: Community Summarization[/bold]"))
    summarizer = CommunitySummarizer(
        llm_params=config.get_llm_params(),
        model=config.summarization_model,
    )
    summarizer.summarize_all(kg)

    # ── Save everything ───────────────────────────────────────────────────────
    console.print(Rule("[bold]Saving Outputs[/bold]"))
    kg.save(config.graph_output_dir)
    summarizer.save_summaries(kg.communities, config.summaries_output_dir)

    elapsed = time.time() - start
    console.print(Panel.fit(
        f"[bold green]✅ Pipeline complete![/bold green]\n"
        f"Elapsed: {elapsed:.1f}s\n"
        f"Graph: {config.graph_output_dir}/knowledge_graph.graphml\n"
        f"Summaries: {config.summaries_output_dir}/community_summaries.json",
        border_style="green",
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphRAG Indexing Pipeline")
    parser.add_argument(
        "--input", "-i", required=True, help="Directory containing source documents"
    )
    parser.add_argument(
        "--output", "-o", default="./output", help="Output directory"
    )
    args = parser.parse_args()
    run_pipeline(Path(args.input), Path(args.output))
