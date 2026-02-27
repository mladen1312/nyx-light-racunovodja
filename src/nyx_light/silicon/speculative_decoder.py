"""
Nyx Light — Speculative Decoding Engine
════════════════════════════════════════
Adapted from Nyx 48.0 hardware/speculative_engine.py

Speculative decoding generates K draft tokens with a small/fast model,
then verifies them in ONE forward pass of the large model.
On Apple Silicon this is especially effective because:

  ┌──────────────────────────────────────────────────────────────┐
  │              SPECULATIVE DECODING ON APPLE SILICON            │
  │                                                               │
  │  DRAFT MODEL:  Qwen3-30B-A3B (3B active, ~2 GB)             │
  │  → Runs on ANE or CPU AMX → 50-80 tokens/sec                │
  │  → Generates K=5 candidate tokens                            │
  │                                                               │
  │  TARGET MODEL: Qwen3-235B-A22B (22B active, ~124 GB)        │
  │  → Runs on GPU → verifies all K tokens in ONE forward pass  │
  │  → Accepts 3-4 of 5 tokens (60-80% acceptance)              │
  │                                                               │
  │  RESULT: Instead of 5 serial GPU forward passes,             │
  │          we do 1 GPU pass + 1 ANE pass = ~2.5× speedup      │
  │                                                               │
  │  UMA ADVANTAGE: Draft→Target tensor = pointer pass (0 copy)  │
  └──────────────────────────────────────────────────────────────┘

For accounting workload:
  - Kontiranje proposals: repetitive patterns → high acceptance rate
  - Law citations: structured text → high acceptance rate
  - Expected speedup: 2.0-2.8× for typical queries

Author: Dr. Mladen Mešter · Nexellum Lab d.o.o.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("nyx_light.silicon.speculative")


# ═══════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════

class DraftStrategy(Enum):
    """Draft model placement strategy."""
    GPU_DRAFT = "gpu_draft"      # Small model on same GPU (default)
    ANE_DRAFT = "ane_draft"      # Small model on Neural Engine
    CPU_AMX_DRAFT = "cpu_amx"    # Small model on CPU AMX units
    NGRAM_DRAFT = "ngram"        # N-gram lookup (no model, fastest)
    DISABLED = "disabled"        # Standard decoding only


@dataclass
class SpeculativeConfig:
    """Configuration for speculative decoding."""
    # Draft model
    draft_model_name: str = "Qwen3-30B-A3B"
    draft_model_params_b: float = 3.0  # Active params (MoE)
    draft_strategy: DraftStrategy = DraftStrategy.GPU_DRAFT

    # Target model
    target_model_name: str = "Qwen3-235B-A22B"
    target_model_params_b: float = 22.0  # Active params

    # Speculative tokens
    num_speculative_tokens: int = 5     # K: tokens to draft
    min_speculative_tokens: int = 2     # Minimum K
    max_speculative_tokens: int = 8     # Maximum K
    acceptance_threshold: float = 0.5   # Below this → reduce K

    # Thermal management
    thermal_reduce_temp_c: float = 85.0   # Reduce K above this
    thermal_fallback_temp_c: float = 95.0  # Disable speculative above this

    # N-gram fallback
    ngram_n: int = 4                      # N-gram context window
    ngram_min_frequency: int = 3          # Min occurrences to use


@dataclass
class SpeculativeStats:
    """Runtime statistics for speculative decoding."""
    total_draft_tokens: int = 0
    total_accepted_tokens: int = 0
    total_rejected_tokens: int = 0
    total_draft_calls: int = 0
    total_target_calls: int = 0
    total_fallback_calls: int = 0
    total_tokens_generated: int = 0
    thermal_throttle_count: int = 0
    total_time_ms: float = 0.0
    draft_time_ms: float = 0.0
    verify_time_ms: float = 0.0

    @property
    def acceptance_rate(self) -> float:
        total = self.total_accepted_tokens + self.total_rejected_tokens
        return self.total_accepted_tokens / max(1, total)

    @property
    def speedup_ratio(self) -> float:
        """Estimated speedup vs standard decoding."""
        if self.total_target_calls == 0:
            return 1.0
        avg_accepted = self.total_accepted_tokens / max(1, self.total_target_calls)
        # Speedup ≈ (accepted+1) / (1 + draft_overhead)
        draft_overhead = self.draft_time_ms / max(1, self.verify_time_ms)
        return (avg_accepted + 1) / (1 + draft_overhead)

    @property
    def tokens_per_second(self) -> float:
        if self.total_time_ms == 0:
            return 0.0
        return self.total_tokens_generated / (self.total_time_ms / 1000)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "acceptance_rate": round(self.acceptance_rate * 100, 1),
            "speedup": round(self.speedup_ratio, 2),
            "tokens_per_sec": round(self.tokens_per_second, 1),
            "total_generated": self.total_tokens_generated,
            "total_drafted": self.total_draft_tokens,
            "total_accepted": self.total_accepted_tokens,
            "total_rejected": self.total_rejected_tokens,
            "thermal_throttles": self.thermal_throttle_count,
            "draft_calls": self.total_draft_calls,
            "target_calls": self.total_target_calls,
            "fallback_calls": self.total_fallback_calls,
        }


@dataclass
class DraftResult:
    tokens: List[int] = field(default_factory=list)
    log_probs: List[float] = field(default_factory=list)
    latency_ms: float = 0.0


@dataclass
class VerifyResult:
    accepted_count: int = 0
    accepted_tokens: List[int] = field(default_factory=list)
    correction_token: Optional[int] = None
    latency_ms: float = 0.0


# ═══════════════════════════════════════════════════════════════
# N-gram Draft Cache (zero-model speculative)
# ═══════════════════════════════════════════════════════════════

class NgramDraftCache:
    """
    N-gram based draft token prediction.

    For accounting workloads, many patterns repeat:
      "Konto 4010 — Nabava" → high frequency
      "PDV 25% na" → high frequency
      "Obveza prema dobavljaču" → high frequency

    This cache builds n-gram statistics from accepted tokens
    and uses them for zero-cost draft predictions.
    """

    def __init__(self, n: int = 4, min_freq: int = 3):
        self._n = n
        self._min_freq = min_freq
        self._ngrams: Dict[tuple, Dict[int, int]] = {}  # context → {next_token: count}
        self._total_predictions = 0
        self._total_hits = 0

    def update(self, tokens: List[int]):
        """Add accepted token sequence to n-gram statistics."""
        for i in range(len(tokens) - self._n):
            context = tuple(tokens[i:i + self._n])
            next_tok = tokens[i + self._n]
            if context not in self._ngrams:
                self._ngrams[context] = {}
            self._ngrams[context][next_tok] = self._ngrams[context].get(next_tok, 0) + 1

    def draft(self, context: List[int], k: int) -> Optional[DraftResult]:
        """
        Draft K tokens using n-gram lookup.
        Returns None if n-gram cache doesn't have sufficient data.
        """
        if len(context) < self._n:
            return None

        tokens = []
        log_probs = []
        current = list(context)

        for _ in range(k):
            key = tuple(current[-self._n:])
            if key not in self._ngrams:
                break
            candidates = self._ngrams[key]
            # Find most frequent next token
            best_tok = max(candidates, key=candidates.get)
            freq = candidates[best_tok]
            total = sum(candidates.values())

            if freq < self._min_freq:
                break

            prob = freq / total
            tokens.append(best_tok)
            log_probs.append(math.log(max(prob, 1e-10)))
            current.append(best_tok)

        self._total_predictions += 1
        if tokens:
            self._total_hits += 1

        if not tokens:
            return None

        return DraftResult(tokens=tokens, log_probs=log_probs, latency_ms=0.01)

    @property
    def hit_rate(self) -> float:
        return self._total_hits / max(1, self._total_predictions)

    @property
    def vocab_size(self) -> int:
        return len(self._ngrams)

    def stats(self) -> Dict[str, Any]:
        return {
            "ngram_n": self._n,
            "vocab_entries": self.vocab_size,
            "hit_rate": round(self.hit_rate * 100, 1),
            "predictions": self._total_predictions,
        }


# ═══════════════════════════════════════════════════════════════
# Speculative Decoding Engine
# ═══════════════════════════════════════════════════════════════

class SpeculativeDecodingEngine:
    """
    Thermal-aware speculative decoding engine for Apple Silicon.

    Usage:
        engine = SpeculativeDecodingEngine(config)
        tokens = await engine.generate("Kontiraj račun...", max_tokens=500)

    The engine adaptively adjusts:
      - K (number of speculative tokens) based on acceptance rate
      - Draft strategy based on thermal state
      - Falls back to standard decoding if GPU is too hot
      - Uses n-gram cache for zero-cost speculation on repetitive patterns

    Integration with vllm-mlx:
      - draft_fn: calls small model via vllm-mlx endpoint
      - verify_fn: calls target model via vllm-mlx batch verification
      - Both share UMA memory → zero-copy tensor passing
    """

    def __init__(
        self,
        config: Optional[SpeculativeConfig] = None,
        draft_fn: Optional[Callable] = None,
        verify_fn: Optional[Callable] = None,
        standard_fn: Optional[Callable] = None,
        thermal_fn: Optional[Callable] = None,
    ):
        self._config = config or SpeculativeConfig()
        self._draft_fn = draft_fn
        self._verify_fn = verify_fn
        self._standard_fn = standard_fn
        self._thermal_fn = thermal_fn
        self._stats = SpeculativeStats()
        self._current_k = self._config.num_speculative_tokens
        self._ngram_cache = NgramDraftCache(
            n=self._config.ngram_n,
            min_freq=self._config.ngram_min_frequency,
        )
        self._enabled = self._config.draft_strategy != DraftStrategy.DISABLED

        logger.info(
            "SpeculativeEngine: strategy=%s, draft=%s (%.1fB), target=%s (%.1fB), K=%d",
            self._config.draft_strategy.value,
            self._config.draft_model_name, self._config.draft_model_params_b,
            self._config.target_model_name, self._config.target_model_params_b,
            self._current_k,
        )

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def stats(self) -> SpeculativeStats:
        return self._stats

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        stop_tokens: Optional[List[int]] = None,
        context_tokens: Optional[List[int]] = None,
    ) -> List[int]:
        """
        Generate tokens using speculative decoding.

        If speculative decoding is disabled or thermal limits are hit,
        falls back to standard autoregressive generation.
        """
        if not self._enabled:
            return await self._standard_generate(prompt, [], max_tokens)

        generated: List[int] = list(context_tokens or [])
        start = time.monotonic()

        while len(generated) < max_tokens:
            # Check thermal state
            gpu_temp = self._get_gpu_temp()

            if gpu_temp >= self._config.thermal_fallback_temp_c:
                self._stats.thermal_throttle_count += 1
                self._stats.total_fallback_calls += 1
                tokens = await self._standard_generate(prompt, generated, 1)
                generated.extend(tokens)
                continue

            if gpu_temp >= self._config.thermal_reduce_temp_c:
                self._current_k = max(
                    self._config.min_speculative_tokens, self._current_k - 1
                )
                self._stats.thermal_throttle_count += 1

            # Step 1: Try n-gram draft first (zero cost)
            draft_result = self._ngram_cache.draft(generated, self._current_k)

            # Step 2: If n-gram misses, use model draft
            if draft_result is None:
                draft_start = time.monotonic()
                draft_result = await self._draft_tokens(prompt, generated, self._current_k)
                self._stats.draft_time_ms += (time.monotonic() - draft_start) * 1000
                self._stats.total_draft_calls += 1
            self._stats.total_draft_tokens += len(draft_result.tokens)

            if not draft_result.tokens:
                tokens = await self._standard_generate(prompt, generated, 1)
                generated.extend(tokens)
                continue

            # Step 3: Verify all K tokens with target model in one pass
            verify_start = time.monotonic()
            verify_result = await self._verify_tokens(
                prompt, generated, draft_result.tokens, draft_result.log_probs,
            )
            self._stats.verify_time_ms += (time.monotonic() - verify_start) * 1000
            self._stats.total_target_calls += 1

            # Step 4: Accept verified tokens
            accepted = verify_result.accepted_tokens
            self._stats.total_accepted_tokens += len(accepted)
            self._stats.total_rejected_tokens += len(draft_result.tokens) - len(accepted)
            generated.extend(accepted)

            # Update n-gram cache with accepted tokens
            if accepted:
                self._ngram_cache.update(generated[-len(accepted) - self._config.ngram_n:])

            # Add correction token if target disagrees
            if verify_result.correction_token is not None:
                generated.append(verify_result.correction_token)

            # Step 5: Adaptive K
            self._adapt_k()

            # Check stop tokens
            if stop_tokens and generated and generated[-1] in stop_tokens:
                break

        elapsed_ms = (time.monotonic() - start) * 1000
        self._stats.total_tokens_generated += len(generated)
        self._stats.total_time_ms += elapsed_ms

        return generated[:max_tokens]

    # ── Draft/Verify ──

    async def _draft_tokens(
        self, prompt: str, context: List[int], k: int
    ) -> DraftResult:
        """Generate K draft tokens using small model."""
        if self._draft_fn:
            return await self._draft_fn(prompt, context, k)
        # Simulation mode
        tokens = [random.randint(100, 50000) for _ in range(k)]
        log_probs = [-random.uniform(0.1, 3.0) for _ in range(k)]
        return DraftResult(tokens=tokens, log_probs=log_probs, latency_ms=k * 2.0)

    async def _verify_tokens(
        self, prompt: str, context: List[int],
        draft_tokens: List[int], draft_log_probs: List[float],
    ) -> VerifyResult:
        """Verify K draft tokens with target model in one forward pass."""
        if self._verify_fn:
            return await self._verify_fn(prompt, context, draft_tokens, draft_log_probs)
        # Simulation: accept based on draft confidence
        accepted = []
        correction = None
        for tok, log_p in zip(draft_tokens, draft_log_probs):
            accept_prob = min(1.0, math.exp(log_p + 0.5))
            if random.random() < accept_prob:
                accepted.append(tok)
            else:
                correction = random.randint(100, 50000)
                break
        return VerifyResult(
            accepted_count=len(accepted),
            accepted_tokens=accepted,
            correction_token=correction,
            latency_ms=15.0,
        )

    async def _standard_generate(
        self, prompt: str, context: List[int], n_tokens: int
    ) -> List[int]:
        """Standard autoregressive generation (fallback)."""
        if self._standard_fn:
            return await self._standard_fn(prompt, context, n_tokens)
        return [random.randint(100, 50000) for _ in range(n_tokens)]

    # ── Adaptive K ──

    def _adapt_k(self):
        """Adjust K based on acceptance rate."""
        rate = self._stats.acceptance_rate
        if rate >= 0.90 and self._current_k < self._config.max_speculative_tokens:
            self._current_k += 1
        elif rate < self._config.acceptance_threshold and \
                self._current_k > self._config.min_speculative_tokens:
            self._current_k -= 1

    # ── Thermal ──

    def _get_gpu_temp(self) -> float:
        if self._thermal_fn:
            return self._thermal_fn()
        return 55.0  # Simulated: nominal

    def get_stats(self) -> Dict[str, Any]:
        return {
            "speculative": self._stats.to_dict(),
            "ngram_cache": self._ngram_cache.stats(),
            "current_k": self._current_k,
            "strategy": self._config.draft_strategy.value,
            "enabled": self._enabled,
        }

    def reset_stats(self):
        self._stats = SpeculativeStats()
