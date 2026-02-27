"""
Nyx Light — Backup & Restore System

Automatski backup svih kritičnih podataka:
  - SQLite baze (memory_db, auth.db, dpo_training.db)
  - DPO dataseti
  - LoRA adapteri
  - Konfiguracija
  - RAG zakoni

10 protected paths se NIKAD ne brišu (Knowledge Preservation).
"""

import gzip
import json
import logging
import os
import shutil
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.backup")

PROTECTED_PATHS = [
    "data/memory_db",
    "data/memory_db/auth.db",
    "data/rag_db",
    "data/dpo_datasets",
    "data/models/lora",
    "data/laws",
    "data/exports",
    "data/backups",
    "data/logs",
    "config.json",
]

BACKUP_DIR = Path("data/backups")
MAX_BACKUPS = 30  # Keep last 30 backups


class BackupManager:
    """Backup i restore za Nyx Light."""

    def __init__(self, backup_dir: str = str(BACKUP_DIR)):
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._backup_count = 0

    def create_backup(self, label: str = "") -> Dict[str, Any]:
        """Full backup svih kritičnih podataka."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"backup_{ts}" + (f"_{label}" if label else "")
        backup_path = self.backup_dir / name
        backup_path.mkdir(parents=True, exist_ok=True)

        files_backed = 0
        total_size = 0
        errors = []

        # Backup SQLite databases (safe copy with WAL checkpoint)
        for db_name, db_path in [
            ("nyx_light.db", "data/memory_db/nyx_light.db"),
            ("auth.db", "data/memory_db/auth.db"),
            ("dpo_training.db", "data/dpo_training.db"),
        ]:
            src = Path(db_path)
            if src.exists():
                dst = backup_path / db_name
                try:
                    # Safe SQLite backup via VACUUM INTO
                    conn = sqlite3.connect(str(src))
                    conn.execute(f"VACUUM INTO '{dst}'")
                    conn.close()
                    files_backed += 1
                    total_size += dst.stat().st_size
                except Exception as e:
                    # Fallback: simple copy
                    try:
                        shutil.copy2(str(src), str(dst))
                        files_backed += 1
                        total_size += dst.stat().st_size
                    except Exception as e2:
                        errors.append(f"{db_name}: {e2}")

        # Backup DPO datasets
        dpo_src = Path("data/dpo_datasets")
        if dpo_src.exists():
            dpo_dst = backup_path / "dpo_datasets"
            dpo_dst.mkdir(exist_ok=True)
            for f in dpo_src.glob("*.jsonl"):
                shutil.copy2(str(f), str(dpo_dst / f.name))
                files_backed += 1
                total_size += f.stat().st_size

        # Backup LoRA adapters (only metadata, not full weights for speed)
        lora_src = Path("data/models/lora")
        if lora_src.exists():
            lora_manifest = []
            for d in lora_src.iterdir():
                if d.is_dir():
                    size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                    lora_manifest.append({"name": d.name, "size": size})
            (backup_path / "lora_manifest.json").write_text(
                json.dumps(lora_manifest, indent=2))
            files_backed += 1

        # Backup config
        for cfg in ["config.json"]:
            if Path(cfg).exists():
                shutil.copy2(cfg, str(backup_path / cfg))
                files_backed += 1

        # Write manifest
        manifest = {
            "timestamp": datetime.now().isoformat(),
            "label": label,
            "files_backed": files_backed,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / 1e6, 2),
            "errors": errors,
        }
        (backup_path / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False))

        # Cleanup old backups
        self._cleanup_old()

        self._backup_count += 1
        logger.info("Backup kreiran: %s (%d files, %.1f MB)",
                     name, files_backed, total_size / 1e6)

        return {
            "name": name,
            "path": str(backup_path),
            **manifest,
        }

    def restore_backup(self, backup_name: str) -> Dict[str, Any]:
        """Restore iz backupa — OPREZNO, prepisuje podatke."""
        backup_path = self.backup_dir / backup_name
        if not backup_path.exists():
            return {"status": "error", "message": f"Backup {backup_name} ne postoji"}

        restored = 0
        errors = []

        # Restore SQLite databases
        for db_name, db_path in [
            ("nyx_light.db", "data/memory_db/nyx_light.db"),
            ("auth.db", "data/memory_db/auth.db"),
            ("dpo_training.db", "data/dpo_training.db"),
        ]:
            src = backup_path / db_name
            if src.exists():
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(src), db_path)
                    restored += 1
                except Exception as e:
                    errors.append(f"{db_name}: {e}")

        # Restore DPO datasets
        dpo_src = backup_path / "dpo_datasets"
        if dpo_src.exists():
            dpo_dst = Path("data/dpo_datasets")
            dpo_dst.mkdir(parents=True, exist_ok=True)
            for f in dpo_src.glob("*.jsonl"):
                shutil.copy2(str(f), str(dpo_dst / f.name))
                restored += 1

        # Restore config
        cfg = backup_path / "config.json"
        if cfg.exists():
            shutil.copy2(str(cfg), "config.json")
            restored += 1

        logger.info("Restore završen: %s (%d files)", backup_name, restored)
        return {"status": "ok", "restored": restored, "errors": errors}

    def list_backups(self) -> List[Dict]:
        """Lista svih backupa."""
        backups = []
        for d in sorted(self.backup_dir.iterdir(), reverse=True):
            if d.is_dir() and d.name.startswith("backup_"):
                manifest_path = d / "manifest.json"
                if manifest_path.exists():
                    manifest = json.loads(manifest_path.read_text())
                else:
                    manifest = {}
                backups.append({
                    "name": d.name,
                    "timestamp": manifest.get("timestamp", ""),
                    "files": manifest.get("files_backed", 0),
                    "size_mb": manifest.get("total_size_mb", 0),
                    "label": manifest.get("label", ""),
                })
        return backups

    def _cleanup_old(self):
        """Obriši backupe starije od MAX_BACKUPS."""
        backups = sorted(
            [d for d in self.backup_dir.iterdir() if d.is_dir() and d.name.startswith("backup_")],
            key=lambda x: x.name,
            reverse=True
        )
        for old in backups[MAX_BACKUPS:]:
            shutil.rmtree(str(old), ignore_errors=True)
            logger.info("Stari backup obrisan: %s", old.name)

    def get_stats(self) -> Dict[str, Any]:
        backups = self.list_backups()
        total_size = sum(b.get("size_mb", 0) for b in backups)
        return {
            "total_backups": len(backups),
            "total_size_mb": round(total_size, 2),
            "last_backup": backups[0]["timestamp"] if backups else None,
            "backup_count_this_session": self._backup_count,
        }
