"""
graphrag/extractor.py
─────────────────────
Phase 1 – Step 2: Entity & Relationship Extraction via LLM.

For each text chunk the extractor sends a structured prompt to an LLM and
parses the JSON response into typed Entity / Relationship objects.

Design decisions:
  • Uses OpenAI structured output (response_format=json_object) for reliability.
  • Tenacity-based retry with exponential back-off for rate limits.
  • Batches concurrently with asyncio to maximise throughput.
"""

from __future__ import annotations

import asyncio
import json
from typing import List

from openai import AsyncOpenAI
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception_type,
)
from rich.console import Console
from rich.progress import track

from .models import Entity, ExtractionResult, Relationship, TextChunk

console = Console()

# ─── Prompt ──────────────────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """\
You are a knowledge-graph extraction engine.

Given a text passage, extract ALL meaningful entities and the relationships
between them.

Return ONLY a valid JSON object with this exact schema:
{
  "entities": [
    {
      "name": "string – canonical entity name (Title Case)",
      "type": "PERSON | ORG | CONCEPT | PLACE | EVENT | PRODUCT | OTHER",
      "description": "one-sentence description"
    }
  ],
  "relationships": [
    {
      "source_entity": "exact name from entities list",
      "target_entity": "exact name from entities list",
      "relation": "short snake_case verb phrase, e.g. 'acquired', 'founded', 'part_of'",
      "description": "one-sentence explanation of the relationship",
      "weight": 0.0-1.0
    }
  ]
}

Rules:
- Only extract entities explicitly mentioned in the passage.
- Prefer canonical / full names (e.g. "Microsoft Corporation" not "MS").
- Every relationship must reference entities in the entities list.
- Be exhaustive but avoid hallucinating information not in the text.
"""

EXTRACTION_USER_TEMPLATE = """\
Passage:
\"\"\"
{text}
\"\"\"

Extract all entities and relationships. Return JSON only."""


# ─── Extractor ────────────────────────────────────────────────────────────────

class EntityExtractor:
    def __init__(
        self,
        llm_params: dict,
        model: str = "gpt-4o",
        max_concurrency: int = 5,
    ):
        self.client = AsyncOpenAI(**llm_params)
        self.model = model
        self.semaphore = asyncio.Semaphore(max_concurrency)

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_random_exponential(min=1, max=30),
        stop=stop_after_attempt(4),
    )
    async def _call_llm(self, text: str) -> dict:
        async with self.semaphore:
            response = await self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": EXTRACTION_USER_TEMPLATE.format(text=text),
                    },
                ],
                temperature=0.0,
            )
        return json.loads(response.choices[0].message.content)

    async def _extract_chunk(self, chunk: TextChunk) -> ExtractionResult:
        try:
            raw = await self._call_llm(chunk.text)
        except Exception as e:
            console.print(f"[red]Extraction failed for chunk {chunk.id}: {e}[/red]")
            return ExtractionResult(chunk_id=chunk.id)

        entities: List[Entity] = []
        for e in raw.get("entities", []):
            entities.append(
                Entity(
                    name=e.get("name", "").strip(),
                    type=e.get("type", "OTHER").upper(),
                    description=e.get("description", ""),
                    source_chunk_id=chunk.id,
                )
            )

        name_set = {ent.name for ent in entities}
        relationships: List[Relationship] = []
        for r in raw.get("relationships", []):
            src = r.get("source_entity", "").strip()
            tgt = r.get("target_entity", "").strip()
            # Only keep relationships where both endpoints were extracted
            if src in name_set and tgt in name_set:
                relationships.append(
                    Relationship(
                        source_entity=src,
                        target_entity=tgt,
                        relation=r.get("relation", "related_to"),
                        description=r.get("description", ""),
                        weight=float(r.get("weight", 1.0)),
                        source_chunk_id=chunk.id,
                    )
                )

        return ExtractionResult(
            chunk_id=chunk.id, entities=entities, relationships=relationships
        )

    async def extract_all_async(
        self, chunks: List[TextChunk]
    ) -> List[ExtractionResult]:
        tasks = [self._extract_chunk(c) for c in chunks]
        results = await asyncio.gather(*tasks)
        total_ents = sum(len(r.entities) for r in results)
        total_rels = sum(len(r.relationships) for r in results)
        console.print(
            f"[green]Extractor[/green] → "
            f"[bold]{total_ents}[/bold] entities, "
            f"[bold]{total_rels}[/bold] relationships across "
            f"[bold]{len(chunks)}[/bold] chunks"
        )
        return list(results)

    def extract_all(self, chunks: List[TextChunk]) -> List[ExtractionResult]:
        """Synchronous wrapper."""
        return asyncio.run(self.extract_all_async(chunks))
