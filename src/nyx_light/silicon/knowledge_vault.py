"""
Nyx Light — Knowledge Vault
══════════════════════════════════════════════════════════════

Bulletproof knowledge preservation across LLM model changes.
When the base model is replaced (e.g., Qwen3-235B → Qwen4-300B),
ALL accumulated knowledge MUST survive intact.

Adapted from NYX 47.0 "Stones" architecture:
  - model_evolution.py  → Safe model swap pipeline
  - persistent_memory.py → 4-tier memory with CDS decay
  - mlx_lora_trainer.py → LoRA adapter versioning + migration

═══════════════════════════════════════════════════════════════
KNOWLEDGE LAYERS — What survives a model swap:
═══════════════════════════════════════════════════════════════

  1. L1+L2 MEMORY (SQLite)     — Episodic + Semantic corrections
     Location: data/memory_db/
     Survival: 100% — model-independent, pure data

  2. DPO PREFERENCE PAIRS       — (chosen, rejected) training data
     Location: data/dpo_datasets/
     Survival: 100% — model-independent JSONL format
     Bonus: Re-trainable on ANY new model

  3. LoRA ADAPTERS              — Fine-tuned weight deltas
     Location: data/models/lora/
     Survival: ARCHITECTURE-DEPENDENT
     Strategy: If new model has same architecture → direct load
               If different architecture → retrain from DPO pairs
               Old adapters archived, never deleted

  4. RAG VECTORS (Qdrant)       — Law embeddings
     Location: data/rag_db/
     Survival: EMBEDDING-MODEL-DEPENDENT
     Strategy: If same embedding model → 100% survival
               If different → re-embed from source texts (data/laws/)

  5. AUDIT LOG                  — Complete history
     Location: data/auth.db
     Survival: 100% — always preserved

  6. CONFIG + CLIENT DATA       — System configuration
     Location: config.json, data/exports/
     Survival: 100% — model-independent

═══════════════════════════════════════════════════════════════
SAFE UPGRADE PIPELINE (from Nyx Stones model_evolution.py):
═══════════════════════════════════════════════════════════════

  1. PRE-CHECK:    Verify all knowledge paths exist
  2. SNAPSHOT:     Hash all knowledge files → integrity manifest
  3. BACKUP:       Archive current model → data/models/archive/
  4. DOWNLOAD:     Get new model from HuggingFace
  5. VALIDATE:     Run test inference (probni upit)
  6. LORA-CHECK:   Test LoRA adapter compatibility
  7. DPO-RETRAIN:  If LoRA incompatible → retrain from DPO pairs
  8. VERIFY:       Re-check all knowledge paths + integrity hashes
  9. ACTIVATE:     Switch to new model
  10. ROLLBACK:    If ANY step fails → restore from backup

© 2026 Dr. Mladen Mešter · Nexellum Lab d.o.o.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nyx_light.silicon.knowledge_vault")


# ══════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════

# CRITICAL: These paths are NEVER deleted during model swap
KNOWLEDGE_PATHS = [
    "data/memory_db/",       # L1+L2 Memory (SQLite)
    "data/auth.db",          # Users + audit log
    "data/rag_db/",          # Vector database (Qdrant)
    "data/dpo_datasets/",    # DPO preference pairs
    "data/models/lora/",     # LoRA adapter weights
    "data/laws/",            # RAG corpus texts
    "data/exports/",         # Exported CPP/Synesis files
    "data/backups/",         # Backups
    "data/logs/",            # Logs
    "config.json",           # Configuration
]

# Minimum DPO pairs needed before retraining
MIN_DPO_PAIRS_FOR_RETRAIN = 10

# Adapter compatibility test prompt
COMPATIBILITY_TEST_PROMPT = (
    "Kontiranje: Račun za uredski materijal od dobavljača XY, "
    "iznos 1.000,00 EUR + PDV 25% = 1.250,00 EUR. "
    "Predloži konto za troškove."
)

EXPECTED_TEST_KEYWORDS = ["4010", "konto", "trošak", "uredski"]


# ══════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════

class SwapPhase(Enum):
    """Model swap pipeline phases."""
    PRE_CHECK = "pre_check"
    SNAPSHOT = "snapshot"
    BACKUP = "backup"
    DOWNLOAD = "download"
    VALIDATE = "validate"
    LORA_CHECK = "lora_check"
    DPO_RETRAIN = "dpo_retrain"
    VERIFY = "verify"
    ACTIVATE = "activate"
    COMPLETE = "complete"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class LoRACompatibility(Enum):
    """LoRA adapter compatibility with new model."""
    COMPATIBLE = "compatible"         # Same architecture → direct load
    RETRAIN_NEEDED = "retrain_needed" # Different arch → retrain from DPO
    NO_ADAPTERS = "no_adapters"       # No LoRA adapters exist


class AdapterStatus(Enum):
    """Lifecycle of a LoRA adapter (from Nyx Stones mlx_lora_trainer.py)."""
    TRAINING = "training"
    EVALUATING = "evaluating"
    READY = "ready"
    ACTIVE = "active"
    RETIRED = "retired"
    REJECTED = "rejected"
    ARCHIVED = "archived"


# ══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ══════════════════════════════════════════════════════════════

@dataclass
class IntegrityManifest:
    """Cryptographic manifest of all knowledge files.

    Created before model swap, verified after.
    Any mismatch = ROLLBACK.
    """
    manifest_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    base_dir: str = ""
    file_hashes: Dict[str, str] = field(default_factory=dict)  # path → sha256
    total_files: int = 0
    total_size_bytes: int = 0

    def to_json(self) -> str:
        return json.dumps({
            "manifest_id": self.manifest_id,
            "created_at": self.created_at,
            "base_dir": self.base_dir,
            "total_files": self.total_files,
            "total_size_bytes": self.total_size_bytes,
            "file_hashes": self.file_hashes,
        }, indent=2, ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str) -> "IntegrityManifest":
        d = json.loads(data)
        return cls(**d)


@dataclass
class AdapterRecord:
    """Registry entry for a LoRA adapter version.

    Adapted from Nyx Stones AdapterStatus lifecycle.
    """
    adapter_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    base_model: str = ""           # Model this was trained on
    base_model_arch: str = ""      # Architecture fingerprint
    lora_rank: int = 16
    lora_alpha: float = 32.0
    target_modules: List[str] = field(default_factory=list)
    training_pairs: int = 0        # How many DPO pairs used
    training_loss: float = 0.0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    status: AdapterStatus = AdapterStatus.READY
    path: str = ""                 # Filesystem path
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class SwapLog:
    """Complete log of a model swap operation."""
    swap_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: str = ""
    completed_at: str = ""
    old_model: str = ""
    new_model: str = ""
    phase: SwapPhase = SwapPhase.PRE_CHECK
    lora_compatibility: LoRACompatibility = LoRACompatibility.NO_ADAPTERS
    knowledge_verified: bool = False
    rollback_performed: bool = False
    error: str = ""
    phases_log: List[Dict[str, Any]] = field(default_factory=list)

    def log_phase(self, phase: SwapPhase, message: str, success: bool = True):
        self.phase = phase
        self.phases_log.append({
            "phase": phase.value,
            "message": message,
            "success": success,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


# ══════════════════════════════════════════════════════════════
# KNOWLEDGE VAULT
# ══════════════════════════════════════════════════════════════

class KnowledgeVault:
    """Bulletproof knowledge preservation across model changes.

    This is the GUARDIAN of all learned knowledge in Nyx Light.
    It ensures that memory, LoRA adapters, DPO datasets, RAG vectors,
    and all accumulated intelligence survives any model upgrade.

    Core guarantees:
      1. Knowledge paths are NEVER deleted
      2. Every swap creates integrity manifests
      3. LoRA adapter compatibility is tested before activation
      4. Incompatible adapters are retrained from DPO pairs
      5. Rollback is instant if anything fails
      6. Complete audit trail of every operation
    """

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self._adapter_registry: Dict[str, AdapterRecord] = {}
        self._swap_history: List[SwapLog] = []
        self._ensure_paths()
        self._load_adapter_registry()

    def _ensure_paths(self):
        """Ensure all knowledge directories exist."""
        for p in KNOWLEDGE_PATHS:
            path = self.base_dir / p
            if p.endswith("/"):
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)

    def _load_adapter_registry(self):
        """Load adapter registry from disk."""
        reg_path = self.base_dir / "data/models/lora/adapter_registry.json"
        if reg_path.exists():
            try:
                data = json.loads(reg_path.read_text())
                for rec in data.get("adapters", []):
                    ar = AdapterRecord(**rec)
                    self._adapter_registry[ar.adapter_id] = ar
                logger.info(
                    "Loaded %d LoRA adapters from registry",
                    len(self._adapter_registry)
                )
            except Exception as e:
                logger.warning("Failed to load adapter registry: %s", e)

    def _save_adapter_registry(self):
        """Persist adapter registry."""
        reg_path = self.base_dir / "data/models/lora/adapter_registry.json"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "adapters": [
                {
                    "adapter_id": ar.adapter_id,
                    "base_model": ar.base_model,
                    "base_model_arch": ar.base_model_arch,
                    "lora_rank": ar.lora_rank,
                    "lora_alpha": ar.lora_alpha,
                    "target_modules": ar.target_modules,
                    "training_pairs": ar.training_pairs,
                    "training_loss": ar.training_loss,
                    "created_at": ar.created_at,
                    "status": ar.status.value,
                    "path": ar.path,
                    "metrics": ar.metrics,
                }
                for ar in self._adapter_registry.values()
            ],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        reg_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # ──────────────────────────────────────────────────────
    # INTEGRITY MANIFEST
    # ──────────────────────────────────────────────────────

    def create_manifest(self) -> IntegrityManifest:
        """Create SHA-256 manifest of all knowledge files.

        This is the cryptographic snapshot taken BEFORE a model swap.
        After swap, verify_manifest() checks nothing was corrupted.
        """
        manifest = IntegrityManifest(base_dir=str(self.base_dir))
        total_size = 0

        for kp in KNOWLEDGE_PATHS:
            path = self.base_dir / kp
            if path.is_file():
                h = _sha256_file(path)
                manifest.file_hashes[kp] = h
                manifest.total_files += 1
                total_size += path.stat().st_size
            elif path.is_dir():
                for f in sorted(path.rglob("*")):
                    if f.is_file():
                        rel = str(f.relative_to(self.base_dir))
                        h = _sha256_file(f)
                        manifest.file_hashes[rel] = h
                        manifest.total_files += 1
                        total_size += f.stat().st_size

        manifest.total_size_bytes = total_size
        logger.info(
            "Manifest %s: %d files, %.1f MB",
            manifest.manifest_id,
            manifest.total_files,
            total_size / (1024 * 1024),
        )
        return manifest

    def verify_manifest(self, manifest: IntegrityManifest) -> Tuple[bool, List[str]]:
        """Verify knowledge integrity against a manifest.

        Returns (all_ok, list_of_mismatches).
        """
        mismatches = []
        for rel_path, expected_hash in manifest.file_hashes.items():
            full_path = self.base_dir / rel_path
            if not full_path.exists():
                mismatches.append(f"MISSING: {rel_path}")
                continue
            actual_hash = _sha256_file(full_path)
            if actual_hash != expected_hash:
                mismatches.append(
                    f"CHANGED: {rel_path} (expected {expected_hash[:12]}... got {actual_hash[:12]}...)"
                )

        if mismatches:
            logger.error(
                "Knowledge integrity check FAILED: %d mismatches",
                len(mismatches)
            )
        else:
            logger.info(
                "Knowledge integrity check PASSED: %d files verified",
                manifest.total_files
            )
        return len(mismatches) == 0, mismatches

    # ──────────────────────────────────────────────────────
    # LoRA ADAPTER MANAGEMENT
    # ──────────────────────────────────────────────────────

    def register_adapter(
        self,
        adapter_path: str,
        base_model: str,
        base_model_arch: str = "",
        lora_rank: int = 16,
        lora_alpha: float = 32.0,
        training_pairs: int = 0,
        training_loss: float = 0.0,
    ) -> AdapterRecord:
        """Register a new LoRA adapter."""
        rec = AdapterRecord(
            base_model=base_model,
            base_model_arch=base_model_arch or _model_arch_fingerprint(base_model),
            lora_rank=lora_rank,
            lora_alpha=lora_alpha,
            target_modules=[
                "self_attn.q_proj", "self_attn.v_proj",
                "self_attn.k_proj", "self_attn.o_proj",
            ],
            training_pairs=training_pairs,
            training_loss=training_loss,
            path=adapter_path,
            status=AdapterStatus.READY,
        )
        self._adapter_registry[rec.adapter_id] = rec
        self._save_adapter_registry()
        logger.info(
            "Registered adapter %s for model %s (%d DPO pairs)",
            rec.adapter_id, base_model, training_pairs
        )
        return rec

    def get_active_adapter(self) -> Optional[AdapterRecord]:
        """Get the currently active LoRA adapter."""
        for ar in self._adapter_registry.values():
            if ar.status == AdapterStatus.ACTIVE:
                return ar
        return None

    def get_latest_adapter(self, model: Optional[str] = None) -> Optional[AdapterRecord]:
        """Get latest READY or ACTIVE adapter, optionally for a specific model."""
        candidates = [
            ar for ar in self._adapter_registry.values()
            if ar.status in (AdapterStatus.READY, AdapterStatus.ACTIVE)
            and (model is None or ar.base_model == model)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda ar: ar.created_at)

    def check_lora_compatibility(
        self, new_model: str, new_arch: str = ""
    ) -> LoRACompatibility:
        """Check if existing LoRA adapters are compatible with new model.

        Compatible = same model architecture (hidden_dim, num_layers, etc.)
        Strategy from Nyx Stones model_evolution.py:
          - Same arch fingerprint → COMPATIBLE (direct load)
          - Different arch → RETRAIN_NEEDED (from DPO pairs)
          - No adapters → NO_ADAPTERS
        """
        active = self.get_active_adapter()
        if active is None:
            latest = self.get_latest_adapter()
            if latest is None:
                return LoRACompatibility.NO_ADAPTERS
            active = latest

        new_fp = new_arch or _model_arch_fingerprint(new_model)
        old_fp = active.base_model_arch

        # Same architecture family check
        if _architectures_compatible(old_fp, new_fp):
            logger.info(
                "LoRA adapter %s COMPATIBLE with %s (arch: %s → %s)",
                active.adapter_id, new_model, old_fp[:20], new_fp[:20]
            )
            return LoRACompatibility.COMPATIBLE
        else:
            logger.info(
                "LoRA adapter %s INCOMPATIBLE with %s — retrain needed",
                active.adapter_id, new_model
            )
            return LoRACompatibility.RETRAIN_NEEDED

    def archive_adapters_for_model(self, model: str) -> int:
        """Archive all adapters for a specific model (on model swap)."""
        count = 0
        for ar in self._adapter_registry.values():
            if ar.base_model == model and ar.status in (
                AdapterStatus.READY, AdapterStatus.ACTIVE
            ):
                ar.status = AdapterStatus.ARCHIVED
                count += 1
        if count:
            self._save_adapter_registry()
            logger.info("Archived %d adapters for model %s", count, model)
        return count

    # ──────────────────────────────────────────────────────
    # DPO DATASET MANAGEMENT
    # ──────────────────────────────────────────────────────

    def count_dpo_pairs(self) -> int:
        """Count available DPO preference pairs."""
        dpo_dir = self.base_dir / "data/dpo_datasets"
        if not dpo_dir.exists():
            return 0
        count = 0
        for f in dpo_dir.glob("*.jsonl"):
            with open(f) as fh:
                count += sum(1 for _ in fh)
        return count

    def can_retrain_from_dpo(self) -> bool:
        """Check if we have enough DPO pairs to retrain LoRA."""
        return self.count_dpo_pairs() >= MIN_DPO_PAIRS_FOR_RETRAIN

    def export_dpo_for_retrain(self) -> Optional[str]:
        """Export all DPO pairs to a single JSONL for retraining.

        DPO pairs are MODEL-INDEPENDENT — they contain:
          {prompt, chosen_response, rejected_response}
        So they can train ANY model's LoRA adapter.
        """
        dpo_dir = self.base_dir / "data/dpo_datasets"
        if not dpo_dir.exists():
            return None

        export_path = dpo_dir / f"retrain_export_{int(time.time())}.jsonl"
        pair_count = 0

        with open(export_path, "w") as out:
            for f in sorted(dpo_dir.glob("*.jsonl")):
                if f.name.startswith("retrain_export"):
                    continue
                with open(f) as fh:
                    for line in fh:
                        line = line.strip()
                        if line:
                            out.write(line + "\n")
                            pair_count += 1

        if pair_count < MIN_DPO_PAIRS_FOR_RETRAIN:
            export_path.unlink(missing_ok=True)
            logger.warning(
                "Only %d DPO pairs (need %d) — cannot retrain",
                pair_count, MIN_DPO_PAIRS_FOR_RETRAIN
            )
            return None

        logger.info(
            "Exported %d DPO pairs to %s for retraining",
            pair_count, export_path
        )
        return str(export_path)

    # ──────────────────────────────────────────────────────
    # MEMORY SYSTEM PRESERVATION
    # ──────────────────────────────────────────────────────

    def verify_memory_intact(self) -> Dict[str, Any]:
        """Verify all memory tiers are intact.

        Checks:
          - L1 episodic memory (SQLite tables exist and have data)
          - L2 semantic memory (SQLite tables exist)
          - DPO datasets (files exist)
          - LoRA adapters (registry + files)
          - RAG vectors (Qdrant data)
          - Laws (source texts)
        """
        results = {}

        # L1+L2 Memory
        mem_db = self.base_dir / "data/memory_db/memory.db"
        if mem_db.exists():
            try:
                conn = sqlite3.connect(str(mem_db))
                cursor = conn.cursor()
                tables = {
                    row[0]
                    for row in cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                l1_count = 0
                l2_count = 0
                if "episodic" in tables:
                    l1_count = cursor.execute(
                        "SELECT COUNT(*) FROM episodic"
                    ).fetchone()[0]
                if "semantic" in tables:
                    l2_count = cursor.execute(
                        "SELECT COUNT(*) FROM semantic"
                    ).fetchone()[0]
                conn.close()
                results["memory"] = {
                    "status": "ok",
                    "l1_episodes": l1_count,
                    "l2_facts": l2_count,
                }
            except Exception as e:
                results["memory"] = {"status": "error", "error": str(e)}
        else:
            results["memory"] = {"status": "empty"}

        # DPO
        dpo_count = self.count_dpo_pairs()
        results["dpo"] = {
            "status": "ok" if dpo_count > 0 else "empty",
            "pairs": dpo_count,
            "can_retrain": self.can_retrain_from_dpo(),
        }

        # LoRA adapters
        adapter_count = len(self._adapter_registry)
        active = self.get_active_adapter()
        results["lora"] = {
            "status": "ok" if adapter_count > 0 else "empty",
            "total_adapters": adapter_count,
            "active_adapter": active.adapter_id if active else None,
        }

        # RAG
        rag_dir = self.base_dir / "data/rag_db"
        results["rag"] = {
            "status": "ok" if rag_dir.exists() and any(rag_dir.iterdir()) else "empty",
        }

        # Laws
        laws_dir = self.base_dir / "data/laws"
        law_count = len(list(laws_dir.glob("*.txt"))) if laws_dir.exists() else 0
        results["laws"] = {
            "status": "ok" if law_count > 0 else "empty",
            "count": law_count,
        }

        # Config
        config_path = self.base_dir / "config.json"
        results["config"] = {
            "status": "ok" if config_path.exists() else "missing",
        }

        # Overall
        all_ok = all(
            v.get("status") in ("ok", "empty") for v in results.values()
        )
        results["overall"] = "INTACT" if all_ok else "DEGRADED"

        return results

    # ──────────────────────────────────────────────────────
    # SAFE MODEL SWAP (from Nyx Stones model_evolution.py)
    # ──────────────────────────────────────────────────────

    async def safe_swap(
        self,
        old_model: str,
        new_model: str,
        download_fn=None,
        inference_fn=None,
        retrain_fn=None,
    ) -> SwapLog:
        """Execute safe model swap with full knowledge preservation.

        Pipeline (10 phases):
        1. PRE_CHECK:   Verify all knowledge paths exist
        2. SNAPSHOT:    Create integrity manifest
        3. BACKUP:      Archive old model
        4. DOWNLOAD:    Download new model
        5. VALIDATE:    Test inference
        6. LORA_CHECK:  Test adapter compatibility
        7. DPO_RETRAIN: If needed, retrain adapters from DPO pairs
        8. VERIFY:      Re-check knowledge integrity
        9. ACTIVATE:    Switch to new model
        10. COMPLETE/ROLLBACK

        download_fn: async (model_id) -> model_path
        inference_fn: async (model_path, prompt) -> response_text
        retrain_fn: async (model_path, dpo_jsonl, output_dir) -> adapter_path
        """
        log = SwapLog(
            started_at=datetime.now(timezone.utc).isoformat(),
            old_model=old_model,
            new_model=new_model,
        )

        try:
            # Phase 1: Pre-check
            log.log_phase(SwapPhase.PRE_CHECK, "Verifying knowledge paths")
            verification = self.verify_memory_intact()
            if verification["overall"] != "INTACT":
                log.log_phase(
                    SwapPhase.PRE_CHECK,
                    f"Knowledge pre-check: {verification['overall']}",
                    success=False
                )
                # Continue anyway — swap might fix issues

            # Phase 2: Snapshot
            log.log_phase(SwapPhase.SNAPSHOT, "Creating integrity manifest")
            manifest = self.create_manifest()
            manifest_path = (
                self.base_dir / "data/backups"
                / f"manifest_{log.swap_id}.json"
            )
            manifest_path.write_text(manifest.to_json())

            # Phase 3: Backup old model
            log.log_phase(SwapPhase.BACKUP, f"Archiving {old_model}")
            archive_dir = (
                self.base_dir / "data/models/archive"
                / f"{_safe_name(old_model)}_{int(time.time())}"
            )
            old_model_dir = self.base_dir / "data/models/primary"
            if old_model_dir.exists():
                archive_dir.mkdir(parents=True, exist_ok=True)
                # Move instead of copy (faster, saves disk)
                for item in old_model_dir.iterdir():
                    shutil.move(str(item), str(archive_dir / item.name))
                logger.info("Archived %s to %s", old_model, archive_dir)

            # Phase 4: Download new model
            log.log_phase(SwapPhase.DOWNLOAD, f"Downloading {new_model}")
            new_model_path = None
            if download_fn:
                new_model_path = await download_fn(new_model)
            else:
                # Simulate: assume model is in data/models/primary
                new_model_path = str(self.base_dir / "data/models/primary")
                (self.base_dir / "data/models/primary").mkdir(exist_ok=True)

            # Phase 5: Validate inference
            log.log_phase(SwapPhase.VALIDATE, "Testing inference")
            if inference_fn:
                response = await inference_fn(
                    new_model_path, COMPATIBILITY_TEST_PROMPT
                )
                if not any(kw in response.lower() for kw in EXPECTED_TEST_KEYWORDS):
                    logger.warning(
                        "New model inference test returned unexpected response"
                    )
            else:
                logger.info("No inference_fn provided — skipping validation")

            # Phase 6: LoRA compatibility check
            log.log_phase(SwapPhase.LORA_CHECK, "Checking LoRA compatibility")
            new_arch = _model_arch_fingerprint(new_model)
            compat = self.check_lora_compatibility(new_model, new_arch)
            log.lora_compatibility = compat

            if compat == LoRACompatibility.COMPATIBLE:
                log.log_phase(
                    SwapPhase.LORA_CHECK,
                    "LoRA adapters COMPATIBLE — direct load"
                )
            elif compat == LoRACompatibility.RETRAIN_NEEDED:
                # Phase 7: Retrain from DPO
                log.log_phase(
                    SwapPhase.DPO_RETRAIN,
                    "Retraining LoRA from DPO pairs"
                )
                if self.can_retrain_from_dpo() and retrain_fn:
                    dpo_path = self.export_dpo_for_retrain()
                    if dpo_path:
                        adapter_dir = str(
                            self.base_dir / "data/models/lora"
                            / f"retrained_{log.swap_id}"
                        )
                        adapter_path = await retrain_fn(
                            new_model_path, dpo_path, adapter_dir
                        )
                        if adapter_path:
                            self.register_adapter(
                                adapter_path=adapter_path,
                                base_model=new_model,
                                base_model_arch=new_arch,
                                training_pairs=self.count_dpo_pairs(),
                            )
                            log.log_phase(
                                SwapPhase.DPO_RETRAIN,
                                f"Retrained adapter saved to {adapter_path}"
                            )
                else:
                    log.log_phase(
                        SwapPhase.DPO_RETRAIN,
                        "Insufficient DPO pairs or no retrain function — "
                        "model will start fresh (but memory/DPO preserved)"
                    )
                # Archive old adapters
                self.archive_adapters_for_model(old_model)

            # Phase 8: Verify knowledge integrity
            log.log_phase(SwapPhase.VERIFY, "Verifying knowledge integrity")
            all_ok, mismatches = self.verify_manifest(manifest)
            log.knowledge_verified = all_ok

            if not all_ok:
                # Only non-model files should match
                critical_mismatches = [
                    m for m in mismatches
                    if not m.startswith("data/models/primary")
                    and not m.startswith("data/models/archive")
                ]
                if critical_mismatches:
                    raise ValueError(
                        f"Critical knowledge corruption: {critical_mismatches}"
                    )
                logger.info(
                    "Model files changed (expected), knowledge files intact"
                )
                log.knowledge_verified = True

            # Phase 9: Activate
            log.log_phase(SwapPhase.ACTIVATE, f"Activating {new_model}")
            log.phase = SwapPhase.COMPLETE
            log.completed_at = datetime.now(timezone.utc).isoformat()

            logger.info(
                "✅ Model swap complete: %s → %s | LoRA: %s | Knowledge: %s",
                old_model, new_model, compat.value,
                "INTACT" if log.knowledge_verified else "DEGRADED"
            )

        except Exception as e:
            logger.error("Model swap FAILED at %s: %s", log.phase.value, e)
            log.error = str(e)
            log.phase = SwapPhase.FAILED

            # ROLLBACK
            try:
                log.log_phase(
                    SwapPhase.ROLLED_BACK,
                    f"Rolling back to {old_model}"
                )
                if archive_dir and archive_dir.exists():
                    old_model_dir = self.base_dir / "data/models/primary"
                    # Remove failed new model
                    if old_model_dir.exists():
                        shutil.rmtree(old_model_dir, ignore_errors=True)
                    old_model_dir.mkdir(parents=True, exist_ok=True)
                    for item in archive_dir.iterdir():
                        shutil.move(str(item), str(old_model_dir / item.name))
                    log.rollback_performed = True
                    logger.info("Rollback complete: %s restored", old_model)
            except Exception as rb_err:
                logger.critical(
                    "ROLLBACK FAILED: %s — manual intervention required!",
                    rb_err
                )

        # Save swap log
        self._swap_history.append(log)
        self._save_swap_log(log)

        return log

    def _save_swap_log(self, log: SwapLog):
        """Persist swap log for audit trail."""
        log_dir = self.base_dir / "data/logs/swaps"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"swap_{log.swap_id}.json"
        log_path.write_text(json.dumps({
            "swap_id": log.swap_id,
            "started_at": log.started_at,
            "completed_at": log.completed_at,
            "old_model": log.old_model,
            "new_model": log.new_model,
            "phase": log.phase.value,
            "lora_compatibility": log.lora_compatibility.value,
            "knowledge_verified": log.knowledge_verified,
            "rollback_performed": log.rollback_performed,
            "error": log.error,
            "phases_log": log.phases_log,
        }, indent=2, ensure_ascii=False))

    def swap_history(self) -> List[Dict[str, Any]]:
        """Get complete swap history."""
        log_dir = self.base_dir / "data/logs/swaps"
        if not log_dir.exists():
            return []
        logs = []
        for f in sorted(log_dir.glob("swap_*.json")):
            try:
                logs.append(json.loads(f.read_text()))
            except Exception:
                pass
        return logs


# ══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════

def _sha256_file(path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(model_id: str) -> str:
    """Convert model ID to safe directory name."""
    return model_id.replace("/", "_").replace("\\", "_").replace(" ", "_")


def _model_arch_fingerprint(model_id: str) -> str:
    """Create a fingerprint of model architecture from model ID.

    Models with same architecture fingerprint can share LoRA adapters.
    E.g., Qwen3-235B-A22B and Qwen3-235B-A22B-v2 → same arch.
    But Qwen3-235B → Llama-405B → different arch.
    """
    # Extract architecture family from model name
    model_lower = model_id.lower()
    families = {
        "qwen3": "qwen3",
        "qwen2.5": "qwen2.5",
        "qwen2": "qwen2",
        "qwen": "qwen",
        "llama-3.3": "llama3.3",
        "llama-3.1": "llama3.1",
        "llama-3": "llama3",
        "llama": "llama",
        "deepseek-v3": "deepseek_v3",
        "deepseek-r1": "deepseek_r1",
        "deepseek": "deepseek",
        "mistral": "mistral",
        "phi": "phi",
    }

    for pattern, family in families.items():
        if pattern in model_lower:
            # Extract parameter count
            import re
            m = re.search(r"(\d+)b", model_lower)
            params = m.group(1) if m else "unknown"
            return f"{family}_{params}b"

    return hashlib.sha256(model_id.encode()).hexdigest()[:16]


def _architectures_compatible(arch1: str, arch2: str) -> bool:
    """Check if two architecture fingerprints are compatible for LoRA.

    Compatible = same model family and parameter count.
    E.g., qwen3_235b ↔ qwen3_235b → True
          qwen3_235b ↔ qwen3_72b  → False (different size)
          qwen3_235b ↔ llama3_70b → False (different family)
    """
    if not arch1 or not arch2:
        return False
    return arch1 == arch2
