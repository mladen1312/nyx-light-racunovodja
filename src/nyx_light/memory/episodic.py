"""
L1 Episodic Memory — dnevnik interakcija.
Sprječava ponavljanje iste greške unutar radnog dana.
Adapted from Nyx 47.0 EpisodicMemory.
"""

import hashlib
import logging
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("nyx_light.memory.episodic")


@dataclass
class Episode:
    id: str
    session_id: str
    user_id: str
    query: str
    response: str
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    keywords: List[str] = field(default_factory=list)


class EpisodicMemory:
    """L1: Epizodička memorija — dnevnik svih interakcija."""

    def __init__(self, max_entries: int = 1_000_000, retention_days: int = 180):
        self.max_entries = max_entries
        self.retention_days = retention_days
        self._episodes: Dict[str, Episode] = {}
        self._by_user: Dict[str, List[str]] = defaultdict(list)
        self._counter = 0
        self._lock = threading.RLock()

    def store(self, query: str, response: str, user_id: str, session_id: str,
              metadata: Dict = None, **kwargs) -> Episode:
        with self._lock:
            self._counter += 1
            ep_id = f"ep_{int(time.time()*1000)}_{self._counter:06d}"
            episode = Episode(
                id=ep_id,
                session_id=session_id,
                user_id=hashlib.sha256(user_id.encode()).hexdigest()[:16],
                query=query,
                response=response,
                metadata=metadata or {},
            )
            self._episodes[ep_id] = episode
            self._by_user[episode.user_id].append(ep_id)
            return episode

    def search_today(self, query: str) -> List[Episode]:
        today = datetime.now().date()
        results = []
        for ep in self._episodes.values():
            if ep.created_at.date() == today and query.lower() in ep.query.lower():
                results.append(ep)
        return results

    def get_stats(self):
        return {"total_episodes": len(self._episodes), "users": len(self._by_user)}
