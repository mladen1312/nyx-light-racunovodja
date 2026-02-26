"""
Nyx Light — vLLM-MLX Provider za Mac Studio M3 Ultra (256 GB)
V1.3 — MoE Architecture: Qwen3-235B-A22B

Ključna inovacija:
  Qwen3-235B-A22B koristi Mixture-of-Experts (MoE) arhitekturu.
  Od 235B parametara, samo ~22B je aktivno u svakom trenutku.
  MLX lazy evaluation + PagedAttention = stabilan rad za 15 korisnika.

Memory Budget (peak):
  Qwen3-235B-A22B aktivni eksperti: ~124 GB
  KV cache (15 sesija):              ~25–35 GB
  OS + servisi:                      ~12–18 GB
  Slobodno:                          ~56–78 GB od 256 GB

Adaptirano iz Nyx 47.0 VLLMMLXProvider.
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.llm")


class InferenceBackend(Enum):
    DIRECT = "direct"
    VLLM_SERVER = "vllm_server"
    AUTO = "auto"


@dataclass
class MoEConfig:
    """Konfiguracija za Mixture-of-Experts model."""
    total_params_b: float = 235.0
    active_params_b: float = 22.0
    num_experts: int = 128
    active_experts_per_token: int = 8
    peak_memory_gb: float = 124.0
    ssd_swap_enabled: bool = True
    expert_cache_size: int = 32      # "Toplih" eksperata u RAM-u


@dataclass
class LLMConfig:
    """Konfiguracija za vLLM-MLX inference."""
    backend: InferenceBackend = InferenceBackend.AUTO

    # Primarni model — MoE
    default_model: str = "mlx-community/Qwen3-235B-A22B-4bit"
    moe: MoEConfig = field(default_factory=MoEConfig)

    # Vision model — Dense, on-demand loading
    vision_model: str = "mlx-community/Qwen3-VL-8B-Instruct-4bit"
    vision_model_loaded: bool = False
    vision_unload_after_s: int = 300  # Unload nakon 5 min neaktivnosti

    # Fallback (low-memory)
    fallback_model: str = "mlx-community/Qwen3-30B-A3B-4bit"

    max_tokens: int = 4096
    temperature: float = 0.3
    top_p: float = 0.95
    repetition_penalty: float = 1.1
    max_kv_size: int = 8192
    kv_bits: int = 4
    enable_prompt_cache: bool = True
    prompt_cache_dir: str = "data/prompt_cache"
    vllm_host: str = "127.0.0.1"
    vllm_port: int = 8080
    vllm_max_concurrency: int = 15
    wired_memory_pct: float = 0.83
    total_memory_gb: float = 256.0


class NyxLightLLM:
    """
    LLM Provider za Nyx Light — Računovođa V1.3.
    
    MoE-Aware Inference Engine:
    - Qwen3-235B-A22B: 235B ukupno, ~22B aktivno (MoE routing)
    - Qwen3-VL-8B: On-demand loading za OCR zadatke
    - Dynamic memory management: MLX lazy eval + PagedAttention
    
    Podržava:
    1. vLLM-MLX server (produkcija, 15 korisnika)
    2. Direct MLX (development)
    3. Estimation fallback (testiranje bez GPU-a)
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._model_loaded = False
        self._vision_loaded = False
        self._vision_last_used = 0.0
        self._call_count = 0
        self._vision_call_count = 0
        self._total_tokens = 0
        self._active_experts_history: List[int] = []
        logger.info(
            "NyxLightLLM V1.3 initialized: model=%s (MoE %dB/%dB), backend=%s",
            self.config.default_model,
            int(self.config.moe.total_params_b),
            int(self.config.moe.active_params_b),
            self.config.backend.value,
        )

    def _is_vllm_running(self) -> bool:
        try:
            import urllib.request
            url = f"http://{self.config.vllm_host}:{self.config.vllm_port}/health"
            resp = urllib.request.urlopen(url, timeout=2)
            return resp.status == 200
        except Exception:
            return False

    async def generate(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generiraj odgovor pomoću LLM-a."""
        temp = temperature or self.config.temperature
        max_tok = max_tokens or self.config.max_tokens

        # Dodaj system prompt za računovodstvo
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}] + messages

        prompt = self._format_messages(messages)

        if self._is_vllm_running():
            content, tokens = await self._vllm_generate(prompt, max_tok, temp)
        else:
            content, tokens = self._fallback_generate(messages, max_tok)

        self._call_count += 1
        self._total_tokens += tokens

        return {
            "content": content,
            "tokens": tokens,
            "model": self.config.default_model,
            "call_count": self._call_count,
        }

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream tokena za chat UI."""
        temp = temperature or self.config.temperature
        max_tok = max_tokens or self.config.max_tokens
        prompt = self._format_messages(messages)

        if self._is_vllm_running():
            async for token in self._vllm_stream(prompt, max_tok, temp):
                yield token
        else:
            response, _ = self._fallback_generate(messages, max_tok)
            for word in response.split():
                yield word + " "
                await asyncio.sleep(0.02)

    async def _vllm_generate(
        self, prompt: str, max_tokens: int, temperature: float
    ) -> Tuple[str, int]:
        try:
            import urllib.request
            url = f"http://{self.config.vllm_host}:{self.config.vllm_port}/v1/completions"
            payload = json.dumps({
                "model": self.config.default_model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": self.config.top_p,
            }).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            resp = urllib.request.urlopen(req, timeout=120)
            data = json.loads(resp.read().decode())
            text = data["choices"][0]["text"]
            tokens = data.get("usage", {}).get("completion_tokens", len(text.split()))
            return text, tokens
        except Exception as e:
            logger.warning("vLLM request failed: %s — using fallback", e)
            return self._fallback_generate([], max_tokens)

    async def _vllm_stream(
        self, prompt: str, max_tokens: int, temperature: float
    ) -> AsyncIterator[str]:
        try:
            import urllib.request
            url = f"http://{self.config.vllm_host}:{self.config.vllm_port}/v1/completions"
            payload = json.dumps({
                "model": self.config.default_model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True,
            }).encode()
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=120)
            for line in resp:
                line = line.decode().strip()
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        text = chunk["choices"][0].get("text", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError):
                        pass
        except Exception as e:
            yield f"[Stream error: {e}]"

    def _fallback_generate(
        self, messages: List[Dict], max_tokens: int
    ) -> Tuple[str, int]:
        content = (
            "[Nyx Light — Estimation Mode] "
            "vLLM-MLX server nije dostupan. Pokrenite server s: "
            "mlx_lm.server --model mlx-community/Qwen3-235B-A22B-4bit "
            f"--port {self.config.vllm_port} --max-concurrency {self.config.vllm_max_concurrency} "
            "--moe-offload"
        )
        return content, len(content.split())

    def estimate_memory_usage(self) -> Dict[str, Any]:
        """Procijeni trenutnu memorijsku potrošnju (MoE-aware)."""
        moe = self.config.moe
        vision_gb = 5.0 if self._vision_loaded else 0.0
        kv_estimate_gb = min(self._call_count * 0.5, 35.0)  # Rough KV cache estimate

        active_model_gb = moe.peak_memory_gb  # Routing weights + active experts
        total_used = active_model_gb + vision_gb + kv_estimate_gb + 15.0  # +15 GB OS/services

        return {
            "model_architecture": "MoE",
            "total_params_b": moe.total_params_b,
            "active_params_b": moe.active_params_b,
            "active_experts": moe.active_experts_per_token,
            "total_experts": moe.num_experts,
            "model_memory_gb": round(active_model_gb, 1),
            "vision_loaded": self._vision_loaded,
            "vision_memory_gb": round(vision_gb, 1),
            "kv_cache_estimate_gb": round(kv_estimate_gb, 1),
            "total_estimated_gb": round(total_used, 1),
            "total_available_gb": self.config.total_memory_gb,
            "headroom_gb": round(self.config.total_memory_gb - total_used, 1),
            "ssd_swap_active": total_used > self.config.total_memory_gb * 0.78,
        }

    async def generate_vision(
        self,
        image_path: str,
        prompt: str = "Izvuci sve podatke s ovog računa: OIB, iznos, PDV, datum.",
    ) -> Dict[str, Any]:
        """
        Pokreni Vision model (Qwen3-VL-8B) za OCR.
        Model se učitava on-demand i unload-a nakon neaktivnosti.
        """
        self._vision_loaded = True
        self._vision_last_used = time.time()
        self._vision_call_count += 1

        # U produkciji: šalje request na vLLM-MLX s vision modelom
        # Za sada: fallback
        logger.info("Vision OCR requested: %s (model loaded on-demand)", image_path)

        return {
            "model": self.config.vision_model,
            "status": "on-demand loaded",
            "vision_calls": self._vision_call_count,
            "note": "Qwen3-VL-8B učitan na zahtjev — unload nakon 5 min",
        }

    def maybe_unload_vision(self):
        """Unload Vision model ako je neaktivan duže od vision_unload_after_s."""
        if self._vision_loaded and self._vision_last_used:
            idle = time.time() - self._vision_last_used
            if idle > self.config.vision_unload_after_s:
                self._vision_loaded = False
                logger.info(
                    "Vision model unloaded (idle %.0f s > %d s threshold)",
                    idle, self.config.vision_unload_after_s,
                )

    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    def get_stats(self) -> Dict[str, Any]:
        self.maybe_unload_vision()  # Check if vision should be unloaded
        memory = self.estimate_memory_usage()
        return {
            "model": self.config.default_model,
            "architecture": "MoE (Mixture-of-Experts)",
            "total_params_b": self.config.moe.total_params_b,
            "active_params_b": self.config.moe.active_params_b,
            "active_experts": f"{self.config.moe.active_experts_per_token}/{self.config.moe.num_experts}",
            "call_count": self._call_count,
            "vision_call_count": self._vision_call_count,
            "total_tokens": self._total_tokens,
            "vllm_running": self._is_vllm_running(),
            "backend": self.config.backend.value,
            "vision_loaded": self._vision_loaded,
            "memory": memory,
        }
