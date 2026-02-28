"""
Nyx Light — LLM Request Queue za 15 konkurentnih korisnika

Problemi koje rješava:
1. Max 3 istovremena LLM poziva (Semaphore) — sprječava OOM
2. Fair scheduling — FIFO red, nijedan korisnik ne monopolizira
3. Per-user rate limit — max 10 req/min po korisniku
4. Timeout — request ne visi zauvijek
5. Priority — admin/hitni upiti idu prvo

Arhitektura:
  Korisnik → RequestQueue → Semaphore(3) → LLM Provider → Response
                ↓
           Rate Limiter (10/min/user)
                ↓
           Metrics (avg wait, queue depth)
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger("nyx_light.llm.queue")

# ── Konfiguracija ──
MAX_CONCURRENT_LLM = 3          # Max istovremenih LLM poziva
MAX_REQUESTS_PER_MIN = 10       # Per-user rate limit
REQUEST_TIMEOUT_SEC = 120       # Max čekanje u redu
QUEUE_MAX_SIZE = 50             # Max veličina reda


@dataclass
class QueuedRequest:
    """Jedan zahtjev u redu čekanja."""
    request_id: str
    user_id: str
    priority: int = 0           # 0=normal, 1=high (admin), 2=urgent
    created_at: float = field(default_factory=time.time)
    future: asyncio.Future = field(default=None)
    func: Callable = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)

    def __lt__(self, other):
        """Za PriorityQueue — viši priority ide prvi, pa FIFO."""
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.created_at < other.created_at


class UserRateLimiter:
    """Sliding window rate limiter po korisniku."""

    def __init__(self, max_per_minute: int = MAX_REQUESTS_PER_MIN):
        self.max_per_minute = max_per_minute
        self._timestamps: Dict[str, List[float]] = defaultdict(list)

    def check(self, user_id: str) -> bool:
        """Provjeri smije li korisnik poslati request."""
        now = time.time()
        cutoff = now - 60
        # Očisti stare
        self._timestamps[user_id] = [
            t for t in self._timestamps[user_id] if t > cutoff
        ]
        return len(self._timestamps[user_id]) < self.max_per_minute

    def record(self, user_id: str):
        """Zabilježi request."""
        self._timestamps[user_id].append(time.time())

    def remaining(self, user_id: str) -> int:
        """Koliko requestova korisnik još ima."""
        now = time.time()
        cutoff = now - 60
        recent = [t for t in self._timestamps[user_id] if t > cutoff]
        return max(0, self.max_per_minute - len(recent))

    def reset_in(self, user_id: str) -> float:
        """Za koliko sekundi se resetira limit."""
        if not self._timestamps[user_id]:
            return 0
        oldest = min(t for t in self._timestamps[user_id] if t > time.time() - 60)
        return max(0, 60 - (time.time() - oldest))


class LLMRequestQueue:
    """
    Fair request queue za LLM pozive.

    Korištenje:
        queue = LLMRequestQueue()

        # U API endpointu:
        result = await queue.submit(
            user_id="racunovodja1",
            func=llm.generate,
            messages=[...],
            temperature=0.3,
        )
    """

    def __init__(
        self,
        max_concurrent: int = MAX_CONCURRENT_LLM,
        max_per_minute: int = MAX_REQUESTS_PER_MIN,
        timeout: float = REQUEST_TIMEOUT_SEC,
    ):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rate_limiter = UserRateLimiter(max_per_minute)
        self._timeout = timeout
        self._max_concurrent = max_concurrent

        # Metrike
        self._total_requests = 0
        self._total_completed = 0
        self._total_rejected = 0
        self._total_timeouts = 0
        self._total_wait_time = 0.0
        self._active_requests = 0
        self._queue_depth = 0
        self._user_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"requests": 0, "completed": 0, "errors": 0}
        )

        logger.info(
            "LLMRequestQueue: max_concurrent=%d, rate_limit=%d/min, timeout=%ds",
            max_concurrent, max_per_minute, timeout,
        )

    async def submit(
        self,
        user_id: str,
        func: Callable[..., Coroutine],
        *args,
        priority: int = 0,
        **kwargs,
    ) -> Any:
        """
        Submit LLM request s rate limiting i fair scheduling.

        Args:
            user_id: ID korisnika
            func: Async funkcija za poziv (npr. llm.generate)
            priority: 0=normal, 1=high, 2=urgent
            *args, **kwargs: Argumenti za func

        Returns:
            Rezultat func poziva

        Raises:
            RateLimitError: Previše requestova
            QueueFullError: Red je pun
            TimeoutError: Predugo čekanje
        """
        # 1. Rate limit check
        if not self._rate_limiter.check(user_id):
            remaining_sec = self._rate_limiter.reset_in(user_id)
            self._total_rejected += 1
            logger.warning("Rate limit: %s (reset za %.0fs)", user_id, remaining_sec)
            raise RateLimitError(
                f"Previše zahtjeva. Pokušajte za {int(remaining_sec)} sekundi.",
                retry_after=remaining_sec,
            )

        # 2. Queue depth check
        if self._queue_depth >= QUEUE_MAX_SIZE:
            self._total_rejected += 1
            raise QueueFullError("Sustav je preopterećen. Pokušajte za minutu.")

        # 3. Record & track
        self._rate_limiter.record(user_id)
        self._total_requests += 1
        self._queue_depth += 1
        self._user_stats[user_id]["requests"] += 1

        start_wait = time.time()

        try:
            # 4. Acquire semaphore (fair FIFO through asyncio)
            async with asyncio.timeout(self._timeout):
                await self._semaphore.acquire()

            wait_time = time.time() - start_wait
            self._total_wait_time += wait_time
            self._queue_depth -= 1
            self._active_requests += 1

            if wait_time > 2:
                logger.info(
                    "Request %s čekao %.1fs u redu (active=%d)",
                    user_id, wait_time, self._active_requests,
                )

            try:
                # 5. Execute LLM call
                result = await func(*args, **kwargs)
                self._total_completed += 1
                self._user_stats[user_id]["completed"] += 1
                return result

            except Exception as e:
                self._user_stats[user_id]["errors"] += 1
                logger.error("LLM error za %s: %s", user_id, e)
                raise

            finally:
                self._active_requests -= 1
                self._semaphore.release()

        except asyncio.TimeoutError:
            self._queue_depth -= 1
            self._total_timeouts += 1
            logger.warning("Timeout za %s nakon %.0fs", user_id, self._timeout)
            raise TimeoutError(
                f"Zahtjev je istekao nakon {int(self._timeout)}s. "
                "Sustav je zauzet — pokušajte ponovo."
            )

    def get_stats(self) -> Dict[str, Any]:
        """Statistike reda čekanja."""
        avg_wait = (
            self._total_wait_time / self._total_completed
            if self._total_completed > 0
            else 0
        )
        return {
            "active_requests": self._active_requests,
            "max_concurrent": self._max_concurrent,
            "queue_depth": self._queue_depth,
            "total_requests": self._total_requests,
            "total_completed": self._total_completed,
            "total_rejected": self._total_rejected,
            "total_timeouts": self._total_timeouts,
            "avg_wait_seconds": round(avg_wait, 2),
            "utilization_pct": round(
                self._active_requests / self._max_concurrent * 100, 1
            ),
        }

    def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Statistike za jednog korisnika."""
        stats = self._user_stats[user_id]
        return {
            "user_id": user_id,
            "requests": stats["requests"],
            "completed": stats["completed"],
            "errors": stats["errors"],
            "rate_remaining": self._rate_limiter.remaining(user_id),
            "rate_reset_in": round(self._rate_limiter.reset_in(user_id), 0),
        }


# ── Custom exceptions ──

class RateLimitError(Exception):
    def __init__(self, message: str, retry_after: float = 60):
        super().__init__(message)
        self.retry_after = retry_after


class QueueFullError(Exception):
    pass
