#!/usr/bin/env python3
"""
Nyx Light — Backup sustav

Noćni backup svih podataka:
- SQLite baza (bookings, corrections, audit)
- L2 semantic memory
- DPO datasets
- Config

Backup je lokalni (NAS/external disk) jer su podaci povjerljivi (OIB, plaće).
NIKADA cloud backup.

Korištenje:
    python -m scripts.backup
    python -m scripts.backup --dest /Volumes/NAS/nyx-backup
    
Cron (svaki dan u 03:00):
    0 3 * * * cd /opt/nyx-light && /opt/nyx-light/venv/bin/python -m scripts.backup
"""

import argparse
import gzip
import logging
import os
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [BACKUP] %(message)s")
logger = logging.getLogger("nyx_light.backup")

# Što backupiramo
BACKUP_SOURCES = [
    "data/memory_db",       # SQLite baze
    "data/dpo_datasets",    # DPO preference parovi
    "data/exports",         # ERP exporti (zadnjih 30 dana)
    "data/laws/_index.json", # RAG indeks
    "config",               # Konfiguracija
]

# Koliko backupa zadržati
MAX_BACKUPS = 30


def create_backup(
    source_dir: str = ".",
    dest_dir: str = "data/backups",
    compress: bool = True,
) -> Dict:
    """Kreiraj backup."""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"nyx_light_backup_{timestamp}"
    dest_path = Path(dest_dir)
    dest_path.mkdir(parents=True, exist_ok=True)
    
    backup_dir = dest_path / backup_name
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    stats = {
        "timestamp": timestamp,
        "files_copied": 0,
        "total_size_mb": 0,
        "errors": [],
    }
    
    logger.info("═══ Nyx Light Backup: %s ═══", timestamp)
    
    for source in BACKUP_SOURCES:
        src = Path(source_dir) / source
        if not src.exists():
            logger.info("  Preskačem (ne postoji): %s", source)
            continue
        
        if src.is_file():
            dst = backup_dir / source
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            stats["files_copied"] += 1
        elif src.is_dir():
            dst = backup_dir / source
            try:
                shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
                file_count = sum(1 for _ in dst.rglob("*") if _.is_file())
                stats["files_copied"] += file_count
                logger.info("  ✅ %s → %d datoteka", source, file_count)
            except Exception as e:
                logger.error("  ❌ %s: %s", source, e)
                stats["errors"].append(str(e))
    
    # SQLite hot backup (safe copy while DB is in use)
    db_path = Path(source_dir) / "data/memory_db/nyx_light.db"
    if db_path.exists():
        try:
            backup_db = backup_dir / "data/memory_db/nyx_light.db"
            backup_db.parent.mkdir(parents=True, exist_ok=True)
            
            src_conn = sqlite3.connect(str(db_path))
            dst_conn = sqlite3.connect(str(backup_db))
            src_conn.backup(dst_conn)
            src_conn.close()
            dst_conn.close()
            logger.info("  ✅ SQLite hot backup uspješan")
        except Exception as e:
            logger.error("  ❌ SQLite backup: %s", e)
            stats["errors"].append(str(e))
    
    # Compress
    archive_path = None
    if compress:
        archive_path = str(dest_path / f"{backup_name}.tar.gz")
        shutil.make_archive(
            str(dest_path / backup_name), "gztar", str(dest_path), backup_name
        )
        shutil.rmtree(str(backup_dir))
        
        size_mb = os.path.getsize(archive_path) / (1024 * 1024)
        stats["total_size_mb"] = round(size_mb, 2)
        stats["archive"] = archive_path
        logger.info("  📦 Komprimirano: %.1f MB", size_mb)
    else:
        size = sum(f.stat().st_size for f in backup_dir.rglob("*") if f.is_file())
        stats["total_size_mb"] = round(size / (1024 * 1024), 2)
        stats["archive"] = str(backup_dir)
    
    # Cleanup starih backupa
    cleanup_old_backups(dest_dir, MAX_BACKUPS)
    
    logger.info("═══ Backup završen: %d datoteka, %.1f MB ═══",
                stats["files_copied"], stats["total_size_mb"])
    
    return stats


def cleanup_old_backups(dest_dir: str, keep: int = MAX_BACKUPS):
    """Obriši stare backupe (zadrži zadnjih N)."""
    dest = Path(dest_dir)
    backups = sorted(dest.glob("nyx_light_backup_*"), key=lambda p: p.name)
    
    if len(backups) > keep:
        to_delete = backups[:len(backups) - keep]
        for old in to_delete:
            if old.is_file():
                old.unlink()
            elif old.is_dir():
                shutil.rmtree(str(old))
            logger.info("  🗑️  Obrisan stari backup: %s", old.name)


def main():
    parser = argparse.ArgumentParser(description="Nyx Light — Backup")
    parser.add_argument("--dest", default="data/backups", help="Odredišni direktorij")
    parser.add_argument("--no-compress", action="store_true", help="Ne komprimiraj")
    parser.add_argument("--keep", type=int, default=30, help="Broj backupa za čuvanje")
    args = parser.parse_args()
    
    global MAX_BACKUPS
    MAX_BACKUPS = args.keep
    
    create_backup(
        source_dir=".",
        dest_dir=args.dest,
        compress=not args.no_compress,
    )


if __name__ == "__main__":
    main()
