"""
graphrag/config.py
──────────────────
Central configuration object loaded from .env / environment variables.
Uses Pydantic v2 / pydantic-settings syntax.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class GraphRAGConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER") # openai | ollama | groq
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    ollama_base_url: str = Field(default="http://localhost:11434/v1", alias="OLLAMA_BASE_URL")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_base_url: str = Field(default="https://api.groq.com/openai/v1", alias="GROQ_BASE_URL")
    extraction_model: str = Field(default="gpt-4o", alias="EXTRACTION_MODEL")
    summarization_model: str = Field(default="gpt-4o-mini", alias="SUMMARIZATION_MODEL")
    
    # ── Embeddings ────────────────────────────────────────────────────────────
    embedding_provider: str = Field(default="openai", alias="EMBEDDING_PROVIDER") # openai | local
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=1536, alias="EMBEDDING_DIM")

    # ── Chunking ─────────────────────────────────────────────────────────────
    chunk_size: int = Field(default=1200, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=100, alias="CHUNK_OVERLAP")
    max_entities_per_chunk: int = Field(default=30, alias="MAX_ENTITIES_PER_CHUNK")

    # ── Community Detection ───────────────────────────────────────────────────
    community_algorithm: str = Field(default="louvain", alias="COMMUNITY_ALGORITHM")
    resolution: float = Field(default=1.0, alias="RESOLUTION")

    # ── Storage ───────────────────────────────────────────────────────────────
    graph_backend: str = Field(default="networkx", alias="GRAPH_BACKEND") # networkx | neo4j
    graph_output_dir: Path = Field(default=Path("./output/graph"), alias="GRAPH_OUTPUT_DIR")
    chroma_persist_dir: Path = Field(default=Path("./output/chroma"), alias="CHROMA_PERSIST_DIR")
    summaries_output_dir: Path = Field(
        default=Path("./output/summaries"), alias="SUMMARIES_OUTPUT_DIR"
    )

    # ── Neo4j (optional) ──────────────────────────────────────────────────────
    neo4j_uri: Optional[str] = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: Optional[str] = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: Optional[str] = Field(default="password", alias="NEO4J_PASSWORD")

    def ensure_dirs(self) -> None:
        for d in [
            self.graph_output_dir,
            self.chroma_persist_dir,
            self.summaries_output_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def require_api_key(self) -> str:
        """Return the API key or raise a clear error if using OpenAI."""
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Copy .env.example → .env and add your key."
            )
        return self.openai_api_key

    def get_llm_params(self) -> dict:
        """Get common LLM parameters based on provider."""
        if self.llm_provider == "ollama":
            return {
                "api_key": "ollama",
                "base_url": self.ollama_base_url
            }
        if self.llm_provider == "groq":
            return {
                "api_key": self.groq_api_key,
                "base_url": self.groq_base_url
            }
        return {
            "api_key": self.openai_api_key
        }


# Singleton
config = GraphRAGConfig()
