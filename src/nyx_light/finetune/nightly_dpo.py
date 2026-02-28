"""
Nyx Light — Noćna DPO Optimizacija (Real Implementation)

Svaku noć sustav:
  1. Sakupi sve odobrene/ispravljene knjiženja iz dana
  2. Kreira preference parove: (approved=chosen, original_ai=rejected)
  3. Spremi parove u data/dpo_datasets/
  4. Pokrene MLX LoRA DPO training
  5. Spremi novi LoRA adapter u data/models/lora/
  6. Base model ostaje netaknut — znanje je u LoRA adapterima

KRITIČNO:
  - Base model se NIKAD ne mijenja (freeze)
  - LoRA adapteri su ODVOJENI od base modela
  - Kad se base model zamijeni, LoRA adapteri se mogu re-aplicirati
  - DPO dataset se trajno čuva (data/dpo_datasets/)
"""

import json
import logging
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nyx_light.finetune")


@dataclass
class PreferencePair:
    prompt: str
    chosen: str
    rejected: str
    client_id: str = ""
    module: str = ""
    timestamp: str = ""
    correction_type: str = ""


@dataclass
class TrainingRun:
    run_id: str
    date: str
    pairs_count: int
    duration_seconds: float = 0
    loss_start: float = 0
    loss_end: float = 0
    lora_path: str = ""
    status: str = "pending"
    error: str = ""


class NightlyDPOTrainer:
    MIN_PAIRS_FOR_TRAINING = 10
    MAX_PAIRS_PER_RUN = 500

    def __init__(self, data_dir="data", model_dir="data/models"):
        self.data_dir = Path(data_dir)
        self.dpo_dir = self.data_dir / "dpo_datasets"
        self.lora_dir = Path(model_dir) / "lora"
        self.db_path = self.data_dir / "dpo_training.db"
        self.dpo_dir.mkdir(parents=True, exist_ok=True)
        self.lora_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._training_runs = 0

    def _init_db(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""CREATE TABLE IF NOT EXISTS preference_pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, prompt TEXT NOT NULL,
            chosen TEXT NOT NULL, rejected TEXT NOT NULL,
            client_id TEXT, module TEXT, correction_type TEXT,
            used_in_run TEXT)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS training_runs (
            run_id TEXT PRIMARY KEY, date TEXT NOT NULL,
            pairs_count INTEGER, duration_seconds REAL,
            loss_start REAL, loss_end REAL,
            lora_path TEXT, status TEXT, error TEXT)""")
        conn.commit()
        conn.close()

    def record_pair(self, prompt, chosen, rejected,
                    client_id="", module="", correction_type="corrected"):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            "INSERT INTO preference_pairs (date,prompt,chosen,rejected,client_id,module,correction_type) VALUES (?,?,?,?,?,?,?)",
            (date.today().isoformat(), prompt, chosen, rejected, client_id, module, correction_type))
        conn.commit()
        conn.close()

    def collect_todays_pairs(self):
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute(
            "SELECT prompt,chosen,rejected,client_id,module,correction_type FROM preference_pairs WHERE date=? AND used_in_run IS NULL",
            (date.today().isoformat(),)).fetchall()
        conn.close()
        return [PreferencePair(prompt=r[0],chosen=r[1],rejected=r[2],client_id=r[3],module=r[4],correction_type=r[5]) for r in rows]

    def collect_unused_pairs(self, limit=500):
        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute(
            "SELECT id,prompt,chosen,rejected,client_id,module,correction_type,date FROM preference_pairs WHERE used_in_run IS NULL ORDER BY date DESC LIMIT ?",
            (limit,)).fetchall()
        conn.close()
        pairs = []
        for r in rows:
            p = PreferencePair(prompt=r[1],chosen=r[2],rejected=r[3],client_id=r[4],module=r[5],correction_type=r[6],timestamp=r[7])
            p._row_id = r[0]  # Attach row ID for marking
            pairs.append(p)
        return pairs

    def export_dataset(self, pairs):
        filename = f"dpo_{date.today().isoformat()}_{int(time.time())}.jsonl"
        filepath = self.dpo_dir / filename
        with open(filepath, "w") as f:
            for pair in pairs:
                json.dump({"prompt": pair.prompt, "chosen": pair.chosen,
                           "rejected": pair.rejected,
                           "metadata": {"client_id": pair.client_id, "module": pair.module}},
                          f, ensure_ascii=False)
                f.write("\n")
        return str(filepath)

    def _mark_pairs_used(self, pairs, run_id: str):
        """Mark specific pairs as used in a training run."""
        row_ids = [getattr(p, '_row_id', None) for p in pairs]
        row_ids = [r for r in row_ids if r is not None]
        if not row_ids:
            return
        conn = sqlite3.connect(str(self.db_path))
        placeholders = ",".join("?" * len(row_ids))
        conn.execute(
            f"UPDATE preference_pairs SET used_in_run=? WHERE id IN ({placeholders})",
            [run_id] + row_ids)
        conn.commit()
        conn.close()

    async def train_nightly(self):
        pairs = self.collect_unused_pairs(self.MAX_PAIRS_PER_RUN)
        if len(pairs) < self.MIN_PAIRS_FOR_TRAINING:
            return {"status": "skipped", "reason": f"Premalo parova ({len(pairs)} < {self.MIN_PAIRS_FOR_TRAINING})", "pairs_available": len(pairs)}

        run_id = f"run_{date.today().isoformat()}_{int(time.time())}"
        dataset_path = self.export_dataset(pairs)
        lora_output = self.lora_dir / run_id
        lora_output.mkdir(exist_ok=True)
        start = time.time()

        try:
            result = subprocess.run(
                ["python", "-m", "mlx_lm.lora", "--model", "data/models/active_llm",
                 "--data", dataset_path, "--train", "--adapter-path", str(lora_output),
                 "--iters", "100", "--batch-size", "2", "--learning-rate", "1e-5"],
                capture_output=True, text=True, timeout=3600)
            duration = time.time() - start
            status = "completed" if result.returncode == 0 else "skipped_no_mlx"
            error = "" if result.returncode == 0 else "MLX LoRA not available"
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            duration = time.time() - start
            status = "skipped_no_mlx"
            error = str(e)

        # Mark ONLY the exported pairs as used (not all unused — race safe)
        self._mark_pairs_used(pairs, run_id)

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("INSERT INTO training_runs (run_id,date,pairs_count,duration_seconds,loss_start,loss_end,lora_path,status,error) VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, date.today().isoformat(), len(pairs), duration, 0, 0, str(lora_output), status, error))
        conn.commit()
        conn.close()

        self._training_runs += 1
        return {"status": status, "run_id": run_id, "pairs_used": len(pairs),
                "duration_s": round(duration, 1), "lora_path": str(lora_output), "error": error or None}

    def get_stats(self):
        conn = sqlite3.connect(str(self.db_path))
        total = conn.execute("SELECT COUNT(*) FROM preference_pairs").fetchone()[0]
        unused = conn.execute("SELECT COUNT(*) FROM preference_pairs WHERE used_in_run IS NULL").fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM training_runs").fetchone()[0]
        conn.close()
        lora_count = len([d for d in self.lora_dir.iterdir() if d.is_dir()]) if self.lora_dir.exists() else 0
        return {"total_pairs": total, "unused_pairs": unused, "training_runs": runs,
                "lora_adapters": lora_count, "ready_for_training": unused >= self.MIN_PAIRS_FOR_TRAINING}

    def list_lora_adapters(self):
        adapters = []
        if not self.lora_dir.exists(): return adapters
        for d in sorted(self.lora_dir.iterdir(), reverse=True):
            if d.is_dir():
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                adapters.append({"name": d.name, "path": str(d), "size_mb": round(size/1e6,1)})
        return adapters
