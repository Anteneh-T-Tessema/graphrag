"""
graphrag/summarizer.py
───────────────────────
Phase 1 – Step 5: Community Summarization.

For each community, we collect the full entity descriptions and the
relationship descriptions within that community, then ask the LLM to
produce a thematic summary.  These summaries are what power Global Search.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Dict, List

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_random_exponential
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import Community, Entity, Relationship
from .graph_builder import KnowledgeGraph

console = Console()

SUMMARIZE_SYSTEM = """\
You are an expert analyst. Given information about a cluster of related
entities and their relationships, write a concise, insightful thematic
summary (3-6 sentences) that captures:
1. Who / what the key entities are
2. The primary themes and dynamics connecting them
3. Any notable patterns or insights

Be specific, avoid generic statements. Write in plain English."""

SUMMARIZE_USER_TEMPLATE = """\
Community Entities:
{entities}

Relationships:
{relationships}

Write a thematic summary of this community."""


class CommunitySummarizer:
    def __init__(
        self,
        llm_params: dict,
        model: str = "gpt-4o-mini",
        max_concurrency: int = 10,
    ):
        self.client = AsyncOpenAI(**llm_params)
        self.model = model
        self.semaphore = asyncio.Semaphore(max_concurrency)

    @retry(
        wait=wait_random_exponential(min=1, max=20),
        stop=stop_after_attempt(3),
    )
    async def _summarize_community(
        self,
        community: Community,
        kg: KnowledgeGraph,
    ) -> Community:
        """Generate a textual summary for a single community."""
        # Build context from entity descriptions
        entity_lines = []
        for name in community.entity_names:
            ent = kg.entity_map.get(name)
            if ent:
                entity_lines.append(f"- {ent.name} ({ent.type}): {ent.description}")
            else:
                entity_lines.append(f"- {name}")

        # Collect internal relationships
        rel_lines = []
        node_set = set(community.entity_names)
        for u, v, data in kg.DG.edges(data=True):
            if u in node_set and v in node_set:
                rel_lines.append(
                    f"- {u} --[{data.get('relation', 'related')}]--> {v}: "
                    f"{data.get('description', '')}"
                )

        entities_str = "\n".join(entity_lines[:50])  # cap context size
        rels_str = "\n".join(rel_lines[:50])

        async with self.semaphore:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SUMMARIZE_SYSTEM},
                    {
                        "role": "user",
                        "content": SUMMARIZE_USER_TEMPLATE.format(
                            entities=entities_str, relationships=rels_str
                        ),
                    },
                ],
                temperature=0.3,
                max_tokens=400,
            )

        community.summary = response.choices[0].message.content.strip()
        return community

    async def summarize_all_async(self, kg: KnowledgeGraph) -> List[Community]:
        communities = kg.communities
        console.print(
            f"[cyan]Summarizer[/cyan] Generating summaries for "
            f"[bold]{len(communities)}[/bold] communities..."
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Summarizing communities...", total=len(communities))
            tasks = []
            for c in communities:
                tasks.append(self._summarize_community(c, kg))

            results = []
            for coro in asyncio.as_completed(tasks):
                result = await coro
                results.append(result)
                progress.advance(task)

        console.print(f"[green]✓ All community summaries generated[/green]")
        return results

    def summarize_all(self, kg: KnowledgeGraph) -> List[Community]:
        """Synchronous wrapper."""
        return asyncio.run(self.summarize_all_async(kg))

    def save_summaries(self, communities: List[Community], output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        data = [c.model_dump() for c in communities]
        out_path = output_dir / "community_summaries.json"
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
        console.print(f"[green]Summaries saved →[/green] {out_path}")

    @staticmethod
    def load_summaries(output_dir: Path) -> List[Community]:
        path = output_dir / "community_summaries.json"
        with open(path) as f:
            data = json.load(f)
        return [Community(**c) for c in data]
