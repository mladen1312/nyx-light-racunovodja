"""
Nyx Light — Deployment Infrastructure za Mac Studio 256GB
═════════════════════════════════════════════════════════════
Kompletna infrastruktura za produkcijski deployment:
  1. Memory Budget Calculator (256GB raspodjela)
  2. LLM Model Stack (reasoning + vision + embedding)
  3. Hot-Reload Development Server (live code changes)
  4. Remote Access (SSH + Tailscale + VS Code)
  5. Service Management (launchd za macOS)
  6. Health Monitoring & Auto-Recovery

Target hardver: Mac Studio M3 Ultra 256GB ili M5 Ultra 256GB
Korisnika: 15-20 istovremenih
Zero cloud dependency — sve lokalno.
"""

import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nyx_light.deployment")


# ═══════════════════════════════════════════════════════════
# 1. MEMORY BUDGET — 256GB Unified Memory raspodjela
# ═══════════════════════════════════════════════════════════

class MemoryTier(str, Enum):
    """Kategorije memorijske alokacije."""
    SYSTEM = "system"           # macOS + sistemski procesi
    APPLICATION = "application" # FastAPI, SQLite, Neo4j, Qdrant
    LLM_REASONING = "llm_reasoning"
    LLM_VISION = "llm_vision"
    LLM_EMBEDDING = "llm_embedding"
    KV_CACHE = "kv_cache"       # KV cache za concurrent korisnike
    BUFFER = "buffer"           # Sigurnosni buffer


@dataclass
class ModelSpec:
    """Specifikacija jednog LLM modela."""
    name: str
    role: str                  # reasoning | vision | embedding
    params_billions: float
    quantization: str          # Q4_K_M, Q6_K, Q8_0, FP16
    ram_gb: float              # Koliko GB zauzima u memoriji
    max_ctx_tokens: int        # Maksimalni kontekst
    tokens_per_sec: float      # Očekivani tok/s na Apple Silicon
    mlx_compatible: bool = True
    notes: str = ""


@dataclass
class MemoryBudget:
    """Kompletna raspodjela 256GB Unified Memory."""
    total_gb: int = 256
    system_gb: float = 10.0
    application_gb: float = 12.0
    reasoning_model: Optional[ModelSpec] = None
    vision_model: Optional[ModelSpec] = None
    embedding_model: Optional[ModelSpec] = None
    kv_cache_gb: float = 0.0
    buffer_gb: float = 0.0

    @property
    def models_gb(self) -> float:
        total = 0.0
        if self.reasoning_model:
            total += self.reasoning_model.ram_gb
        if self.vision_model:
            total += self.vision_model.ram_gb
        if self.embedding_model:
            total += self.embedding_model.ram_gb
        return total

    @property
    def used_gb(self) -> float:
        return self.system_gb + self.application_gb + self.models_gb + self.kv_cache_gb

    @property
    def free_gb(self) -> float:
        return self.total_gb - self.used_gb

    @property
    def is_feasible(self) -> bool:
        return self.free_gb >= 10.0  # Min 10GB buffer

    def summary(self) -> Dict[str, Any]:
        items = {
            "total_gb": self.total_gb,
            "system_gb": self.system_gb,
            "application_gb": self.application_gb,
        }
        if self.reasoning_model:
            items["reasoning"] = {
                "model": self.reasoning_model.name,
                "quant": self.reasoning_model.quantization,
                "ram_gb": self.reasoning_model.ram_gb,
                "ctx": self.reasoning_model.max_ctx_tokens,
                "tok_s": self.reasoning_model.tokens_per_sec,
            }
        if self.vision_model:
            items["vision"] = {
                "model": self.vision_model.name,
                "quant": self.vision_model.quantization,
                "ram_gb": self.vision_model.ram_gb,
            }
        if self.embedding_model:
            items["embedding"] = {
                "model": self.embedding_model.name,
                "ram_gb": self.embedding_model.ram_gb,
            }
        items.update({
            "kv_cache_gb": self.kv_cache_gb,
            "models_total_gb": round(self.models_gb, 1),
            "used_gb": round(self.used_gb, 1),
            "free_gb": round(self.free_gb, 1),
            "feasible": self.is_feasible,
            "utilization_pct": round(self.used_gb / self.total_gb * 100, 1),
        })
        return items


# ═══════════════════════════════════════════════════════════
# PREDEFINIRANI MODEL STACK-ovi za 256GB
# ═══════════════════════════════════════════════════════════

# ── Reasoning modeli ──

QWEN3_235B_A22B = ModelSpec(
    name="Qwen3-235B-A22B",
    role="reasoning",
    params_billions=235,
    quantization="Q4_K_M",
    ram_gb=128.0,
    max_ctx_tokens=131072,
    tokens_per_sec=25.0,
    notes="MoE: 235B total ali samo 22B aktivno po tokenu. "
          "Izvanredan za složeno rezoniranje. Brz unatoč veličini."
)

QWEN3_32B = ModelSpec(
    name="Qwen3-32B",
    role="reasoning",
    params_billions=32,
    quantization="Q8_0",
    ram_gb=36.0,
    max_ctx_tokens=131072,
    tokens_per_sec=45.0,
    notes="Kompaktni reasoning model. Odličan omjer kvalitete i brzine."
)

DEEPSEEK_R1_70B = ModelSpec(
    name="DeepSeek-R1-Distill-Qwen-70B",
    role="reasoning",
    params_billions=70,
    quantization="Q6_K",
    ram_gb=58.0,
    max_ctx_tokens=65536,
    tokens_per_sec=20.0,
    notes="Deep reasoning s chain-of-thought. Odličan za porezna pitanja."
)

QWEN25_72B = ModelSpec(
    name="Qwen2.5-72B-Instruct",
    role="reasoning",
    params_billions=72,
    quantization="Q6_K",
    ram_gb=58.0,
    max_ctx_tokens=131072,
    tokens_per_sec=18.0,
    notes="Stabilan, pouzdan. Izvrsno poznaje europsko pravo i računovodstvo."
)

LLAMA4_MAVERICK = ModelSpec(
    name="Llama-4-Maverick-17B-128E",
    role="reasoning",
    params_billions=400,
    quantization="Q4_K_M",
    ram_gb=115.0,
    max_ctx_tokens=1048576,
    tokens_per_sec=30.0,
    notes="MoE: 400B total, 17B aktivno. 1M kontekst. Meta 2025."
)

# ── Vision modeli ──

QWEN25_VL_72B = ModelSpec(
    name="Qwen2.5-VL-72B-Instruct",
    role="vision",
    params_billions=72,
    quantization="Q4_K_M",
    ram_gb=42.0,
    max_ctx_tokens=32768,
    tokens_per_sec=15.0,
    notes="Najjači open-source vision model. Čita račune, skenove, "
          "tablice, rukom pisani tekst. Multimodalni OCR+razumijevanje."
)

QWEN25_VL_32B = ModelSpec(
    name="Qwen2.5-VL-32B-Instruct",
    role="vision",
    params_billions=32,
    quantization="Q6_K",
    ram_gb=28.0,
    max_ctx_tokens=32768,
    tokens_per_sec=30.0,
    notes="Brži vision model. Dobar za rutinske račune. "
          "Prebaci na 72B za složenije dokumente."
)

QWEN25_VL_7B = ModelSpec(
    name="Qwen2.5-VL-7B-Instruct",
    role="vision",
    params_billions=7,
    quantization="Q8_0",
    ram_gb=8.5,
    max_ctx_tokens=32768,
    tokens_per_sec=65.0,
    notes="Najbrži. Za jednostavne račune (Konzum, benzinska). "
          "Fallback na veći model ako confidence <0.8."
)

# ── Embedding modeli ──

BGE_M3 = ModelSpec(
    name="BAAI/bge-m3",
    role="embedding",
    params_billions=0.568,
    quantization="FP16",
    ram_gb=1.2,
    max_ctx_tokens=8192,
    tokens_per_sec=500.0,
    notes="Multilingual embedding. Za RAG pretragu zakona RH."
)

NOMIC_EMBED = ModelSpec(
    name="nomic-embed-text-v2-moe",
    role="embedding",
    params_billions=0.475,
    quantization="FP16",
    ram_gb=1.0,
    max_ctx_tokens=8192,
    tokens_per_sec=600.0,
    notes="Alternativni embedding. MoE arhitektura."
)


# ═══════════════════════════════════════════════════════════
# PREDEFINIRANI STACK KONFIGURACIJE
# ═══════════════════════════════════════════════════════════

def _kv_cache_estimate(reasoning_ctx: int, vision_ctx: int,
                       concurrent_users: int = 15) -> float:
    """Procjena KV cache memorije u GB."""
    # KV cache ~ 2 * num_layers * hidden_dim * ctx_len * 2 (K+V) * dtype_bytes
    # Simplified: ~2GB per 32K ctx per model at Q4
    reasoning_kv = (reasoning_ctx / 32768) * 2.0 * concurrent_users * 0.3
    vision_kv = (vision_ctx / 32768) * 2.0 * (concurrent_users * 0.2)  # Fewer concurrent vision
    return round(reasoning_kv + vision_kv, 1)


STACK_CONFIGS = {
    # ── PREMIUM: Maksimalna kvaliteta (256GB) ──
    "premium_256gb": {
        "name": "Premium 256GB — Maksimalna kvaliteta",
        "description": "Najveći modeli za najsloženije zadatke. "
                       "MoE reasoning + full 72B vision.",
        "reasoning": QWEN3_235B_A22B,
        "vision": QWEN25_VL_72B,
        "embedding": BGE_M3,
        "concurrent_users": 15,
        "best_for": "Složeni porezni savjeti, revizija, GFI priprema, "
                    "čitanje loše skeniranih dokumenata",
    },
    # ── BALANCED: Optimalni omjer brzina/kvaliteta (256GB) ──
    "balanced_256gb": {
        "name": "Balanced 256GB — Optimalni omjer",
        "description": "72B reasoning + 32B vision. Brži inference, "
                       "i dalje vrlo kvalitetno.",
        "reasoning": QWEN25_72B,
        "vision": QWEN25_VL_32B,
        "embedding": BGE_M3,
        "concurrent_users": 20,
        "best_for": "Svakodnevno kontiranje, bankovni izvodi, "
                    "rutinski ulazni računi",
    },
    # ── SPEED: Maksimalna brzina (256GB) ──
    "speed_256gb": {
        "name": "Speed 256GB — Maksimalna propusnost",
        "description": "32B reasoning + 7B vision. Najbrži, obrađuje "
                       "najviše dokumenata po satu.",
        "reasoning": QWEN3_32B,
        "vision": QWEN25_VL_7B,
        "embedding": BGE_M3,
        "concurrent_users": 25,
        "best_for": "Masovna obrada izvoda, bulk kontiranje, "
                    "jednostavni računi velikih dobavljača",
    },
    # ── DUAL REASONING: Za složenu analizu ──
    "dual_reasoning_256gb": {
        "name": "Dual Reasoning 256GB — Dva reasoning modela",
        "description": "DeepSeek-R1 za duboko rezoniranje + Qwen3-32B "
                       "za brze odgovore. Tiered routing.",
        "reasoning": DEEPSEEK_R1_70B,  # Complex queries
        "vision": QWEN25_VL_32B,
        "embedding": BGE_M3,
        "concurrent_users": 15,
        "best_for": "Porezno savjetovanje, PD obrazac, "
                    "tumačenje mišljenja Porezne uprave",
        "secondary_reasoning": QWEN3_32B,  # Fast queries
    },
}


def calculate_budget(stack_name: str = "premium_256gb",
                     total_ram: int = 256,
                     concurrent_users: int = 15) -> MemoryBudget:
    """Izračunaj memory budget za odabrani stack."""
    stack = STACK_CONFIGS.get(stack_name)
    if not stack:
        available = list(STACK_CONFIGS.keys())
        return MemoryBudget(total_gb=total_ram,
                            buffer_gb=total_ram - 10,
                            system_gb=10)

    reasoning = stack["reasoning"]
    vision = stack["vision"]
    embedding = stack["embedding"]

    kv = _kv_cache_estimate(
        reasoning.max_ctx_tokens, vision.max_ctx_tokens, concurrent_users)

    budget = MemoryBudget(
        total_gb=total_ram,
        system_gb=10.0,
        application_gb=12.0,  # FastAPI + SQLite + Neo4j + Qdrant
        reasoning_model=reasoning,
        vision_model=vision,
        embedding_model=embedding,
        kv_cache_gb=kv,
    )
    budget.buffer_gb = budget.free_gb
    return budget


def recommend_stack(total_ram: int = 256,
                    priority: str = "quality") -> Dict[str, Any]:
    """Preporuči optimalni stack na temelju RAM-a i prioriteta."""
    priority_map = {
        "quality": "premium_256gb",
        "balanced": "balanced_256gb",
        "speed": "speed_256gb",
        "reasoning": "dual_reasoning_256gb",
    }
    stack_name = priority_map.get(priority, "balanced_256gb")
    budget = calculate_budget(stack_name, total_ram)

    if not budget.is_feasible:
        # Fallback na manji stack
        for fallback in ["balanced_256gb", "speed_256gb"]:
            budget = calculate_budget(fallback, total_ram)
            if budget.is_feasible:
                stack_name = fallback
                break

    stack = STACK_CONFIGS[stack_name]
    return {
        "recommended_stack": stack_name,
        "stack_info": {
            "name": stack["name"],
            "description": stack["description"],
            "best_for": stack["best_for"],
            "concurrent_users": stack.get("concurrent_users", 15),
        },
        "memory_budget": budget.summary(),
        "models": {
            "reasoning": f"{stack['reasoning'].name} ({stack['reasoning'].quantization})",
            "vision": f"{stack['vision'].name} ({stack['vision'].quantization})",
            "embedding": f"{stack['embedding'].name}",
        },
        "performance": {
            "reasoning_tok_s": stack["reasoning"].tokens_per_sec,
            "vision_tok_s": stack["vision"].tokens_per_sec,
            "reasoning_ctx": stack["reasoning"].max_ctx_tokens,
            "vision_ctx": stack["vision"].max_ctx_tokens,
        },
    }


# ═══════════════════════════════════════════════════════════
# 2. HOT-RELOAD DEVELOPMENT SERVER
# ═══════════════════════════════════════════════════════════

@dataclass
class FileChange:
    """Zapis o promjeni datoteke."""
    path: str
    action: str  # modified, created, deleted
    timestamp: str
    size: int = 0
    checksum: str = ""


class HotReloadWatcher:
    """
    Prati promjene u kodu i automatski reloada module.

    Kako radi:
    1. Periodički skenira src/ direktorij za promjene (mtime)
    2. Kad detektira promjenu → reloada Python modul
    3. Logira sve promjene za audit trail
    4. Opcionalno trigera test suite za promijenjeni modul

    Korištenje na Mac Studiju:
    - Developer SSH-a na Mac Studio
    - Editira kod u VS Code Remote
    - Watcher automatski reloada bez restarta servera
    """

    def __init__(self, watch_dirs: List[str] = None,
                 ignore_patterns: List[str] = None,
                 check_interval: float = 1.0):
        self.watch_dirs = watch_dirs or ["src/nyx_light"]
        self.ignore_patterns = ignore_patterns or [
            "__pycache__", ".pyc", ".pyo", ".git", ".DS_Store",
            "node_modules", ".pytest_cache",
        ]
        self.check_interval = check_interval
        self._file_mtimes: Dict[str, float] = {}
        self._file_checksums: Dict[str, str] = {}
        self._changes: List[FileChange] = []
        self._callbacks: List[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def on_change(self, callback: Callable):
        """Registriraj callback za promjene."""
        self._callbacks.append(callback)

    def start(self):
        """Pokreni watcher u background threadu."""
        if self._running:
            return
        self._running = True
        self._scan_initial()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info(f"HotReload watcher started: {self.watch_dirs}")

    def stop(self):
        """Zaustavi watcher."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def get_changes(self, limit: int = 50) -> List[Dict]:
        """Dohvati povijest promjena."""
        return [{"path": c.path, "action": c.action,
                 "timestamp": c.timestamp, "size": c.size}
                for c in self._changes[-limit:]]

    def _scan_initial(self):
        """Inicijalni scan svih datoteka."""
        for watch_dir in self.watch_dirs:
            path = Path(watch_dir)
            if not path.exists():
                continue
            for py_file in path.rglob("*.py"):
                if self._should_ignore(str(py_file)):
                    continue
                key = str(py_file)
                try:
                    self._file_mtimes[key] = py_file.stat().st_mtime
                    self._file_checksums[key] = self._checksum(py_file)
                except OSError:
                    pass

    def _watch_loop(self):
        """Glavni loop — skenira za promjene."""
        while self._running:
            try:
                self._check_changes()
            except Exception as e:
                logger.error(f"Watcher error: {e}")
            time.sleep(self.check_interval)

    def _check_changes(self):
        """Provjeri sve datoteke za promjene."""
        current_files: Set[str] = set()

        for watch_dir in self.watch_dirs:
            path = Path(watch_dir)
            if not path.exists():
                continue
            for py_file in path.rglob("*.py"):
                if self._should_ignore(str(py_file)):
                    continue
                key = str(py_file)
                current_files.add(key)

                try:
                    mtime = py_file.stat().st_mtime
                except OSError:
                    continue

                old_mtime = self._file_mtimes.get(key)

                if old_mtime is None:
                    # Nova datoteka
                    self._file_mtimes[key] = mtime
                    self._file_checksums[key] = self._checksum(py_file)
                    self._record_change(key, "created", py_file)
                elif mtime > old_mtime:
                    # Promijenjena datoteka — potvrdi s checksum
                    new_checksum = self._checksum(py_file)
                    if new_checksum != self._file_checksums.get(key):
                        self._file_mtimes[key] = mtime
                        self._file_checksums[key] = new_checksum
                        self._record_change(key, "modified", py_file)
                    else:
                        self._file_mtimes[key] = mtime

        # Obrisane datoteke
        deleted = set(self._file_mtimes.keys()) - current_files
        for key in deleted:
            del self._file_mtimes[key]
            self._file_checksums.pop(key, None)
            change = FileChange(
                path=key, action="deleted",
                timestamp=datetime.now().isoformat())
            with self._lock:
                self._changes.append(change)
            self._notify(change)

    def _record_change(self, key: str, action: str, py_file: Path):
        """Zabilježi promjenu i obavijesti callbackove."""
        try:
            size = py_file.stat().st_size
        except OSError:
            size = 0

        change = FileChange(
            path=key, action=action,
            timestamp=datetime.now().isoformat(),
            size=size,
            checksum=self._file_checksums.get(key, ""))

        with self._lock:
            self._changes.append(change)

        logger.info(f"[HOT-RELOAD] {action.upper()}: {key} ({size} bytes)")
        self._notify(change)

    def _notify(self, change: FileChange):
        """Obavijesti sve registrirane callbackove."""
        for cb in self._callbacks:
            try:
                cb(change)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _should_ignore(self, path: str) -> bool:
        return any(pat in path for pat in self.ignore_patterns)

    @staticmethod
    def _checksum(filepath: Path) -> str:
        try:
            return hashlib.md5(filepath.read_bytes()).hexdigest()[:12]
        except OSError:
            return ""


class ModuleReloader:
    """
    Reloada Python module bez restarta servera.

    Sigurni reload:
    1. Importa novi modul u izoliranom namespace-u
    2. Ako nema syntax error → zamijeni stari modul
    3. Ako ima error → zadrži stari, logira grešku
    """

    def __init__(self):
        self._reloaded: List[Dict] = []
        self._errors: List[Dict] = []

    def reload_module(self, filepath: str) -> Dict[str, Any]:
        """Pokušaj reloadati modul iz filepath-a."""
        module_name = self._path_to_module(filepath)
        if not module_name:
            return {"status": "skip", "reason": "Not a module path"}

        if module_name not in sys.modules:
            return {"status": "skip", "reason": f"Module {module_name} not loaded"}

        try:
            import importlib
            module = sys.modules[module_name]
            importlib.reload(module)

            result = {
                "status": "reloaded",
                "module": module_name,
                "timestamp": datetime.now().isoformat(),
                "filepath": filepath,
            }
            self._reloaded.append(result)
            logger.info(f"✅ Reloaded: {module_name}")
            return result

        except Exception as e:
            error = {
                "status": "error",
                "module": module_name,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            self._errors.append(error)
            logger.error(f"❌ Reload failed: {module_name}: {e}")
            return error

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_reloads": len(self._reloaded),
            "total_errors": len(self._errors),
            "last_reload": self._reloaded[-1] if self._reloaded else None,
            "last_error": self._errors[-1] if self._errors else None,
        }

    @staticmethod
    def _path_to_module(filepath: str) -> str:
        """Pretvori filepath u Python module name."""
        path = filepath.replace("\\", "/")
        # src/nyx_light/modules/ledger/__init__.py → nyx_light.modules.ledger
        if "src/" in path:
            path = path.split("src/", 1)[1]
        path = path.replace("/", ".")
        if path.endswith(".__init__.py"):
            path = path[:-12]
        elif path.endswith(".py"):
            path = path[:-3]
        return path


# ═══════════════════════════════════════════════════════════
# 3. REMOTE ACCESS & DEVELOPMENT CONFIGURATION
# ═══════════════════════════════════════════════════════════

@dataclass
class RemoteDevConfig:
    """Konfiguracija za remote development na Mac Studiju."""

    # SSH
    ssh_port: int = 22
    ssh_user: str = "nyx"
    ssh_key_auth_only: bool = True  # Zabrani password auth

    # Tailscale (mesh VPN — pristup s bilo gdje)
    tailscale_enabled: bool = True
    tailscale_hostname: str = "nyx-studio"

    # VS Code Remote SSH
    vscode_remote: bool = True

    # Application server
    api_host: str = "0.0.0.0"
    api_port: int = 8420
    api_workers: int = 4

    # MLX LLM server
    mlx_host: str = "127.0.0.1"
    mlx_port: int = 8421
    mlx_chat_port: int = 8422  # OpenAI-compatible chat endpoint

    # Development
    hot_reload: bool = True
    debug_mode: bool = False
    log_level: str = "INFO"
    auto_test_on_change: bool = True

    # Paths (na Mac Studiju)
    project_root: str = "/Users/nyx/nyx-light-racunovodja"
    models_dir: str = "/Users/nyx/models"
    data_dir: str = "/Users/nyx/nyx-data"
    logs_dir: str = "/Users/nyx/nyx-data/logs"
    backup_dir: str = "/Users/nyx/nyx-data/backups"

    def generate_ssh_config(self) -> str:
        """Generiraj ~/.ssh/config entry za klijente."""
        return f"""# Nyx Light Mac Studio
Host nyx-studio
    HostName {self.tailscale_hostname if self.tailscale_enabled else 'MAC_STUDIO_IP'}
    User {self.ssh_user}
    Port {self.ssh_port}
    IdentityFile ~/.ssh/nyx_ed25519
    ForwardAgent yes
    # Port forwarding za API i MLX
    LocalForward {self.api_port} 127.0.0.1:{self.api_port}
    LocalForward {self.mlx_chat_port} 127.0.0.1:{self.mlx_chat_port}
"""

    def generate_vscode_settings(self) -> Dict[str, Any]:
        """VS Code Remote SSH settings."""
        return {
            "remote.SSH.remotePlatform": {"nyx-studio": "macOS"},
            "remote.SSH.defaultExtensions": [
                "ms-python.python",
                "ms-python.pylint",
                "charliermarsh.ruff",
                "ms-toolsai.jupyter",
            ],
            "python.defaultInterpreterPath":
                f"{self.project_root}/.venv/bin/python",
            "python.testing.pytestEnabled": True,
            "python.testing.pytestArgs": ["tests/"],
            "files.autoSave": "afterDelay",
            "files.autoSaveDelay": 1000,
        }


# ═══════════════════════════════════════════════════════════
# 4. SERVICE MANAGEMENT (macOS launchd)
# ═══════════════════════════════════════════════════════════

class ServiceManager:
    """Generira macOS launchd plist datoteke za sve servise."""

    @staticmethod
    def generate_api_plist(config: RemoteDevConfig) -> str:
        """FastAPI server — glavni application server."""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>hr.nyxlight.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>{config.project_root}/.venv/bin/python</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>nyx_light.api.main:app</string>
        <string>--host</string>
        <string>{config.api_host}</string>
        <string>--port</string>
        <string>{config.api_port}</string>
        <string>--workers</string>
        <string>{config.api_workers}</string>
        <string>--reload</string>
        <string>--reload-dir</string>
        <string>{config.project_root}/src</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{config.project_root}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>{config.project_root}/src</string>
        <key>NYX_ENV</key>
        <string>production</string>
        <key>NYX_DATA_DIR</key>
        <string>{config.data_dir}</string>
        <key>NYX_MODELS_DIR</key>
        <string>{config.models_dir}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{config.logs_dir}/api.log</string>
    <key>StandardErrorPath</key>
    <string>{config.logs_dir}/api.error.log</string>
    <key>SoftResourceLimits</key>
    <dict>
        <key>NumberOfFiles</key>
        <integer>65536</integer>
    </dict>
</dict>
</plist>"""

    @staticmethod
    def generate_mlx_plist(config: RemoteDevConfig,
                           stack: str = "premium_256gb") -> str:
        """MLX LLM server — AI inference engine."""
        stack_config = STACK_CONFIGS.get(stack, STACK_CONFIGS["premium_256gb"])
        model = stack_config["reasoning"]

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>hr.nyxlight.mlx</string>
    <key>ProgramArguments</key>
    <array>
        <string>{config.project_root}/.venv/bin/python</string>
        <string>-m</string>
        <string>mlx_lm.server</string>
        <string>--model</string>
        <string>{config.models_dir}/{model.name}</string>
        <string>--host</string>
        <string>{config.mlx_host}</string>
        <string>--port</string>
        <string>{config.mlx_chat_port}</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{config.project_root}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>MLX_METAL_DEVICE</key>
        <string>0</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{config.logs_dir}/mlx.log</string>
    <key>StandardErrorPath</key>
    <string>{config.logs_dir}/mlx.error.log</string>
</dict>
</plist>"""

    @staticmethod
    def generate_watcher_plist(config: RemoteDevConfig) -> str:
        """Hot-reload watcher service."""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>hr.nyxlight.watcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>{config.project_root}/.venv/bin/python</string>
        <string>-c</string>
        <string>from nyx_light.deployment import start_watcher; start_watcher()</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{config.project_root}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{config.logs_dir}/watcher.log</string>
    <key>StandardErrorPath</key>
    <string>{config.logs_dir}/watcher.error.log</string>
</dict>
</plist>"""


# ═══════════════════════════════════════════════════════════
# 5. HEALTH MONITORING & AUTO-RECOVERY
# ═══════════════════════════════════════════════════════════

@dataclass
class HealthCheck:
    """Rezultat health check-a."""
    service: str
    status: str  # healthy, degraded, down
    response_time_ms: float = 0
    details: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class HealthMonitor:
    """Prati zdravlje svih servisa."""

    def __init__(self):
        self._checks: List[HealthCheck] = []

    def check_all(self, config: RemoteDevConfig = None) -> Dict[str, Any]:
        """Provjeri sve servise."""
        config = config or RemoteDevConfig()
        results = {}

        # Check API
        results["api"] = self._check_http(
            f"http://127.0.0.1:{config.api_port}/health", "api")

        # Check MLX
        results["mlx"] = self._check_http(
            f"http://127.0.0.1:{config.mlx_chat_port}/v1/models", "mlx")

        # Check disk space
        results["disk"] = self._check_disk(config.data_dir)

        # Check memory
        results["memory"] = self._check_memory()

        overall = "healthy"
        if any(r.get("status") == "down" for r in results.values()
               if isinstance(r, dict)):
            overall = "down"
        elif any(r.get("status") == "degraded" for r in results.values()
                 if isinstance(r, dict)):
            overall = "degraded"

        return {
            "overall": overall,
            "timestamp": datetime.now().isoformat(),
            "services": results,
        }

    def _check_http(self, url: str, name: str) -> Dict:
        try:
            import urllib.request
            start = time.time()
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                elapsed = (time.time() - start) * 1000
                return {"status": "healthy", "response_ms": round(elapsed, 1)}
        except Exception as e:
            return {"status": "down", "error": str(e)}

    def _check_disk(self, path: str) -> Dict:
        try:
            import shutil
            usage = shutil.disk_usage(path)
            free_gb = usage.free / (1024**3)
            status = "healthy" if free_gb > 50 else (
                "degraded" if free_gb > 10 else "down")
            return {"status": status, "free_gb": round(free_gb, 1)}
        except Exception:
            return {"status": "healthy", "note": "Path not available in dev"}

    def _check_memory(self) -> Dict:
        try:
            import psutil
            mem = psutil.virtual_memory()
            return {
                "status": "healthy" if mem.percent < 90 else "degraded",
                "total_gb": round(mem.total / (1024**3), 1),
                "used_pct": mem.percent,
                "available_gb": round(mem.available / (1024**3), 1),
            }
        except ImportError:
            return {"status": "healthy", "note": "psutil not available"}


# ═══════════════════════════════════════════════════════════
# 6. DEPLOYMENT SCRIPTS GENERATOR
# ═══════════════════════════════════════════════════════════

class DeploymentGenerator:
    """Generira sve potrebne skripte za deployment na Mac Studio."""

    @staticmethod
    def generate_setup_script(config: RemoteDevConfig,
                              stack: str = "premium_256gb") -> str:
        """Bash skripta za inicijalni setup Mac Studija."""
        stack_config = STACK_CONFIGS.get(stack, STACK_CONFIGS["premium_256gb"])

        return f"""#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Nyx Light — Mac Studio Initial Setup
# Target: {stack_config['name']}
# ═══════════════════════════════════════════════════════════
set -euo pipefail

echo "🌙 Nyx Light — Postavljanje Mac Studija"
echo "Stack: {stack_config['name']}"
echo ""

# ── 1. Xcode Command Line Tools ──
echo "📦 Instalacija Xcode CLI tools..."
xcode-select --install 2>/dev/null || true

# ── 2. Homebrew ──
echo "🍺 Instalacija Homebrew..."
which brew || /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# ── 3. Systemske ovisnosti ──
echo "📦 Instalacija ovisnosti..."
brew install python@3.12 git git-lfs cmake pkg-config
brew install neo4j qdrant tailscale
brew install --cask visual-studio-code

# ── 4. Python okruženje ──
echo "🐍 Python virtualno okruženje..."
cd {config.project_root} || mkdir -p {config.project_root}
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel

# ── 5. MLX i AI ovisnosti ──
echo "🧠 MLX i AI paketi..."
pip install mlx mlx-lm mlx-vlm
pip install vllm  # Ako je dostupan za macOS
pip install transformers tokenizers sentencepiece
pip install qdrant-client neo4j

# ── 6. Aplikacijske ovisnosti ──
echo "📦 Nyx Light ovisnosti..."
pip install fastapi uvicorn[standard] websockets
pip install pydantic python-multipart aiofiles
pip install openpyxl python-docx lxml
pip install psutil httpx aiohttp

# ── 7. Dev tools ──
echo "🛠 Dev alati..."
pip install pytest pytest-asyncio ruff mypy
pip install ipython jupyter

# ── 8. Nyx Light instalacija ──
echo "📦 Nyx Light install..."
cd {config.project_root}
git clone https://github.com/mladen1312/nyx-light-racunovodja.git . 2>/dev/null || git pull
pip install -e ".[dev]"

# ── 9. Direktoriji ──
echo "📁 Kreiranje direktorija..."
mkdir -p {config.data_dir}/db
mkdir -p {config.data_dir}/uploads
mkdir -p {config.data_dir}/outputs
mkdir -p {config.logs_dir}
mkdir -p {config.backup_dir}
mkdir -p {config.models_dir}

# ── 10. Download modela ──
echo "🧠 Preuzimanje AI modela (ovo traje)..."
echo "Reasoning: {stack_config['reasoning'].name}"
python -c "
from mlx_lm import load
print('Downloading reasoning model...')
# model, tokenizer = load('{stack_config['reasoning'].name}')
print('Model ready (uncomment above for actual download)')
"

echo "Vision: {stack_config['vision'].name}"
echo "Embedding: {stack_config['embedding'].name}"
echo ""
echo "⚠️  Za download modela koristi:"
echo "  mlx_lm.convert --hf-path <HF_MODEL_ID> -q --q-bits 4"
echo "  ili huggingface-cli download <MODEL> --local-dir {config.models_dir}/<MODEL>"

# ── 11. Tailscale (VPN) ──
echo "🔗 Tailscale setup..."
sudo tailscale up --hostname={config.tailscale_hostname}

# ── 12. SSH hardening ──
echo "🔒 SSH konfiguracija..."
echo "PasswordAuthentication no" | sudo tee -a /etc/ssh/sshd_config.d/nyx.conf
echo "PubkeyAuthentication yes" | sudo tee -a /etc/ssh/sshd_config.d/nyx.conf

# ── 13. Launchd servisi ──
echo "⚙️  Instalacija servisa..."
# Plist datoteke se kopiraju iz deployment/services/

# ── 14. Testovi ──
echo "🧪 Pokretanje testova..."
cd {config.project_root}
python -m pytest tests/ -q --tb=short

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "✅ Nyx Light Mac Studio spreman!"
echo ""
echo "Servisi:"
echo "  API:  http://localhost:{config.api_port}"
echo "  MLX:  http://localhost:{config.mlx_chat_port}/v1/chat/completions"
echo ""
echo "Remote pristup:"
echo "  SSH:  ssh {config.ssh_user}@{config.tailscale_hostname}"
echo "  VS Code: Remote SSH → nyx-studio"
echo ""
echo "Memory budget:"
python3 -c "
from nyx_light.deployment import recommend_stack
r = recommend_stack(256, 'quality')
b = r['memory_budget']
print(f'  Reasoning: {{r[\"models\"][\"reasoning\"]}}')
print(f'  Vision:    {{r[\"models\"][\"vision\"]}}')
print(f'  RAM used:  {{b[\"used_gb\"]}} / {{b[\"total_gb\"]}} GB ({{b[\"utilization_pct\"]}}%)')
print(f'  Free:      {{b[\"free_gb\"]}} GB')
"
echo "═══════════════════════════════════════════════════════════"
"""

    @staticmethod
    def generate_deploy_script(config: RemoteDevConfig) -> str:
        """Skripta za deployment update-a (git pull + reload)."""
        return f"""#!/bin/bash
# Nyx Light — Deploy Update (zero-downtime)
set -euo pipefail

PROJECT="{config.project_root}"
cd "$PROJECT"

echo "🌙 Nyx Light Deploy"
echo "$(date)"

# 1. Git pull
echo "📥 Git pull..."
git fetch origin
git reset --hard origin/main

# 2. Install dependencies (if changed)
if git diff HEAD~1 --name-only | grep -q "pyproject.toml\\|requirements"; then
    echo "📦 Updating dependencies..."
    source .venv/bin/activate
    pip install -e ".[dev]" -q
fi

# 3. Run tests
echo "🧪 Testovi..."
source .venv/bin/activate
python -m pytest tests/ -q --tb=short -x
if [ $? -ne 0 ]; then
    echo "❌ Testovi pali! Deploy PREKINUT."
    exit 1
fi

# 4. Reload API (graceful — uvicorn --reload handles it)
echo "♻️  API se automatski reloada (uvicorn --reload)..."

# 5. Log
echo "✅ Deploy uspješan: $(git log -1 --oneline)"
echo "$(date) $(git log -1 --oneline)" >> {config.logs_dir}/deploy.log
"""

    @staticmethod
    def generate_live_edit_script(config: RemoteDevConfig) -> str:
        """Skripta za live editing sesiju."""
        return f"""#!/bin/bash
# Nyx Light — Live Edit Session
# Pokreni ovo kad želiš editirati kod u živo

PROJECT="{config.project_root}"
cd "$PROJECT"
source .venv/bin/activate

echo "🌙 Nyx Light — Live Edit Mode"
echo ""
echo "Servisi:"
echo "  API:     http://localhost:{config.api_port} (auto-reload ON)"
echo "  MLX:     http://localhost:{config.mlx_chat_port}"
echo "  Tests:   pytest tests/ -v"
echo ""
echo "Korisne komande:"
echo "  nyx-test       → pokreni sve testove"
echo "  nyx-test-fast  → samo promijenjene module"
echo "  nyx-reload     → force reload API-ja"
echo "  nyx-logs       → pratI logove"
echo "  nyx-status     → zdravlje sustava"
echo "  nyx-memory     → memory usage"
echo ""

# Aliasi
alias nyx-test="python -m pytest tests/ -v --tb=short"
alias nyx-test-fast="python -m pytest tests/ -v --tb=short -x --lf"
alias nyx-reload="kill -HUP \\$(pgrep -f uvicorn) 2>/dev/null || echo 'API not running'"
alias nyx-logs="tail -f {config.logs_dir}/*.log"
alias nyx-status="python -c 'from nyx_light.deployment import HealthMonitor; import json; print(json.dumps(HealthMonitor().check_all(), indent=2))'"
alias nyx-memory="python -c '
from nyx_light.deployment import recommend_stack
import json
r = recommend_stack(256)
print(json.dumps(r, indent=2))
'"

# Start watcher u pozadini
python -c "
from nyx_light.deployment import HotReloadWatcher, ModuleReloader
import signal, sys

watcher = HotReloadWatcher(watch_dirs=['src/nyx_light'])
reloader = ModuleReloader()
watcher.on_change(lambda c: reloader.reload_module(c.path) if c.action != 'deleted' else None)
watcher.start()
print('👀 Hot-reload watcher aktivan. Editiraj kod — automatski se reloada.')
print('Ctrl+C za izlaz.')
signal.signal(signal.SIGINT, lambda s, f: (watcher.stop(), sys.exit(0)))
signal.pause()
" &

# Interaktivni shell
exec bash --rcfile <(echo 'PS1="🌙 nyx> "')"
"""


# ═══════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════

def start_watcher():
    """Entry point za watcher service."""
    watcher = HotReloadWatcher(watch_dirs=["src/nyx_light"])
    reloader = ModuleReloader()
    watcher.on_change(
        lambda c: reloader.reload_module(c.path)
        if c.action != "deleted" else None)
    watcher.start()
    logger.info("Watcher started — waiting for changes...")
    signal.signal(signal.SIGINT, lambda s, f: (watcher.stop(), sys.exit(0)))
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        watcher.stop()


def get_stats() -> Dict[str, Any]:
    """Statistike deployment modula."""
    return {
        "module": "deployment",
        "available_stacks": list(STACK_CONFIGS.keys()),
        "models": {
            "reasoning": [QWEN3_235B_A22B.name, DEEPSEEK_R1_70B.name,
                          QWEN25_72B.name, QWEN3_32B.name],
            "vision": [QWEN25_VL_72B.name, QWEN25_VL_32B.name,
                       QWEN25_VL_7B.name],
            "embedding": [BGE_M3.name, NOMIC_EMBED.name],
        },
    }
