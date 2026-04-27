"""
server.py
──────────
FastAPI backend for the GraphRAG UI.

Endpoints:
  GET  /                          → Serve frontend
  GET  /api/status                → System readiness + graph stats
  GET  /api/graph                 → Full graph data (nodes + edges) for D3
  GET  /api/communities           → All community summaries
  POST /api/query                 → Run a query (local / global / auto)
  POST /api/upload                → Upload documents to ./data/
  POST /api/pipeline/run          → Trigger indexing pipeline (background)
  GET  /api/pipeline/status       → Pipeline run status
  WS   /ws/pipeline               → Stream pipeline logs in real-time

Run:
  source venv/bin/activate
  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

import networkx as nx
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from graphrag.config import config
from graphrag.graph_builder import KnowledgeGraph
from graphrag.neo4j_store import Neo4jKnowledgeGraph
from graphrag.summarizer import CommunitySummarizer

# ─── App setup ───────────────────────────────────────────────────────────────

app = FastAPI(title="GraphRAG UI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Global state ─────────────────────────────────────────────────────────────

_kg: Optional[KnowledgeGraph] = None
_communities = []
_pipeline_status = {
    "running": False,
    "progress": 0,
    "step": "idle",
    "logs": [],
    "last_run": None,
    "error": None,
}
_ws_clients: List[WebSocket] = []


def _load_graph():
    if config.graph_backend == "neo4j":
        try:
            return Neo4jKnowledgeGraph(
                uri=config.neo4j_uri,
                user=config.neo4j_user,
                password=config.neo4j_password
            )
        except Exception:
            return None
            
    pkl = config.graph_output_dir / "knowledge_graph.pkl"
    if pkl.exists():
        try:
            with open(pkl, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None
    return None


def _load_communities():
    try:
        return CommunitySummarizer.load_summaries(config.summaries_output_dir)
    except Exception:
        return []


def _refresh_state():
    global _kg, _communities
    _kg = _load_graph()
    _communities = _load_communities()


# Attempt to load on startup
_refresh_state()


# ─── WebSocket broadcast ──────────────────────────────────────────────────────

async def _broadcast(message: dict):
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


# ─── Pipeline runner (background) ─────────────────────────────────────────────

async def _run_pipeline_bg(input_dir: str):
    global _pipeline_status

    _pipeline_status.update(
        running=True, progress=0, step="starting", logs=[], error=None,
        last_run=time.strftime("%Y-%m-%dT%H:%M:%S")
    )
    await _broadcast({"type": "pipeline_status", "data": _pipeline_status})

    steps = [
        (10, "chunking", "Chunking documents…"),
        (30, "extracting", "Extracting entities & relationships (LLM)…"),
        (60, "building_graph", "Building knowledge graph…"),
        (75, "detecting_communities", "Detecting communities…"),
        (90, "summarizing", "Summarizing communities (LLM)…"),
        (100, "saving", "Saving outputs…"),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "pipeline.py", "--input", input_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=Path(__file__).parent,
        )

        step_idx = 0
        async for line in proc.stdout:
            text = line.decode("utf-8", errors="replace").rstrip()
            _pipeline_status["logs"].append(text)

            # Advance step based on keyword matching
            if step_idx < len(steps):
                pct, step_key, _ = steps[step_idx]
                keywords = {
                    "chunking": "chunker",
                    "extracting": "extractor",
                    "building_graph": "graphbuilder",
                    "detecting_communities": "community",
                    "summarizing": "summarizer",
                    "saving": "saved",
                }
                if keywords.get(step_key, "") in text.lower():
                    _pipeline_status["progress"] = pct
                    _pipeline_status["step"] = step_key
                    step_idx += 1

            await _broadcast({
                "type": "pipeline_log",
                "line": text,
                "progress": _pipeline_status["progress"],
                "step": _pipeline_status["step"],
            })

        await proc.wait()

        if proc.returncode == 0:
            _pipeline_status["progress"] = 100
            _pipeline_status["step"] = "complete"
            _refresh_state()
            await _broadcast({"type": "pipeline_complete"})
        else:
            _pipeline_status["error"] = "Pipeline exited with non-zero status"
            await _broadcast({"type": "pipeline_error", "message": _pipeline_status["error"]})

    except Exception as e:
        _pipeline_status["error"] = str(e)
        await _broadcast({"type": "pipeline_error", "message": str(e)})
    finally:
        _pipeline_status["running"] = False
        await _broadcast({"type": "pipeline_status", "data": _pipeline_status})


# ─── REST Endpoints ───────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    has_graph = _kg is not None
    backend_status = "connected" if has_graph else "not_found"
    
    # Extra check for Neo4j
    if config.graph_backend == "neo4j" and has_graph:
        try:
            # Simple ping
            _kg.driver.verify_connectivity()
        except Exception:
            backend_status = "connection_error"

    return {
        "ready": has_graph and backend_status == "connected",
        "backend": config.graph_backend,
        "backend_status": backend_status,
        "graph": {
            "nodes": _kg.G.number_of_nodes() if (has_graph and hasattr(_kg, 'G')) else 0, # Note: Neo4j would need a count query
            "edges": _kg.G.number_of_edges() if (has_graph and hasattr(_kg, 'G')) else 0,
            "communities": len(_communities),
        },
        "pipeline": {
            "running": _pipeline_status["running"],
            "step": _pipeline_status["step"],
            "progress": _pipeline_status["progress"],
            "last_run": _pipeline_status["last_run"],
        },
        "data_files": [
            f.name for f in Path("./data").glob("*")
            if f.suffix in (".txt", ".md") and f.is_file()
        ],
    }


@app.get("/api/graph")
async def get_graph():
    if _kg is None:
        return {"nodes": [], "links": []}

    nodes = []
    for name, data in _kg.G.nodes(data=True):
        community_id = None
        for c in _communities:
            if name in c.entity_names:
                community_id = c.id
                break
        nodes.append({
            "id": name,
            "type": data.get("type", "OTHER"),
            "description": data.get("description", ""),
            "community": community_id,
            "degree": _kg.G.degree(name),
        })

    links = []
    for u, v, data in _kg.G.edges(data=True):
        links.append({
            "source": u,
            "target": v,
            "relation": data.get("relation", ""),
            "weight": data.get("weight", 1.0),
        })

    return {"nodes": nodes, "links": links}


@app.get("/api/communities")
async def get_communities():
    return [c.model_dump() for c in _communities]


class QueryRequest(BaseModel):
    question: str
    mode: str = "auto"  # auto | local | global


@app.post("/api/query")
async def run_query(req: QueryRequest):
    if config.llm_provider == "openai" and not config.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="OPENAI_API_KEY not set. Add it to your .env file or switch to LLM_PROVIDER=ollama"
        )
    if _kg is None:
        raise HTTPException(
            status_code=400,
            detail="No knowledge graph found. Run the indexing pipeline first."
        )

    from graphrag.retriever import GraphRAGRetriever

    retriever = GraphRAGRetriever(
        kg=_kg,
        communities=_communities,
        llm_params=config.get_llm_params(),
        extraction_model=config.extraction_model,
        summarization_model=config.summarization_model,
        embedding_model=config.embedding_model,
    )
    mode = None if req.mode == "auto" else req.mode
    result = retriever.query(req.question, mode=mode)
    return result


@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)
    saved = []
    for f in files:
        dest = data_dir / f.filename
        content = await f.read()
        dest.write_bytes(content)
        saved.append(f.filename)
    return {"saved": saved, "count": len(saved)}


class PipelineRequest(BaseModel):
    input_dir: str = "./data"


@app.post("/api/pipeline/run")
async def start_pipeline(req: PipelineRequest, background_tasks: BackgroundTasks):
    if _pipeline_status["running"]:
        raise HTTPException(status_code=409, detail="Pipeline already running")
    if not config.openai_api_key:
        raise HTTPException(
            status_code=400,
            detail="OPENAI_API_KEY not set. Add it to .env first."
        )
    background_tasks.add_task(_run_pipeline_bg, req.input_dir)
    return {"started": True, "input_dir": req.input_dir}


@app.get("/api/pipeline/status")
async def pipeline_status():
    return _pipeline_status


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/pipeline")
async def ws_pipeline(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    # Send current state immediately on connect
    await websocket.send_json({"type": "pipeline_status", "data": _pipeline_status})
    try:
        while True:
            await websocket.receive_text()  # keep alive
    except WebSocketDisconnect:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


# ─── Static files (frontend) ──────────────────────────────────────────────────

FRONTEND_DIR = Path(__file__).parent / "frontend"

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")


@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/{path:path}")
async def serve_spa(path: str):
    file = FRONTEND_DIR / path
    if file.exists() and file.is_file():
        return FileResponse(str(file))
    return FileResponse(str(FRONTEND_DIR / "index.html"))
