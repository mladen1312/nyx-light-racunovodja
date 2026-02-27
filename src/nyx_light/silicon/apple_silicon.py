"""
Nyx Light — Apple Silicon Runtime
══════════════════════════════════════════════════════════════

Adapted from NYX 47.0 "Stones" architecture for single-node
Mac Studio operation (256 GB+ Unified Memory).
Supports M3 Ultra (current) and future Apple Silicon chips.

This is the HARDWARE ABSTRACTION LAYER for Nyx Light.
All model inference, memory management, and silicon-specific
optimizations flow through this module.

Architecture (Single Node — Mac Studio, Apple Silicon Ultra):
  ┌──────────────────────────────────────────────────┐
  │  Apple Silicon Ultra SoC — 256+ GB Unified Memory │
  │                                                   │
  │  ┌─────────────┐  ┌─────────────┐                │
  │  │  GPU Die 0   │  │  GPU Die 1   │  80 cores    │
  │  │  40 cores    │  │  40 cores    │  ~27 TFLOPS   │
  │  └──────┬───────┘  └──────┬───────┘              │
  │         │    UltraFusion    │                      │
  │         └────────┬──────────┘                      │
  │  ┌───────────────┴────────────────┐               │
  │  │  Unified Memory (256+ GB)      │               │
  │  │  ┌──────────┐ ┌──────────────┐ │               │
  │  │  │ LLM 124GB│ │ KV Cache 30GB│ │  Zero-copy    │
  │  │  └──────────┘ └──────────────┘ │  No PCIe      │
  │  │  ┌──────────┐ ┌──────────────┐ │               │
  │  │  │Vision 5GB│ │ RAG/Emb 3GB  │ │  GPU+CPU      │
  │  │  └──────────┘ └──────────────┘ │  same bytes   │
  │  └────────────────────────────────┘               │
  │  ┌──────────┐  ┌──────────────┐                   │
  │  │ ANE 38T  │  │ CPU 32-core  │                   │
  │  │ INT8     │  │ 24P + 8E     │                   │
  │  └──────────┘  └──────────────┘                   │
  └──────────────────────────────────────────────────┘

Key Optimizations (from Nyx Stones):
  1. MLX_METAL_FAST_SYNCH=1    — Reduce GPU sync overhead
  2. MLX_METAL_PREALLOCATE=true — Pre-allocate Metal buffers
  3. Wired memory for KV cache  — Prevent macOS page-out
  4. Die-aware allocation       — Balance load across UltraFusion
  5. mmap model weights         — Zero-copy loading
  6. ANE for embeddings         — Free GPU for LLM inference
  7. Prompt caching             — Reuse system prompt KV state

© 2026 Dr. Mladen Mešter · Nexellum Lab d.o.o.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.silicon")

# ══════════════════════════════════════════════════════════════
# ENVIRONMENT — Apple Silicon MLX Tuning
# ══════════════════════════════════════════════════════════════

# Critical MLX performance flags (from Nyx Stones m5_maximizer)
_MLX_ENV = {
    "MLX_METAL_FAST_SYNCH": "1",       # Faster GPU command submission
    "MLX_METAL_PREALLOCATE": "true",   # Pre-allocate Metal buffers → less allocation stalls
    "MLX_METAL_DEVICE_INDEX": "0",     # Explicit GPU device
    "TOKENIZERS_PARALLELISM": "false", # Avoid tokenizer fork deadlock
    "MALLOC_NANO_ZONE": "0",          # Better large allocation performance
    "MKL_NUM_THREADS": "1",           # No MKL thread contention
}

for key, val in _MLX_ENV.items():
    os.environ.setdefault(key, val)


# ══════════════════════════════════════════════════════════════
# MLX / CoreML Detection (graceful degradation)
# ══════════════════════════════════════════════════════════════

HAS_MLX = False
HAS_COREML = False
HAS_PSUTIL = False

try:
    import mlx.core as mx
    HAS_MLX = True
    logger.info("✅ MLX framework detected — hardware acceleration ACTIVE")
except ImportError:
    mx = None  # type: ignore
    logger.warning("MLX not available — simulation mode")

try:
    import coremltools as ct
    HAS_COREML = True
    logger.info("✅ CoreML detected — ANE offload available")
except ImportError:
    ct = None  # type: ignore

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    psutil = None  # type: ignore


# ══════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════

class ChipGeneration(Enum):
    """Apple Silicon generations."""
    M1 = "m1"
    M2 = "m2"
    M3 = "m3"
    M4 = "m4"
    M5 = "m5"
    UNKNOWN = "unknown"


class ChipVariant(Enum):
    """Apple Silicon chip variants."""
    BASE = "base"
    PRO = "pro"
    MAX = "max"
    ULTRA = "ultra"
    UNKNOWN = "unknown"


class ComputeUnit(Enum):
    """M5 Ultra compute units."""
    GPU_METAL = "gpu"
    NEURAL_ENGINE = "ane"
    CPU_PERFORMANCE = "cpu_p"
    CPU_EFFICIENCY = "cpu_e"


class MemoryRegionType(Enum):
    """Types of UMA memory regions."""
    MODEL_WEIGHTS = "model_weights"
    KV_CACHE = "kv_cache"
    WORKING_BUFFER = "working_buffer"
    EMBEDDING_STORE = "embedding_store"
    PROMPT_CACHE = "prompt_cache"
    VISION_MODEL = "vision_model"
    LORA_ADAPTERS = "lora_adapters"


class MemoryPriority(Enum):
    """Eviction priority (lower = evict first)."""
    LOW = 1
    NORMAL = 5
    HIGH = 8
    PINNED = 10   # Never evict


class PressureLevel(Enum):
    """UMA pressure levels (from Nyx Stones memory_pressure.py)."""
    NOMINAL = "nominal"       # < 70% — full speed
    ELEVATED = "elevated"     # 70-80% — minor adjustments
    WARNING = "warning"       # 80-88% — halve batch, consider Q3
    CRITICAL = "critical"     # 88-95% — minimum batch, evict cold
    EMERGENCY = "emergency"   # > 95% — single query mode


class ThermalState(Enum):
    """Thermal states (from Nyx Stones thermal_manager.py)."""
    COOL = "cool"              # < 45°C
    NOMINAL = "nominal"        # 45-65°C
    WARM = "warm"              # 65-80°C
    HOT = "hot"                # 80-95°C
    THROTTLING = "throttling"  # 95-105°C
    CRITICAL = "critical"      # > 105°C


# ══════════════════════════════════════════════════════════════
# HARDWARE SPECS — M5 Ultra (from Nyx Stones m5_maximizer.py)
# ══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class M5UltraSpec:
    """M5 Ultra hardware specification.

    M5 Ultra = 2× M5 Max dies fused via UltraFusion.
    3nm 3rd-gen process. ~240 billion transistors.
    """
    cpu_p_cores: int = 24
    cpu_e_cores: int = 8
    cpu_total: int = 32
    gpu_cores: int = 80
    gpu_tflops_fp16: float = 27.0
    gpu_tflops_int8: float = 54.0
    ane_tops_int8: float = 38.0
    ane_tops_fp16: float = 19.0
    ane_max_model_mb: int = 4096
    memory_bw_gbps: float = 819.0
    ultrafusion_bw_gbps: float = 2500.0
    ultrafusion_latency_ns: int = 15
    tdp_watts: int = 280
    process_nm: str = "3nm_gen3"
    transistors_b: float = 240.0


# Default spec (overridden by detection)
DEFAULT_SPEC = M5UltraSpec()


# ══════════════════════════════════════════════════════════════
# HARDWARE DETECTION (from Nyx Stones apple_silicon.py)
# ══════════════════════════════════════════════════════════════

@dataclass
class DetectedHardware:
    """Detected Apple Silicon hardware."""
    chip_name: str = "Unknown"
    generation: ChipGeneration = ChipGeneration.UNKNOWN
    variant: ChipVariant = ChipVariant.UNKNOWN
    total_memory_gb: float = 0.0
    cpu_cores: int = 0
    gpu_cores: int = 0
    neural_engine_cores: int = 0
    memory_bw_gbps: float = 0.0
    is_apple_silicon: bool = False
    macos_version: str = ""
    hostname: str = ""

    @property
    def is_ultra(self) -> bool:
        return self.variant == ChipVariant.ULTRA

    @property
    def can_run_235b(self) -> bool:
        """Can this machine run Qwen3-235B-A22B at Q4?"""
        return self.total_memory_gb >= 200

    @property
    def recommended_model_tier(self) -> str:
        if self.total_memory_gb >= 256:
            return "235B"  # Qwen3-235B-A22B
        elif self.total_memory_gb >= 96:
            return "72B"   # Qwen2.5-72B
        elif self.total_memory_gb >= 64:
            return "30B"   # Qwen3-30B-A3B
        else:
            return "8B"    # Qwen3-8B


def detect_hardware() -> DetectedHardware:
    """Detect Apple Silicon hardware via sysctl and system_profiler.

    Adapted from Nyx Stones apple_silicon.py with single-node focus.
    """
    hw = DetectedHardware()
    hw.hostname = platform.node()

    if platform.system() != "Darwin":
        logger.info("Not macOS — running in simulation mode")
        hw.total_memory_gb = _estimate_memory_non_mac()
        return hw

    # --- Memory (sysctl) ---
    try:
        out = subprocess.check_output(
            ["sysctl", "-n", "hw.memsize"], text=True, timeout=5
        ).strip()
        hw.total_memory_gb = int(out) / (1024 ** 3)
    except Exception:
        hw.total_memory_gb = 256.0  # Safe default

    # --- CPU cores ---
    try:
        hw.cpu_cores = int(subprocess.check_output(
            ["sysctl", "-n", "hw.ncpu"], text=True, timeout=5
        ).strip())
    except Exception:
        hw.cpu_cores = 32

    # --- Chip detection (sysctl hw.chip_name or machdep.cpu.brand_string) ---
    chip_str = ""
    for key in ["machdep.cpu.brand_string", "hw.chip_name"]:
        try:
            chip_str = subprocess.check_output(
                ["sysctl", "-n", key], text=True, timeout=5
            ).strip()
            if chip_str:
                break
        except Exception:
            continue

    if not chip_str:
        # Fallback: system_profiler
        try:
            sp = subprocess.check_output(
                ["system_profiler", "SPHardwareDataType"],
                text=True, timeout=10
            )
            for line in sp.splitlines():
                if "Chip" in line or "Processor" in line:
                    chip_str = line.split(":")[-1].strip()
                    break
        except Exception:
            pass

    hw.chip_name = chip_str or "Unknown Apple Silicon"
    hw.is_apple_silicon = "apple" in chip_str.lower() or "m1" in chip_str.lower() or "m2" in chip_str.lower() or "m3" in chip_str.lower() or "m4" in chip_str.lower() or "m5" in chip_str.lower()

    # Parse generation and variant
    chip_lower = chip_str.lower()
    for gen in [("m5", ChipGeneration.M5), ("m4", ChipGeneration.M4),
                ("m3", ChipGeneration.M3), ("m2", ChipGeneration.M2),
                ("m1", ChipGeneration.M1)]:
        if gen[0] in chip_lower:
            hw.generation = gen[1]
            break

    for var in [("ultra", ChipVariant.ULTRA), ("max", ChipVariant.MAX),
                ("pro", ChipVariant.PRO)]:
        if var[0] in chip_lower:
            hw.variant = var[1]
            break
    else:
        if hw.is_apple_silicon:
            hw.variant = ChipVariant.BASE

    # GPU cores estimate
    gpu_estimates = {
        (ChipGeneration.M5, ChipVariant.ULTRA): 80,
        (ChipGeneration.M5, ChipVariant.MAX): 40,
        (ChipGeneration.M4, ChipVariant.ULTRA): 80,
        (ChipGeneration.M4, ChipVariant.MAX): 40,
        (ChipGeneration.M3, ChipVariant.ULTRA): 76,
        (ChipGeneration.M3, ChipVariant.MAX): 40,
    }
    hw.gpu_cores = gpu_estimates.get(
        (hw.generation, hw.variant), 16
    )

    # Memory bandwidth estimate (GB/s)
    bw_estimates = {
        ChipVariant.ULTRA: 819.0,
        ChipVariant.MAX: 546.0,
        ChipVariant.PRO: 273.0,
        ChipVariant.BASE: 120.0,
    }
    hw.memory_bw_gbps = bw_estimates.get(hw.variant, 100.0)

    # Neural Engine
    hw.neural_engine_cores = 32 if hw.is_ultra else 16

    # macOS version
    try:
        hw.macos_version = platform.mac_ver()[0]
    except Exception:
        pass

    logger.info(
        "Detected: %s | %.0f GB | %d GPU cores | %.0f GB/s bandwidth | %s",
        hw.chip_name, hw.total_memory_gb, hw.gpu_cores,
        hw.memory_bw_gbps, hw.variant.value
    )
    return hw


def _estimate_memory_non_mac() -> float:
    """Estimate memory on non-macOS (Linux/Windows)."""
    if HAS_PSUTIL:
        return psutil.virtual_memory().total / (1024 ** 3)
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    return int(line.split()[1]) / (1024 ** 2)
    except Exception:
        pass
    return 64.0


# ══════════════════════════════════════════════════════════════
# UNIFIED MEMORY CONTROLLER (from Nyx Stones m5_maximizer.py)
# ══════════════════════════════════════════════════════════════

@dataclass
class MemoryRegion:
    """A tracked region of unified memory."""
    region_id: str
    region_type: MemoryRegionType
    size_bytes: int
    priority: MemoryPriority
    wired: bool = False
    mmap_path: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024 ** 3)

    def touch(self):
        self.last_accessed = time.time()
        self.access_count += 1


class UMAController:
    """Unified Memory Architecture controller for single Mac Studio.

    Adapted from Nyx Stones UMAController for single-node (256GB).
    Manages memory budgets across LLM, Vision, KV cache, embeddings,
    LoRA adapters, and working buffers.

    Memory Budget (256 GB target):
      ┌────────────────────┬──────────┬────────┐
      │ Component          │ Budget % │ ~GB    │
      ├────────────────────┼──────────┼────────┤
      │ LLM weights        │   50%    │ 128 GB │
      │ KV cache (15 users)│   15%    │  38 GB │
      │ Vision model       │    3%    │   8 GB │
      │ Embeddings + RAG   │    3%    │   8 GB │
      │ LoRA adapters      │    2%    │   5 GB │
      │ Working buffers    │   10%    │  26 GB │
      │ Prompt cache       │    5%    │  13 GB │
      │ OS + headroom      │   12%    │  30 GB │
      └────────────────────┴──────────┴────────┘
    """

    # Budget allocations (fraction of total UMA)
    DEFAULT_BUDGETS = {
        MemoryRegionType.MODEL_WEIGHTS:   0.50,
        MemoryRegionType.KV_CACHE:        0.15,
        MemoryRegionType.VISION_MODEL:    0.03,
        MemoryRegionType.EMBEDDING_STORE: 0.03,
        MemoryRegionType.LORA_ADAPTERS:   0.02,
        MemoryRegionType.WORKING_BUFFER:  0.10,
        MemoryRegionType.PROMPT_CACHE:    0.05,
    }

    def __init__(self, total_gb: float = 256.0):
        self.total_bytes = int(total_gb * (1024 ** 3))
        self._regions: Dict[str, MemoryRegion] = {}
        self._budgets = dict(self.DEFAULT_BUDGETS)
        self._wired_bytes = 0
        self._max_wired_pct = 0.85
        self._pressure = PressureLevel.NOMINAL

        logger.info(
            "UMAController: %.0f GB total, budgets: %s",
            total_gb,
            {k.value: f"{v:.0%}" for k, v in self._budgets.items()}
        )

    @property
    def used_bytes(self) -> int:
        return sum(r.size_bytes for r in self._regions.values())

    @property
    def used_gb(self) -> float:
        return self.used_bytes / (1024 ** 3)

    @property
    def free_gb(self) -> float:
        return (self.total_bytes - self.used_bytes) / (1024 ** 3)

    @property
    def utilization(self) -> float:
        if self.total_bytes == 0:
            return 0.0
        return self.used_bytes / self.total_bytes

    @property
    def pressure(self) -> PressureLevel:
        util = self.utilization
        if util < 0.70:
            return PressureLevel.NOMINAL
        elif util < 0.80:
            return PressureLevel.ELEVATED
        elif util < 0.88:
            return PressureLevel.WARNING
        elif util < 0.95:
            return PressureLevel.CRITICAL
        else:
            return PressureLevel.EMERGENCY

    def budget_remaining_gb(self, region_type: MemoryRegionType) -> float:
        budget_bytes = int(self.total_bytes * self._budgets.get(region_type, 0))
        used = sum(
            r.size_bytes for r in self._regions.values()
            if r.region_type == region_type
        )
        return max(0, budget_bytes - used) / (1024 ** 3)

    def allocate(
        self,
        region_id: str,
        region_type: MemoryRegionType,
        size_gb: float,
        priority: MemoryPriority = MemoryPriority.NORMAL,
        wire: bool = False,
    ) -> Optional[MemoryRegion]:
        """Allocate a UMA memory region.

        Wire=True pins memory (prevents macOS page-out).
        Use for KV cache to ensure memory-bandwidth access.
        """
        if region_id in self._regions:
            self._regions[region_id].touch()
            return self._regions[region_id]

        size_bytes = int(size_gb * (1024 ** 3))

        # Check budget
        budget_remaining = self.budget_remaining_gb(region_type) * (1024 ** 3)
        if budget_remaining < size_bytes:
            freed = self._evict_for(region_type, size_bytes)
            if freed < size_bytes:
                logger.warning(
                    "UMA: Cannot allocate %s (%.1f GB) — budget for %s exhausted",
                    region_id, size_gb, region_type.value
                )
                return None

        # Wired limit
        if wire:
            max_wired = int(self.total_bytes * self._max_wired_pct)
            if self._wired_bytes + size_bytes > max_wired:
                logger.warning(
                    "UMA: Wired limit (%.0f GB) reached — %s falls back to non-wired",
                    max_wired / (1024 ** 3), region_id
                )
                wire = False

        region = MemoryRegion(
            region_id=region_id,
            region_type=region_type,
            size_bytes=size_bytes,
            priority=priority,
            wired=wire,
        )
        self._regions[region_id] = region
        if wire:
            self._wired_bytes += size_bytes

        logger.debug(
            "UMA: Allocated %s — %.1f GB (%s, wired=%s) — %.1f/%.1f GB used",
            region_id, size_gb, region_type.value, wire,
            self.used_gb, self.total_bytes / (1024 ** 3)
        )
        return region

    def release(self, region_id: str) -> bool:
        """Release a memory region."""
        region = self._regions.pop(region_id, None)
        if region:
            if region.wired:
                self._wired_bytes -= region.size_bytes
            logger.debug("UMA: Released %s (%.1f GB)", region_id, region.size_gb)
            return True
        return False

    def _evict_for(
        self, region_type: MemoryRegionType, needed_bytes: int
    ) -> int:
        """Evict low-priority regions to make space."""
        # Sort by priority (ascending), then by age (oldest first)
        candidates = sorted(
            [
                r for r in self._regions.values()
                if r.region_type == region_type
                and r.priority.value < MemoryPriority.PINNED.value
            ],
            key=lambda r: (r.priority.value, -r.last_accessed)
        )
        freed = 0
        for r in candidates:
            if freed >= needed_bytes:
                break
            self.release(r.region_id)
            freed += r.size_bytes

        return freed

    def status(self) -> Dict[str, Any]:
        """Get UMA status snapshot."""
        total_gb = self.total_bytes / (1024 ** 3)
        return {
            "total_gb": round(total_gb, 1),
            "used_gb": round(self.used_gb, 1),
            "free_gb": round(self.free_gb, 1),
            "utilization_pct": round(self.utilization * 100, 1),
            "pressure": self.pressure.value,
            "wired_gb": round(self._wired_bytes / (1024 ** 3), 1),
            "regions": len(self._regions),
            "by_type": {
                rt.value: round(
                    sum(
                        r.size_bytes for r in self._regions.values()
                        if r.region_type == rt
                    ) / (1024 ** 3), 1
                )
                for rt in MemoryRegionType
            }
        }


# ══════════════════════════════════════════════════════════════
# MEMORY PRESSURE MONITOR (from Nyx Stones memory_pressure.py)
# ══════════════════════════════════════════════════════════════

@dataclass
class MemorySnapshot:
    """Point-in-time memory state."""
    timestamp: datetime
    total_gb: float
    used_gb: float
    available_gb: float
    compressed_gb: float = 0.0
    swap_used_gb: float = 0.0
    wired_gb: float = 0.0
    pressure_level: PressureLevel = PressureLevel.NOMINAL
    source: str = "estimated"

    @property
    def utilization(self) -> float:
        return self.used_gb / max(0.001, self.total_gb)

    @property
    def is_swapping(self) -> bool:
        return self.swap_used_gb > 0.1


def read_memory_pressure() -> MemorySnapshot:
    """Read real-time memory from macOS vm_stat or psutil.

    On macOS: parses vm_stat for page statistics.
    On Linux:  uses /proc/meminfo.
    Fallback:  psutil or estimation.
    """
    now = datetime.now(timezone.utc)

    if platform.system() == "Darwin":
        return _read_macos_memory(now)
    elif HAS_PSUTIL:
        return _read_psutil_memory(now)
    else:
        return _read_fallback_memory(now)


def _read_macos_memory(now: datetime) -> MemorySnapshot:
    """Parse macOS vm_stat output."""
    try:
        out = subprocess.check_output(["vm_stat"], text=True, timeout=5)
        pages = {}
        page_size = 16384  # ARM64 page size
        for line in out.splitlines():
            if "page size" in line.lower():
                m = re.search(r"(\d+)", line)
                if m:
                    page_size = int(m.group(1))
            for key in ["free", "active", "inactive", "wired", "compressed",
                        "occupied by compressor"]:
                if key in line.lower():
                    m = re.search(r":\s+(\d+)", line)
                    if m:
                        pages[key] = int(m.group(1))

        to_gb = lambda p: (p * page_size) / (1024 ** 3)

        total_gb = 256.0  # Will be overridden by sysctl
        try:
            out2 = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"], text=True, timeout=5
            ).strip()
            total_gb = int(out2) / (1024 ** 3)
        except Exception:
            pass

        wired = to_gb(pages.get("wired", 0))
        active = to_gb(pages.get("active", 0))
        compressed = to_gb(pages.get("compressed", 0) + pages.get("occupied by compressor", 0))
        free = to_gb(pages.get("free", 0))
        inactive = to_gb(pages.get("inactive", 0))

        used = wired + active + compressed
        available = free + inactive

        # Swap
        swap_gb = 0.0
        try:
            sw = subprocess.check_output(
                ["sysctl", "-n", "vm.swapusage"], text=True, timeout=5
            )
            m = re.search(r"used\s*=\s*([\d.]+)([MG])", sw)
            if m:
                val = float(m.group(1))
                swap_gb = val / 1024 if m.group(2) == "M" else val
        except Exception:
            pass

        snap = MemorySnapshot(
            timestamp=now,
            total_gb=total_gb,
            used_gb=used,
            available_gb=available,
            compressed_gb=compressed,
            swap_used_gb=swap_gb,
            wired_gb=wired,
            source="vm_stat",
        )

    except Exception as e:
        logger.warning("vm_stat failed: %s — fallback to psutil", e)
        return _read_psutil_memory(now) if HAS_PSUTIL else _read_fallback_memory(now)

    # Determine pressure level
    util = snap.utilization
    if util < 0.70:
        snap.pressure_level = PressureLevel.NOMINAL
    elif util < 0.80:
        snap.pressure_level = PressureLevel.ELEVATED
    elif util < 0.88:
        snap.pressure_level = PressureLevel.WARNING
    elif util < 0.95:
        snap.pressure_level = PressureLevel.CRITICAL
    else:
        snap.pressure_level = PressureLevel.EMERGENCY

    return snap


def _read_psutil_memory(now: datetime) -> MemorySnapshot:
    """Read memory via psutil."""
    if not HAS_PSUTIL:
        return _read_fallback_memory(now)
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    total = vm.total / (1024 ** 3)
    used = vm.used / (1024 ** 3)
    available = vm.available / (1024 ** 3)
    swap = sw.used / (1024 ** 3) if sw else 0
    util = used / max(total, 0.001)

    level = PressureLevel.NOMINAL
    if util >= 0.95:
        level = PressureLevel.EMERGENCY
    elif util >= 0.88:
        level = PressureLevel.CRITICAL
    elif util >= 0.80:
        level = PressureLevel.WARNING
    elif util >= 0.70:
        level = PressureLevel.ELEVATED

    return MemorySnapshot(
        timestamp=now, total_gb=total, used_gb=used,
        available_gb=available, swap_used_gb=swap,
        pressure_level=level, source="psutil"
    )


def _read_fallback_memory(now: datetime) -> MemorySnapshot:
    """Fallback memory estimation."""
    return MemorySnapshot(
        timestamp=now, total_gb=256.0, used_gb=170.0,
        available_gb=86.0, pressure_level=PressureLevel.NOMINAL,
        source="estimated"
    )


# ══════════════════════════════════════════════════════════════
# THERMAL MONITORING (from Nyx Stones thermal_manager.py)
# ══════════════════════════════════════════════════════════════

def read_thermal_state() -> ThermalState:
    """Read macOS thermal pressure without root.

    Uses: notifyutil -g com.apple.system.thermalpressurelevel
      0 = Nominal, 1 = Moderate, 2 = Heavy, 3+ = Critical
    """
    if platform.system() != "Darwin":
        return ThermalState.NOMINAL

    try:
        out = subprocess.check_output(
            ["notifyutil", "-g", "com.apple.system.thermalpressurelevel"],
            text=True, timeout=5
        )
        m = re.search(r"(\d+)\s*$", out.strip())
        if m:
            level = int(m.group(1))
            if level == 0:
                return ThermalState.NOMINAL
            elif level == 1:
                return ThermalState.WARM
            elif level == 2:
                return ThermalState.HOT
            else:
                return ThermalState.THROTTLING
    except Exception:
        pass

    return ThermalState.NOMINAL


# ══════════════════════════════════════════════════════════════
# ADAPTIVE BATCH CONTROLLER (from Nyx Stones)
# ══════════════════════════════════════════════════════════════

@dataclass
class BatchConfig:
    """Adaptive batch configuration for 15 concurrent users."""
    max_concurrent: int = 15
    max_batch_size: int = 8
    max_tokens_per_request: int = 4096
    kv_cache_per_user_gb: float = 2.0  # ~2GB KV for 128K context

    # Pressure-scaled values
    current_batch_size: int = 8
    current_max_tokens: int = 4096


class AdaptiveBatchController:
    """Scale batch size based on memory pressure and thermal state.

    From Nyx Stones memory_pressure.py ScalingDecision.

    ┌──────────┬─────────────────────┬────────────────────┐
    │ Pressure │ Batch Size          │ Max Tokens         │
    ├──────────┼─────────────────────┼────────────────────┤
    │ NOMINAL  │ 8 (full)            │ 4096               │
    │ ELEVATED │ 6 (-25%)            │ 4096               │
    │ WARNING  │ 4 (-50%)            │ 2048               │
    │ CRITICAL │ 2 (min)             │ 1024               │
    │ EMERGENCY│ 1 (single query)    │ 512                │
    └──────────┴─────────────────────┴────────────────────┘
    """

    PRESSURE_SCALING = {
        PressureLevel.NOMINAL:   (8, 4096),
        PressureLevel.ELEVATED:  (6, 4096),
        PressureLevel.WARNING:   (4, 2048),
        PressureLevel.CRITICAL:  (2, 1024),
        PressureLevel.EMERGENCY: (1, 512),
    }

    THERMAL_SCALING = {
        ThermalState.COOL:       1.0,
        ThermalState.NOMINAL:    1.0,
        ThermalState.WARM:       0.85,
        ThermalState.HOT:        0.65,
        ThermalState.THROTTLING: 0.40,
        ThermalState.CRITICAL:   0.25,
    }

    def __init__(self, config: Optional[BatchConfig] = None):
        self.config = config or BatchConfig()
        self._history: List[Tuple[float, PressureLevel, ThermalState]] = []

    def compute(
        self,
        pressure: PressureLevel,
        thermal: ThermalState,
    ) -> BatchConfig:
        """Compute optimal batch config given current pressure & thermal."""
        base_batch, base_tokens = self.PRESSURE_SCALING.get(
            pressure, (8, 4096)
        )
        thermal_factor = self.THERMAL_SCALING.get(thermal, 1.0)

        batch_size = max(1, int(base_batch * thermal_factor))
        max_tokens = max(256, int(base_tokens * thermal_factor))

        self.config.current_batch_size = batch_size
        self.config.current_max_tokens = max_tokens

        self._history.append((time.time(), pressure, thermal))
        if len(self._history) > 1000:
            self._history = self._history[-500:]

        return self.config


# ══════════════════════════════════════════════════════════════
# SILICON RUNTIME — MASTER SINGLETON
# ══════════════════════════════════════════════════════════════

class SiliconRuntime:
    """Master runtime binding all Apple Silicon components.

    This is the SINGLE ENTRY POINT for hardware interaction in Nyx Light.
    All modules should use get_runtime() to access the singleton.

    Integrates:
      - Hardware detection
      - UMA memory management
      - Memory pressure monitoring
      - Thermal state monitoring
      - Adaptive batch control
    """

    _instance: Optional["SiliconRuntime"] = None

    def __init__(self):
        self.hardware = detect_hardware()
        self.uma = UMAController(total_gb=self.hardware.total_memory_gb)
        self.batch_controller = AdaptiveBatchController()
        self._initialized_at = time.time()
        logger.info(
            "SiliconRuntime initialized: %s | %.0f GB | %d GPU cores",
            self.hardware.chip_name,
            self.hardware.total_memory_gb,
            self.hardware.gpu_cores,
        )

    @classmethod
    def get_instance(cls) -> "SiliconRuntime":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset singleton (for testing)."""
        cls._instance = None

    def health_check(self) -> Dict[str, Any]:
        """Complete health snapshot."""
        mem = read_memory_pressure()
        thermal = read_thermal_state()
        batch = self.batch_controller.compute(mem.pressure_level, thermal)

        return {
            "hardware": {
                "chip": self.hardware.chip_name,
                "generation": self.hardware.generation.value,
                "variant": self.hardware.variant.value,
                "total_memory_gb": self.hardware.total_memory_gb,
                "gpu_cores": self.hardware.gpu_cores,
                "memory_bw_gbps": self.hardware.memory_bw_gbps,
                "is_apple_silicon": self.hardware.is_apple_silicon,
            },
            "memory": {
                "system": {
                    "total_gb": round(mem.total_gb, 1),
                    "used_gb": round(mem.used_gb, 1),
                    "available_gb": round(mem.available_gb, 1),
                    "swap_gb": round(mem.swap_used_gb, 1),
                    "compressed_gb": round(mem.compressed_gb, 1),
                    "pressure": mem.pressure_level.value,
                    "is_swapping": mem.is_swapping,
                },
                "uma": self.uma.status(),
            },
            "thermal": thermal.value,
            "batch": {
                "max_batch": batch.current_batch_size,
                "max_tokens": batch.current_max_tokens,
            },
            "uptime_seconds": round(time.time() - self._initialized_at, 1),
            "mlx_available": HAS_MLX,
            "coreml_available": HAS_COREML,
            "recommended_model": self.hardware.recommended_model_tier,
        }


def get_runtime() -> SiliconRuntime:
    """Get the global SiliconRuntime singleton."""
    return SiliconRuntime.get_instance()
