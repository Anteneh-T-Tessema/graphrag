---
title: GraphRAG Blueprint
emoji: 🕸️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: true
license: mit
---

# GraphRAG — Custom Knowledge Graph RAG Pipeline

A production-grade, from-scratch implementation of the **GraphRAG** architecture based on Microsoft Research's design: a two-phase system that builds a knowledge graph from documents and queries it via Local (entity-centric) or Global (community-summary) search.

> [!TIP]
> **New:** This implementation now supports **Ollama** for a 100% local, private GraphRAG experience. See [DOCUMENTATION.md](DOCUMENTATION.md) for details.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   PHASE 1: INDEXING                              │
│                                                                 │
│  Documents → Chunks → [LLM] Entity/Rel Extraction              │
│           → NetworkX Graph → Community Detection (Leiden)       │
│           → [LLM] Community Summarization → Summaries           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   PHASE 2: QUERYING                              │
│                                                                 │
│  "Who is the CEO?"  → LOCAL SEARCH  → N-hop subgraph → Answer  │
│  "What are themes?" → GLOBAL SEARCH → Top-K summaries → Answer │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
graphrag/
├── graphrag/
│   ├── __init__.py          # Public API
│   ├── config.py            # Pydantic settings from .env
│   ├── models.py            # Shared data models
│   ├── chunker.py           # Phase 1, Step 1: Token-aware chunking
│   ├── extractor.py         # Phase 1, Step 2: LLM entity/rel extraction
│   ├── graph_builder.py     # Phase 1, Steps 3&4: Graph + community detection
│   ├── summarizer.py        # Phase 1, Step 5: Community summarization
│   └── retriever.py         # Phase 2: Local + Global search
├── data/                    # Place your source documents here (.txt, .md)
├── output/
│   ├── graph/               # GraphML + pickle
│   └── summaries/           # community_summaries.json
├── tests/
│   ├── test_chunker.py
│   └── test_graph_builder.py
├── pipeline.py              # Indexing orchestrator
├── query.py                 # Query CLI
├── requirements.txt
└── .env.example
```

## Quick Start

### 1. Setup

```bash
# Create and activate venv
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env and set your OPENAI_API_KEY
```

### 2. Run the Indexing Pipeline

```bash
# Index documents in ./data directory
python pipeline.py --input ./data
```

This will:
1. Chunk all `.txt` / `.md` files in `./data`
2. Extract entities & relationships via GPT-4o
3. Build the NetworkX knowledge graph
4. Detect communities (Leiden algorithm)
5. Generate LLM summaries for each community
6. Save graph + summaries to `./output/`

### 3. Query the System

```bash
# Auto-routed (recommended)
python query.py "Who founded OpenAI?"

# Force LOCAL search (entity-specific)
python query.py --mode local "What companies did Sam Altman lead?"

# Force GLOBAL search (thematic)
python query.py --mode global "What are the main investment patterns in AI?"

# Interactive REPL
python query.py --interactive

# JSON output (for API integration)
python query.py --json "What are the key themes?"
```

### 4. Running in the Background (Forever Free)

If you want the GraphRAG Intelligence Engine to run continuously in the background on your machine (starting automatically on login), we provide a universal setup script for macOS and Linux.

```bash
# Set up the background service (Native macOS LaunchAgent or Linux Systemd)
bash scripts/setup_service.sh
```

- **Mac**: Installs a `LaunchAgent` to `~/Library/LaunchAgents/`
- **Linux**: Installs a `Systemd` user service to `~/.config/systemd/user/`
- **Logs**: View background activity in `output/logs/`

---

### 5. Run Tests

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | required | Your OpenAI API key |
| `EXTRACTION_MODEL` | `gpt-4o` | LLM for entity extraction |
| `SUMMARIZATION_MODEL` | `gpt-4o-mini` | LLM for community summaries |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `CHUNK_SIZE` | `1200` | Tokens per chunk |
| `CHUNK_OVERLAP` | `100` | Overlap between chunks |
| `COMMUNITY_ALGORITHM` | `leiden` | `leiden` \| `louvain` \| `label_propagation` |
| `RESOLUTION` | `1.0` | Community detection resolution |

## Search Modes Explained

### Local Search
Best for: **"Who is X?"**, **"What does Y do?"**, **"How are A and B connected?"**

- Embeds the query and finds the most semantically similar entity node
- Extracts an N-hop neighbourhood subgraph around that entity
- Uses the subgraph context to generate a precise answer

### Global Search
Best for: **"What are the main themes?"**, **"What patterns exist?"**, **"Give me an overview of..."**

- Ranks all community summaries by semantic similarity to the query
- Feeds the top-K summaries to the LLM for synthesis
- Produces a holistic, bird's-eye-view answer

### Auto-Routing
The default mode scans the query for known entity names. If a match is found, it routes to Local; otherwise Global.

## Upgrading to Neo4j (Production)

To swap NetworkX for Neo4j, install `neo4j>=5.20.0`, uncomment the `NEO4J_*` vars in `.env`, and replace `KnowledgeGraph` with a `Neo4jKnowledgeGraph` subclass that mirrors the same interface. The retriever and summarizer require no changes.

## Inspecting the Graph

The graph is saved as `output/graph/knowledge_graph.graphml` — open it with:
- **[Gephi](https://gephi.org/)** (free, desktop)
- **[Cytoscape](https://cytoscape.org/)** (free, desktop)
- **NetworkX** directly in a notebook

```python
import networkx as nx
G = nx.read_graphml("output/graph/knowledge_graph.graphml")
print(nx.info(G))
```
