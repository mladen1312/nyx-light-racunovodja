"""
Folder Watcher — nadzor lokalnih mrežnih mapa za nove dokumente.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("nyx_light.ingest.folder")


class FolderWatcher:
    """Nadzire watch foldere za nove dokumente."""

    def __init__(self, watch_paths: List[str] = None):
        self.watch_paths = [Path(p) for p in (watch_paths or ["data/uploads"])]
        logger.info("FolderWatcher: %s", [str(p) for p in self.watch_paths])

    def scan(self) -> List[Dict[str, Any]]:
        """Skeniraj watch foldere za nove datoteke."""
        new_files = []
        for folder in self.watch_paths:
            if folder.exists():
                for f in folder.iterdir():
                    if f.is_file() and f.suffix.lower() in (".pdf", ".csv", ".sta", ".xlsx"):
                        new_files.append({
                            "path": str(f),
                            "name": f.name,
                            "size": f.stat().st_size,
                            "type": f.suffix.lower(),
                        })
        return new_files
