"""
Nyx Light — Folder Watcher

Kontinuirano nadzire lokalne mape (watch folders) za nove dokumente.
Koristi polling (kompatibilno sa svim OS-ovima, uključujući SMB/NFS share).

Konfiguracija:
  "folders": {
    "watch_paths": ["data/uploads", "/Volumes/Shared/Racuni"],
    "scan_interval_sec": 10,
    "auto_process": true
  }
"""

import asyncio
import hashlib
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("nyx_light.ingest.folder")

SUPPORTED_EXTENSIONS = {
    ".pdf", ".xml", ".csv", ".xlsx", ".xls",
    ".png", ".jpg", ".jpeg", ".tiff", ".tif",
    ".sta", ".mt940", ".txt",
}


class FolderWatcher:
    """
    Nadzire watch foldere za nove dokumente.

    Flow:
      1. Skenira sve konfigurirane foldere
      2. Za nove/izmijenjene datoteke:
         a. Kopira u data/uploads/folder/
         b. Kreiraj pending booking
         c. Opcionalno premjesti original u "processed" podfolder
      3. Ponovi svakih N sekundi
    """

    def __init__(
        self,
        watch_paths: Optional[List[str]] = None,
        scan_interval: int = 10,
        auto_process: bool = True,
        processed_subfolder: str = "_processed",
        upload_dir: str = "data/uploads/folder",
    ):
        self.watch_paths = [Path(p) for p in (watch_paths or ["data/uploads"])]
        self.scan_interval = scan_interval
        self.auto_process = auto_process
        self.processed_subfolder = processed_subfolder
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._known_files: Dict[str, str] = {}  # path -> hash
        self._on_document: Optional[Callable] = None
        self._stats = {
            "scans": 0, "files_detected": 0,
            "files_processed": 0, "errors": 0, "last_scan": None,
        }
        logger.info("FolderWatcher: %s", [str(p) for p in self.watch_paths])

    def set_document_callback(self, callback: Callable):
        self._on_document = callback

    async def start(self):
        """Pokreni folder monitoring."""
        self._running = True
        # Initial scan to build known files set
        self._initial_scan()
        self._task = asyncio.create_task(self._loop())
        logger.info("Folder watcher pokrenut (interval: %ds, paths: %d)",
                     self.scan_interval, len(self.watch_paths))

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def _initial_scan(self):
        """Zabilježi postojeće datoteke (ne obrađuj ih)."""
        for folder in self.watch_paths:
            if not folder.exists():
                continue
            for f in self._iter_files(folder):
                self._known_files[str(f)] = self._file_hash(f)

    async def _loop(self):
        while self._running:
            try:
                new_files = await asyncio.to_thread(self._scan)
                for file_info in new_files:
                    if self._on_document:
                        try:
                            self._on_document(file_info["saved_to"], file_info)
                        except Exception as e:
                            logger.error("Callback error: %s", e)
                self._stats["last_scan"] = datetime.now().isoformat()
            except Exception as e:
                self._stats["errors"] += 1
                logger.error("Scan error: %s", e)

            try:
                await asyncio.sleep(self.scan_interval)
            except asyncio.CancelledError:
                break

    def _scan(self) -> List[Dict[str, Any]]:
        """Skeniraj sve foldere za nove/izmijenjene datoteke."""
        self._stats["scans"] += 1
        new_files = []

        for folder in self.watch_paths:
            if not folder.exists():
                continue

            for f in self._iter_files(folder):
                fpath = str(f)
                fhash = self._file_hash(f)

                if fpath in self._known_files and self._known_files[fpath] == fhash:
                    continue  # Already known, unchanged

                self._known_files[fpath] = fhash
                self._stats["files_detected"] += 1

                # Process new file
                try:
                    info = self._process_file(f)
                    if info:
                        new_files.append(info)
                        self._stats["files_processed"] += 1
                except Exception as e:
                    self._stats["errors"] += 1
                    logger.error("Error processing %s: %s", f.name, e)

        return new_files

    def _process_file(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """Obradi novu datoteku."""
        ext = filepath.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            return None

        # Copy to upload dir
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self.upload_dir / f"{ts}_{filepath.name}"
        shutil.copy2(filepath, dest)

        # Detect document type
        doc_type = self._detect_type(filepath)

        info = {
            "source": "folder",
            "original_path": str(filepath),
            "saved_to": str(dest),
            "filename": filepath.name,
            "size_bytes": filepath.stat().st_size,
            "extension": ext,
            "document_type": doc_type,
            "detected_at": datetime.now().isoformat(),
        }

        # Optionally move to processed subfolder
        if self.auto_process and self.processed_subfolder:
            processed_dir = filepath.parent / self.processed_subfolder
            processed_dir.mkdir(exist_ok=True)
            try:
                shutil.move(str(filepath), str(processed_dir / filepath.name))
                info["moved_to"] = str(processed_dir / filepath.name)
            except Exception as e:
                logger.warning("Could not move %s: %s", filepath.name, e)

        logger.info("New file detected: %s (%s, %d bytes)",
                    filepath.name, doc_type, info["size_bytes"])
        return info

    def _detect_type(self, filepath: Path) -> str:
        """Detektiraj tip dokumenta."""
        fn = filepath.name.lower()
        ext = filepath.suffix.lower()

        if ext in (".sta", ".mt940"):
            return "bank_statement"
        if ext == ".xml":
            try:
                text = filepath.read_text(encoding="utf-8", errors="ignore")[:2000]
                if "Invoice" in text or "Račun" in text:
                    return "e_racun"
            except Exception:
                pass
            return "xml_document"
        if ext == ".csv":
            try:
                text = filepath.read_text(encoding="utf-8", errors="ignore")[:500]
                if any(kw in text.lower() for kw in ["iban", "iznos", "saldo"]):
                    return "bank_statement"
            except Exception:
                pass
            return "csv_data"

        # PDF/images
        if any(kw in fn for kw in ["racun", "račun", "invoice", "faktura"]):
            return "invoice_scan"
        if any(kw in fn for kw in ["izvod", "statement", "izvadak"]):
            return "bank_statement"
        if any(kw in fn for kw in ["putni", "nalog", "travel"]):
            return "putni_nalog"
        if any(kw in fn for kw in ["ios", "usklađ", "usklad"]):
            return "ios_form"
        if any(kw in fn for kw in ["blagajn", "gotov", "cash"]):
            return "blagajna"
        return "invoice_scan"

    def _iter_files(self, folder: Path):
        """Iteriraj datoteke (bez subdirektorija s podvlakom)."""
        for item in folder.iterdir():
            if item.is_file() and not item.name.startswith("."):
                yield item
            elif item.is_dir() and not item.name.startswith("_") and not item.name.startswith("."):
                yield from self._iter_files(item)

    @staticmethod
    def _file_hash(filepath: Path) -> str:
        """Brzi hash (size + mtime) za detekciju promjena."""
        stat = filepath.stat()
        return f"{stat.st_size}_{stat.st_mtime}"

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "running": self._running,
            "watch_paths": [str(p) for p in self.watch_paths],
            "known_files": len(self._known_files),
        }
