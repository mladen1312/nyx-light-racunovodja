"""
L2 Semantic Memory — trajna pravila kontiranja.
Adapted from Nyx 47.0 SemanticMemory with accounting-specific domains.
"""

import hashlib
import logging
import math
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nyx_light.memory.semantic")


@dataclass
class AccountingFact:
    id: str
    content: str
    domain: str = "kontiranje"
    topics: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    initial_confidence: float = 1.0
    current_confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.now)
    access_count: int = 0


class SemanticMemory:
    """L2: Semantička memorija — trajna pravila za kontiranje."""

    HALF_LIVES = {
        "kontiranje": 365,
        "porezno_pravilo": 180,
        "klijent_preferencija": 90,
        "zakon": float("inf"),
    }

    def __init__(self, confidence_threshold: float = 0.7):
        self.confidence_threshold = confidence_threshold
        self._facts: Dict[str, AccountingFact] = {}
        self._by_topic: Dict[str, Set[str]] = defaultdict(set)
        self._by_keyword: Dict[str, Set[str]] = defaultdict(set)
        self._counter = 0
        self._lock = threading.RLock()

    def store(self, content: str, domain: str = "kontiranje",
              confidence: float = 1.0, topics: List[str] = None,
              **kwargs) -> Tuple[AccountingFact, bool]:
        with self._lock:
            self._counter += 1
            fact_id = f"fact_{int(time.time()*1000)}_{self._counter:08d}"
            keywords = [w.lower().strip(".,!?") for w in content.split() if len(w) > 3]
            fact = AccountingFact(
                id=fact_id,
                content=content,
                domain=domain,
                topics=topics or [],
                keywords=keywords[:20],
                initial_confidence=confidence,
                current_confidence=confidence,
            )
            self._facts[fact_id] = fact
            for t in fact.topics:
                self._by_topic[t.lower()].add(fact_id)
            for k in fact.keywords:
                self._by_keyword[k].add(fact_id)
            return fact, True

    def search(self, topics: List[str] = None, keywords: List[str] = None,
               limit: int = 10, **kwargs) -> List[AccountingFact]:
        with self._lock:
            candidate_ids = None
            if topics:
                for t in topics:
                    ids = self._by_topic.get(t.lower(), set())
                    candidate_ids = ids.copy() if candidate_ids is None else candidate_ids & ids
            if keywords:
                for k in keywords:
                    ids = self._by_keyword.get(k.lower(), set())
                    candidate_ids = ids.copy() if candidate_ids is None else candidate_ids & ids
            if candidate_ids is None:
                candidate_ids = set(self._facts.keys())
            results = [self._facts[fid] for fid in candidate_ids if fid in self._facts]
            results.sort(key=lambda f: f.current_confidence, reverse=True)
            return results[:limit]

    def get_stats(self):
        return {"total_facts": len(self._facts), "topics": len(self._by_topic)}
