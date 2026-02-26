"""
Nyx Light — vLLM-MLX Provider za Mac Studio M5 Ultra (192 GB)

Optimizirani inference engine za 15 paralelnih korisnika.
Koristi Continuous Batching + PagedAttention za glatko posluživanje.

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
class LLMConfig:
    """Konfiguracija za vLLM-MLX inference."""
    backend: InferenceBackend = InferenceBackend.AUTO
    default_model: str = "mlx-community/Qwen2.5-72B-Instruct-4bit"
    vision_model: str = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"
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


class NyxLightLLM:
    """
    LLM Provider za Nyx Light — Računovođa.
    
    Podržava:
    1. vLLM-MLX server (produkcija, 15 korisnika)
    2. Direct MLX (development)
    3. Estimation fallback (testiranje bez GPU-a)
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._model_loaded = False
        self._call_count = 0
        self._total_tokens = 0
        logger.info(
            "NyxLightLLM initialized: model=%s, backend=%s",
            self.config.default_model, self.config.backend.value
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
            "mlx_lm.server --model mlx-community/Qwen2.5-72B-Instruct-4bit "
            f"--port {self.config.vllm_port} --max-concurrency {self.config.vllm_max_concurrency}"
        )
        return content, len(content.split())

    def _format_messages(self, messages: List[Dict[str, str]]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"<|im_start|>{role}\n{content}<|im_end|>")
        parts.append("<|im_start|>assistant\n")
        return "\n".join(parts)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "call_count": self._call_count,
            "total_tokens": self._total_tokens,
            "model": self.config.default_model,
            "vllm_running": self._is_vllm_running(),
            "backend": self.config.backend.value,
        }
