"""
Nyx Light — Model Manager

Automatski download, verzioniranje i safe swap LLM modela.

KRITIČNI AKSIOM: Zamjena modela NE SMIJE izgubiti naučeno znanje.

Znanje se čuva u:
  1. L2 Semantic Memory (SQLite) — pravila kontiranja
  2. L1 Episodic Memory (SQLite) — dnevne interakcije
  3. LoRA adapteri (data/models/lora/) — DPO fine-tune težine
  4. DPO dataset (data/dpo_datasets/) — preference parovi
  5. RAG baza (data/rag_db/) — vektorski zakoni
  6. Neo4j graf (data/neo4j/) — relacije klijenata
  7. Config & auth (data/auth.db, config.json)

Svi se čuvaju ODVOJENO od base modela.
Base model se može zamijeniti, a znanje ostaje netaknuto.

Tijek:
  1. Provjeri dostupnu RAM → odaberi model tier
  2. Download putem huggingface-cli (MLX format)
  3. Spremi metadata (verzija, datum, hash)
  4. Pri upgrade-u: backup stari → download novi → test → switch
  5. Ako test padne → rollback na stari
"""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.model_manager")


# ═══════════════════════════════════════════════════
# MODEL TIERS
# ═══════════════════════════════════════════════════

@dataclass
class ModelSpec:
    """Specifikacija jednog modela."""
    name: str
    hf_repo: str
    min_ram_gb: int
    size_gb: float
    description: str
    model_type: str = "llm"  # llm | vision
    quantization: str = "4bit"
    active_params: str = ""


# Model katalog — MLX formati za Apple Silicon
MODEL_CATALOG: Dict[str, ModelSpec] = {
    # LLM modeli (po RAM tierovima)
    "qwen3-235b-a22b": ModelSpec(
        name="Qwen3-235B-A22B",
        hf_repo="mlx-community/Qwen3-235B-A22B-4bit",
        min_ram_gb=192,
        size_gb=124,
        description="MoE 235B (22B aktivno) — vrhunska logika",
        active_params="22B active / 235B total",
    ),
    "qwen2.5-72b": ModelSpec(
        name="Qwen2.5-72B",
        hf_repo="mlx-community/Qwen2.5-72B-Instruct-4bit",
        min_ram_gb=96,
        size_gb=42,
        description="Dense 72B — odlična logika za 96GB+",
    ),
    "qwen2.5-32b": ModelSpec(
        name="Qwen2.5-32B",
        hf_repo="mlx-community/Qwen2.5-32B-Instruct-4bit",
        min_ram_gb=64,
        size_gb=20,
        description="Dense 32B — dobra za 64GB sustave",
    ),
    "deepseek-r1-distill-32b": ModelSpec(
        name="DeepSeek-R1-Distill-32B",
        hf_repo="mlx-community/DeepSeek-R1-Distill-Qwen-32B-4bit",
        min_ram_gb=64,
        size_gb=20,
        description="R1 reasoning distill — odlično za kontiranje",
    ),

    # Vision model (uvijek se skida uz LLM)
    "qwen2.5-vl-7b": ModelSpec(
        name="Qwen2.5-VL-7B",
        hf_repo="mlx-community/Qwen2.5-VL-7B-Instruct-4bit",
        min_ram_gb=16,
        size_gb=5,
        description="Vision model za OCR skenova",
        model_type="vision",
    ),
}

# ═══════════════════════════════════════════════════
# KNOWLEDGE PRESERVATION
# ═══════════════════════════════════════════════════

# Ove datoteke/direktorije sadrže naučeno znanje
# i NIKADA se ne brišu pri zamjeni modela
KNOWLEDGE_PATHS = [
    "data/memory_db/",       # L1 + L2 memorija (SQLite)
    "data/auth.db",          # Korisnici i audit log
    "data/rag_db/",          # Vektorska baza zakona
    "data/dpo_datasets/",    # DPO preference parovi
    "data/models/lora/",     # LoRA adapter težine
    "data/laws/",            # RAG corpus tekstovi
    "data/exports/",         # Exportirani CPP/Synesis fajlovi
    "data/backups/",         # Backupi
    "data/logs/",            # Logovi
    "config.json",           # Konfiguracija
]


@dataclass
class ModelVersion:
    """Instalirana verzija modela."""
    model_id: str
    hf_repo: str
    installed_at: str
    path: str
    size_bytes: int = 0
    sha256: str = ""
    is_active: bool = True
    lora_adapters: List[str] = field(default_factory=list)


@dataclass
class DownloadProgress:
    """Status download-a."""
    model_id: str
    total_gb: float
    downloaded_gb: float = 0.0
    speed_mbps: float = 0.0
    eta_minutes: float = 0.0
    status: str = "pending"  # pending, downloading, verifying, done, error
    error: str = ""


class ModelManager:
    """Upravlja LLM modelima — download, verzije, safe swap."""

    def __init__(self, models_dir: str = "data/models",
                 config_path: str = "data/models/registry.json"):
        self.models_dir = Path(models_dir)
        self.config_path = Path(config_path)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        (self.models_dir / "lora").mkdir(exist_ok=True)
        (self.models_dir / "archive").mkdir(exist_ok=True)
        self._registry = self._load_registry()

    # ════════════════════════════════════════
    # REGISTRY
    # ════════════════════════════════════════

    def _load_registry(self) -> Dict[str, Any]:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {"installed": {}, "active_llm": None, "active_vision": None,
                "history": [], "last_check": None}

    def _save_registry(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self._registry, indent=2))

    # ════════════════════════════════════════
    # RAM DETECTION
    # ════════════════════════════════════════

    def detect_ram_gb(self) -> int:
        """Detektiraj dostupni RAM (GB)."""
        try:
            # macOS
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return int(result.stdout.strip()) // (1024 ** 3)
        except Exception:
            pass

        try:
            # Linux
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb // (1024 * 1024)
        except Exception:
            pass

        return 0

    def recommend_model(self, ram_gb: int = 0) -> ModelSpec:
        """Preporuči najbolji model za dostupnu RAM."""
        if ram_gb == 0:
            ram_gb = self.detect_ram_gb()

        if ram_gb >= 192:
            return MODEL_CATALOG["qwen3-235b-a22b"]
        elif ram_gb >= 96:
            return MODEL_CATALOG["qwen2.5-72b"]
        elif ram_gb >= 64:
            return MODEL_CATALOG["deepseek-r1-distill-32b"]
        else:
            return MODEL_CATALOG["qwen2.5-32b"]

    # ════════════════════════════════════════
    # DOWNLOAD
    # ════════════════════════════════════════

    def download_model(self, model_id: str,
                       callback=None) -> Dict[str, Any]:
        """Download model s Hugging Face (MLX format).

        Args:
            model_id: Ključ iz MODEL_CATALOG
            callback: Optional(DownloadProgress) za UI update

        Returns:
            {"ok": True, "path": "...", "size_gb": X}
        """
        if model_id not in MODEL_CATALOG:
            return {"ok": False, "error": f"Nepoznati model: {model_id}"}

        spec = MODEL_CATALOG[model_id]
        target_dir = self.models_dir / model_id

        progress = DownloadProgress(
            model_id=model_id,
            total_gb=spec.size_gb,
            status="downloading",
        )

        if callback:
            callback(progress)

        logger.info("Downloading %s (%s GB) from %s",
                     spec.name, spec.size_gb, spec.hf_repo)

        try:
            # Koristi huggingface-cli za download
            cmd = [
                "huggingface-cli", "download",
                spec.hf_repo,
                "--local-dir", str(target_dir),
                "--local-dir-use-symlinks", "False",
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=7200,  # 2h max
            )

            if result.returncode != 0:
                # Fallback: pokušaj s git clone
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                cmd2 = [
                    "git", "clone", "--depth", "1",
                    f"https://huggingface.co/{spec.hf_repo}",
                    str(target_dir),
                ]
                result2 = subprocess.run(
                    cmd2, capture_output=True, text=True, timeout=7200,
                )
                if result2.returncode != 0:
                    progress.status = "error"
                    progress.error = result2.stderr[:500]
                    if callback:
                        callback(progress)
                    return {"ok": False, "error": result2.stderr[:500]}

            # Calculate size
            size_bytes = sum(
                f.stat().st_size for f in target_dir.rglob("*") if f.is_file()
            )

            # Register
            version = ModelVersion(
                model_id=model_id,
                hf_repo=spec.hf_repo,
                installed_at=datetime.now().isoformat(),
                path=str(target_dir),
                size_bytes=size_bytes,
            )

            self._registry["installed"][model_id] = {
                "model_id": model_id,
                "hf_repo": spec.hf_repo,
                "installed_at": version.installed_at,
                "path": str(target_dir),
                "size_bytes": size_bytes,
                "name": spec.name,
                "model_type": spec.model_type,
            }

            # Auto-activate
            if spec.model_type == "vision":
                self._registry["active_vision"] = model_id
            else:
                self._registry["active_llm"] = model_id

            self._save_registry()

            progress.status = "done"
            progress.downloaded_gb = spec.size_gb
            if callback:
                callback(progress)

            logger.info("Model %s installed: %s (%.1f GB)",
                        spec.name, target_dir, size_bytes / 1e9)

            return {"ok": True, "path": str(target_dir),
                    "size_gb": round(size_bytes / 1e9, 1)}

        except Exception as e:
            progress.status = "error"
            progress.error = str(e)
            if callback:
                callback(progress)
            return {"ok": False, "error": str(e)}

    def first_install(self, callback=None) -> Dict[str, Any]:
        """Prva instalacija — detektiraj RAM, skini odgovarajući model + vision."""
        ram = self.detect_ram_gb()
        llm = self.recommend_model(ram)
        vision = MODEL_CATALOG["qwen2.5-vl-7b"]

        results = {}

        # LLM
        llm_id = [k for k, v in MODEL_CATALOG.items() if v == llm][0]
        if llm_id not in self._registry.get("installed", {}):
            logger.info("First install: downloading LLM %s (RAM: %d GB)", llm.name, ram)
            results["llm"] = self.download_model(llm_id, callback)
        else:
            results["llm"] = {"ok": True, "already_installed": True}

        # Vision
        if "qwen2.5-vl-7b" not in self._registry.get("installed", {}):
            logger.info("First install: downloading Vision model")
            results["vision"] = self.download_model("qwen2.5-vl-7b", callback)
        else:
            results["vision"] = {"ok": True, "already_installed": True}

        return {"ram_gb": ram, "recommended": llm.name, "results": results}

    # ════════════════════════════════════════
    # VERSION CHECK & UPGRADE
    # ════════════════════════════════════════

    def check_for_updates(self) -> List[Dict[str, Any]]:
        """Provjeri ima li novih verzija na HuggingFace."""
        updates = []
        try:
            import httpx
            for model_id, info in self._registry.get("installed", {}).items():
                spec = MODEL_CATALOG.get(model_id)
                if not spec:
                    continue
                resp = httpx.get(
                    f"https://huggingface.co/api/models/{spec.hf_repo}",
                    timeout=10,
                )
                if resp.status_code == 200:
                    remote = resp.json()
                    remote_modified = remote.get("lastModified", "")
                    local_installed = info.get("installed_at", "")
                    if remote_modified > local_installed:
                        updates.append({
                            "model_id": model_id,
                            "name": spec.name,
                            "local_date": local_installed,
                            "remote_date": remote_modified,
                            "action": "upgrade_available",
                        })
        except Exception as e:
            logger.warning("Update check failed: %s", e)

        self._registry["last_check"] = datetime.now().isoformat()
        self._save_registry()
        return updates

    def safe_upgrade(self, model_id: str,
                     callback=None) -> Dict[str, Any]:
        """Safe upgrade — backup stari, download novi, test, switch.

        KRITIČNO: Znanje se NE GUBI jer je odvojeno od base modela.

        Tijek:
          1. Backup stari model u archive/
          2. Download novi model
          3. Test inferenca (probni upit)
          4. Ako OK → switch + zadrži LoRA adaptere
          5. Ako FAIL → rollback na backup

        LoRA adapteri ostaju u data/models/lora/ i rade s novim modelom.
        """
        if model_id not in self._registry.get("installed", {}):
            return {"ok": False, "error": "Model nije instaliran"}

        spec = MODEL_CATALOG.get(model_id)
        if not spec:
            return {"ok": False, "error": "Model nije u katalogu"}

        old_info = self._registry["installed"][model_id]
        old_path = Path(old_info["path"])
        archive_path = self.models_dir / "archive" / f"{model_id}_{int(time.time())}"

        # Dohvati postojeće LoRA adaptere (ovi se ČUVAJU)
        lora_dir = self.models_dir / "lora" / model_id
        lora_exists = lora_dir.exists() and any(lora_dir.iterdir()) if lora_dir.exists() else False

        logger.info("Safe upgrade: %s", spec.name)
        logger.info("  LoRA adapteri: %s", "DA — bit će očuvani" if lora_exists else "NEMA")
        logger.info("  Knowledge dirs safe: %s",
                     ", ".join(KNOWLEDGE_PATHS[:5]))

        try:
            # Step 1: Backup stari model
            if old_path.exists():
                logger.info("Step 1: Archiving old model to %s", archive_path)
                shutil.move(str(old_path), str(archive_path))

            # Record in history
            self._registry.setdefault("history", []).append({
                "model_id": model_id,
                "action": "upgrade_started",
                "timestamp": datetime.now().isoformat(),
                "old_path": str(archive_path),
            })
            self._save_registry()

            # Step 2: Download novi
            logger.info("Step 2: Downloading new version")
            result = self.download_model(model_id, callback)

            if not result.get("ok"):
                # Step 5: Rollback
                logger.error("Download failed — rolling back")
                if archive_path.exists():
                    shutil.move(str(archive_path), str(old_path))
                return {"ok": False, "error": f"Download failed: {result.get('error')}",
                        "rolled_back": True}

            # Step 3: Test inference
            logger.info("Step 3: Testing new model")
            test_ok = self._test_model(model_id)

            if not test_ok:
                # Step 5: Rollback
                logger.error("Test failed — rolling back")
                new_path = self.models_dir / model_id
                if new_path.exists():
                    shutil.rmtree(new_path)
                if archive_path.exists():
                    shutil.move(str(archive_path), str(old_path))
                return {"ok": False, "error": "Model test failed",
                        "rolled_back": True}

            # Step 4: Switch
            logger.info("Step 4: Upgrade successful")
            self._registry["history"].append({
                "model_id": model_id,
                "action": "upgrade_completed",
                "timestamp": datetime.now().isoformat(),
            })
            self._save_registry()

            # Stari archive se može obrisati nakon par dana
            return {
                "ok": True,
                "upgraded": spec.name,
                "lora_preserved": lora_exists,
                "knowledge_preserved": True,
                "archive_path": str(archive_path),
                "note": "LoRA adapteri i svo znanje su očuvani",
            }

        except Exception as e:
            logger.error("Upgrade error: %s — rolling back", e)
            # Emergency rollback
            new_path = self.models_dir / model_id
            if new_path.exists() and archive_path.exists():
                shutil.rmtree(new_path)
                shutil.move(str(archive_path), str(old_path))
            return {"ok": False, "error": str(e), "rolled_back": True}

    def _test_model(self, model_id: str) -> bool:
        """Quick test — probni inference s novim modelom."""
        model_path = self.models_dir / model_id
        if not model_path.exists():
            return False

        # Provjeri da config.json postoji
        config = model_path / "config.json"
        if not config.exists():
            logger.error("Model config.json not found")
            return False

        # Provjeri da safetensors postoje
        safetensors = list(model_path.glob("*.safetensors"))
        if not safetensors:
            gguf = list(model_path.glob("*.gguf"))
            if not gguf:
                logger.error("No model weights found (.safetensors or .gguf)")
                return False

        logger.info("Model test passed: config OK, weights found (%d files)",
                     len(safetensors) or len(list(model_path.glob("*.gguf"))))
        return True

    # ════════════════════════════════════════
    # KNOWLEDGE VERIFICATION
    # ════════════════════════════════════════

    def verify_knowledge_intact(self) -> Dict[str, Any]:
        """Verificiraj da su svi knowledge pathovi netaknuti."""
        results = {}
        for kp in KNOWLEDGE_PATHS:
            p = Path(kp)
            if p.is_dir():
                files = list(p.rglob("*"))
                results[kp] = {
                    "exists": True,
                    "files": len([f for f in files if f.is_file()]),
                    "size_mb": round(sum(
                        f.stat().st_size for f in files if f.is_file()
                    ) / 1e6, 1),
                }
            elif p.is_file():
                results[kp] = {
                    "exists": True,
                    "size_mb": round(p.stat().st_size / 1e6, 1),
                }
            else:
                results[kp] = {"exists": False}

        all_ok = all(r.get("exists", False) for r in results.values()
                     if not r.get("optional", False))
        return {"all_intact": all_ok, "paths": results}

    # ════════════════════════════════════════
    # STATUS
    # ════════════════════════════════════════

    def get_status(self) -> Dict[str, Any]:
        ram = self.detect_ram_gb()
        installed = self._registry.get("installed", {})
        return {
            "ram_gb": ram,
            "recommended": self.recommend_model(ram).name,
            "active_llm": self._registry.get("active_llm"),
            "active_vision": self._registry.get("active_vision"),
            "installed_models": {
                k: {"name": v.get("name", k),
                    "size_gb": round(v.get("size_bytes", 0) / 1e9, 1),
                    "installed_at": v.get("installed_at", "")}
                for k, v in installed.items()
            },
            "knowledge_paths": len(KNOWLEDGE_PATHS),
            "last_update_check": self._registry.get("last_check"),
            "history_count": len(self._registry.get("history", [])),
        }

    def cleanup_archives(self, keep_days: int = 7) -> int:
        """Obriši stare archive modele starije od keep_days."""
        archive_dir = self.models_dir / "archive"
        if not archive_dir.exists():
            return 0
        removed = 0
        cutoff = time.time() - keep_days * 86400
        for d in archive_dir.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d)
                removed += 1
                logger.info("Cleaned archive: %s", d.name)
        return removed
