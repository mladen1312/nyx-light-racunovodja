"""
L0 Working Memory — session-scoped, sub-millisecond.
Adapted from Nyx 47.0 WorkingMemory.
"""

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional


@dataclass
class ChatMessage:
    id: str
    role: str
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkingMemory:
    """L0: Radna memorija — trenutni chat kontekst."""

    MAX_TURNS = 50
    MAX_TOKENS = 128_000

    def __init__(self):
        self._conversation: Deque[ChatMessage] = deque(maxlen=self.MAX_TURNS)
        self._session_id = str(uuid.uuid4())
        self._access_count = 0

    def add_message(self, role: str, content: str, metadata: Dict = None) -> ChatMessage:
        msg = ChatMessage(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )
        self._conversation.append(msg)
        self._access_count += 1
        return msg

    def get_conversation(self, last_n: int = None) -> List[ChatMessage]:
        if last_n:
            return list(self._conversation)[-last_n:]
        return list(self._conversation)

    def clear(self):
        self._conversation.clear()

    def get_stats(self) -> Dict[str, Any]:
        return {
            "session_id": self._session_id,
            "turns": len(self._conversation),
            "access_count": self._access_count,
        }
