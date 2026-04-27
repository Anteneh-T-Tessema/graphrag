"""
graphrag/watcher.py
───────────────────
Real-time file system monitoring for the GraphRAG pipeline.
Automatically triggers indexing when new documents are added to the data/ directory.
"""

import time
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GraphRAG-Watcher")

class DataFolderHandler(FileSystemEventHandler):
    """
    Handles file creation and modification events in the data directory.
    Uses a simple debounce to avoid multiple triggers for a single file.
    """
    def __init__(self, callback):
        self.callback = callback
        self.last_triggered = 0
        self.debounce_seconds = 5

    def on_modified(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(('.txt', '.md', '.pdf')):
            self._trigger(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(('.txt', '.md', '.pdf')):
            self._trigger(event.src_path)

    def _trigger(self, file_path):
        current_time = time.time()
        if current_time - self.last_triggered > self.debounce_seconds:
            logger.info(f"📁 New/Modified file detected: {file_path}")
            self.last_triggered = current_time
            self.callback()

def start_watcher(pipeline_callback):
    """
    Starts the watchdog observer in a background thread.
    """
    data_dir = config.graph_output_dir.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    event_handler = DataFolderHandler(pipeline_callback)
    observer = Observer()
    observer.schedule(event_handler, str(data_dir), recursive=False)
    
    logger.info(f"👁️ Watcher active: Monitoring {data_dir} for changes...")
    observer.start()
    return observer
