# GraphRAG Intelligence Engine — Deep Dive Documentation

![GraphRAG Hero Architecture](/Users/antenehtessema/.gemini/antigravity/brain/ecd0d963-2426-40dd-ba91-f7651b85053d/graphrag_visual_guide_hero_1777322872931.png)

This document provides an exhaustive, visual guide to the **GraphRAG Intelligence Engine**. It covers the end-to-end lifecycle of a document, from "dropping it in a folder" to "querying the collective intelligence."

---

## 1. The Autonomous "Watch-and-Index" Lifecycle

The system is designed to be zero-touch. The moment a file is added to your environment, a series of background events are triggered.

### 🔄 Data Ingestion Flowchart
```mermaid
graph TD
    A[New File .txt/.md/.pdf] -->|FileSystem Event| B(Watcher Service)
    B -->|Debounce 5s| C{Pipeline Running?}
    C -->|Yes| D[Queue Task]
    C -->|No| E[Start Indexing Pipeline]
    E --> F[1. Token-Aware Chunking]
    F --> G[2. Entity & Relationship Extraction]
    G --> H[3. Knowledge Graph Assembly]
    H --> I[4. Community Detection]
    I --> J[5. Community Summarization]
    J --> K[Final Graph Store & Vector Index]
    K --> L[Update UI Status]
```

---

## 2. Advanced Retrieval Strategies

GraphRAG doesn't just search for text; it understands **relationships** and **thematic structures**.

### 🔍 Local Search (Deep Context)
Best for specific entities. It extracts a "knowledge subgraph" around your query.

```mermaid
sequenceDiagram
    participant U as User
    participant R as Retriever
    participant E as Embeddings
    participant G as NetworkX Graph
    participant L as LLM (Ollama)

    U->>R: Query: "What are the CEO's main connections?"
    R->>E: Generate Query Embedding
    E->>G: Find 'CEO' Entity Node
    G->>R: Extract 2-Hop Relationship Subgraph
    R->>L: Generate Answer (Context: Subgraph Triples)
    L->>U: "The CEO is connected to X, Y, and Z via..."
```

### 🌍 Global Search (Big Picture)
Best for "What are the main themes?" It uses pre-computed **Community Summaries**.

```mermaid
sequenceDiagram
    participant U as User
    participant R as Retriever
    participant S as Community Summaries
    participant L as LLM (Ollama)

    U->>R: Query: "What are the overarching trends?"
    R->>S: Rank Summaries by Semantic Similarity
    S->>R: Top-K Summaries (Themes)
    R->>L: Synthesize Holistic Answer
    L->>U: "The primary trends identified are..."
```

---

## 3. Background Persistence (Forever Free)

The engine runs as a native OS service, ensuring it's always ready without an open terminal.

### 🖥️ macOS/Linux Deployment Architecture
```mermaid
graph LR
    A[macOS Login] -->|LaunchAgent| B(run_background.sh)
    B --> C[Uvicorn Server :8000]
    C --> D[File Watcher Thread]
    D -->|Monitoring| E[./data/ folder]
    C --> F[API Endpoints]
    F --> G[Vanilla JS Frontend]
```

---

## 4. CI/CD & Cloud Pipeline

Your development workflow is automated from local push to global registry.

```mermaid
graph TD
    A[Local Code Push] -->|GitHub Actions| B(Test Job: Pytest)
    B -->|Success| C(Build Job: Docker)
    C --> D[Push to GHCR]
    D --> E[Sync to Hugging Face Spaces]
    E -->|Live Demo| F[https://huggingface.co/spaces/...]
```

---

## 5. Technical Specification

| Component | Technology | Role |
|---|---|---|
| **Language** | Python 3.11 | Core Logic & API |
| **LLM Provider** | Ollama (Llama 3) | Extraction & Summarization |
| **Embeddings** | Sentence-Transformers | Local Semantic Search |
| **Graph Backend** | NetworkX / Neo4j | Relationship Storage |
| **Persistence** | GraphML & Pickle | Local Disk Storage |
| **Monitoring** | Watchdog | Real-time Ingestion |
| **Automation** | GitHub Actions | CI/CD |

---

## 6. Visual Glossary

*   **Entity (Node)**: A person, place, concept, or object identified in your data.
*   **Relationship (Edge)**: A specific connection between two entities (e.g., "Works At", "Founded By").
*   **Community**: A cluster of highly-related entities identified via the **Leiden Algorithm**.
*   **Summary**: An AI-generated thematic description of a specific community.

---

*This documentation is automatically updated and maintained by the GraphRAG Intelligence Engine.*
