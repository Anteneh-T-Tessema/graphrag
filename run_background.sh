#!/bin/bash
# ─── GraphRAG Background Runner ──────────────────────────────────────────────

# Path to your project
PROJECT_DIR="/Users/antenehtessema/developer/graphrag"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
VENV_UVICORN="$PROJECT_DIR/venv/bin/uvicorn"

# Navigate to project
cd "$PROJECT_DIR"

# Run the server
# We use port 8000 for local background access
exec "$VENV_UVICORN" server:app --host 0.0.0.0 --port 8000
