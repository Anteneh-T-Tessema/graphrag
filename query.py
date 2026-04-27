"""
query.py
─────────
Interactive query CLI for the GraphRAG system.

Usage:
  # Auto-route (recommended):
  python query.py "What are the main themes in this corpus?"

  # Force local search:
  python query.py --mode local "Tell me about OpenAI"

  # Force global search:
  python query.py --mode global "What are the recurring patterns?"

  # Interactive REPL mode:
  python query.py --interactive
"""

from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from graphrag.config import config
from graphrag.graph_builder import KnowledgeGraph
from graphrag.retriever import GraphRAGRetriever
from graphrag.summarizer import CommunitySummarizer

console = Console()


def load_retriever() -> GraphRAGRetriever:
    """Load pre-built graph and community summaries from disk."""
    console.print("[cyan]Loading knowledge graph...[/cyan]")
    kg = KnowledgeGraph.load(config.graph_output_dir)

    console.print("[cyan]Loading community summaries...[/cyan]")
    communities = CommunitySummarizer.load_summaries(config.summaries_output_dir)

    retriever = GraphRAGRetriever(
        kg=kg,
        communities=communities,
        llm_params=config.get_llm_params(),
        extraction_model=config.extraction_model,
        summarization_model=config.summarization_model,
        embedding_model=config.embedding_model,
    )
    console.print("[green]✓ GraphRAG system ready[/green]\n")
    return retriever


def print_result(result: dict) -> None:
    console.print(Panel(
        Markdown(result["answer"]),
        title=f"[bold cyan]{result['mode'].upper()} SEARCH[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    ))


def run_interactive(retriever: GraphRAGRetriever) -> None:
    console.print(Panel.fit(
        "[bold cyan]GraphRAG Interactive Query[/bold cyan]\n"
        "Type your question (or 'exit' to quit)\n"
        "Prefix with [local] or [global] to force a mode",
        border_style="cyan",
    ))

    while True:
        try:
            question = console.input("\n[bold yellow]> [/bold yellow]").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not question or question.lower() in ("exit", "quit", "q"):
            break

        mode = None
        if question.startswith("[local]"):
            mode = "local"
            question = question[7:].strip()
        elif question.startswith("[global]"):
            mode = "global"
            question = question[8:].strip()

        result = retriever.query(question, mode=mode)
        print_result(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphRAG Query Interface")
    parser.add_argument("question", nargs="?", help="Question to answer")
    parser.add_argument(
        "--mode",
        choices=["local", "global", "auto"],
        default="auto",
        help="Search mode (default: auto)",
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Start interactive REPL"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output result as JSON"
    )
    args = parser.parse_args()

    retriever = load_retriever()

    if args.interactive:
        run_interactive(retriever)
    elif args.question:
        mode = None if args.mode == "auto" else args.mode
        result = retriever.query(args.question, mode=mode)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_result(result)
    else:
        parser.print_help()
        sys.exit(1)
