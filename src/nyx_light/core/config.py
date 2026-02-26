"""
Nyx Light — Računovođa: Konfiguracija sustava

Sva podešavanja za Mac Studio M5 Ultra (192 GB).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class NyxLightConfig:
    """Master konfiguracija sustava."""

    # ── Hardware ──
    total_memory_gb: float = 192.0
    wired_memory_pct: float = 0.83  # 160 GB wired za 192 GB Mac Studio
    max_concurrent_users: int = 15

    # ── AI Modeli ──
    primary_model: str = "mlx-community/Qwen2.5-72B-Instruct-4bit"
    vision_model: str = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"
    embedding_model: str = "intfloat/multilingual-e5-base"

    # ── vLLM-MLX Server ──
    vllm_host: str = "127.0.0.1"
    vllm_port: int = 8080
    vllm_max_concurrency: int = 15
    max_tokens: int = 4096
    temperature: float = 0.3  # Niža za računovodstvo (preciznost)

    # ── API Server ──
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ── Data Paths ──
    data_dir: Path = Path("data")
    uploads_dir: Path = Path("data/uploads")
    exports_dir: Path = Path("data/exports")
    models_dir: Path = Path("data/models")
    memory_db_dir: Path = Path("data/memory_db")
    rag_db_dir: Path = Path("data/rag_db")
    laws_dir: Path = Path("data/laws")
    prompt_cache_dir: Path = Path("data/prompt_cache")

    # ── ERP Integracija ──
    erp_systems: List[str] = field(default_factory=lambda: ["CPP", "Synesis"])
    export_formats: List[str] = field(default_factory=lambda: ["XML", "JSON", "CSV"])

    # ── Banke ──
    supported_banks: List[str] = field(
        default_factory=lambda: ["Erste", "Zaba", "PBZ", "OTP", "Addiko"]
    )

    # ── Sigurnost ──
    require_human_approval: bool = True  # UVIJEK True — Tvrda granica
    enable_cloud_apis: bool = False       # UVIJEK False — Apsolutna privatnost
    max_cash_limit_eur: float = 10_000.0
    km_naknada_eur: float = 0.30

    def ensure_dirs(self):
        """Kreiraj sve potrebne direktorije."""
        for d in [
            self.data_dir, self.uploads_dir, self.exports_dir,
            self.models_dir, self.memory_db_dir, self.rag_db_dir,
            self.laws_dir, self.prompt_cache_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)


# Singleton
config = NyxLightConfig()
